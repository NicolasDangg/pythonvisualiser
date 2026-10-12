"""Runs user code under sys.settrace and prints a JSON execution trace.

Input (stdin):  {"code": "...", "stdin": "optional input() lines"}
Output (stdout): {"steps": [...], "error": "..."?}

Each step holds the line about to run, the call stack (frames + variables),
a heap snapshot of every object reachable from those frames, stdout so far,
and any diagrams the program emitted with mermaid(src, title).
"""
import builtins
import collections
import io
import json
import sys
import types

FILENAME = "<user>"
MAX_STEPS = 1000
MAX_ITEMS = 100
MAX_STR = 200
HIDDEN = {"mermaid", "input"}


class StepLimit(BaseException):
    """BaseException so a bare `except Exception` in user code can't swallow it."""


class Tracer:
    def __init__(self, stdin_text=""):
        self.steps = []
        self.ids = {}    # id(obj) -> small stable number
        self.keep = []   # keep objects alive so id() values are never reused
        self.out = io.StringIO()
        self.custom = {}
        self.stdin_lines = iter(stdin_text.splitlines())

    # ---------- serialisation ----------
    def oid(self, v):
        k = id(v)
        if k not in self.ids:
            self.ids[k] = len(self.ids) + 1
            self.keep.append(v)
        return self.ids[k]

    def enc(self, v, heap):
        if v is None or isinstance(v, (bool, int, float, complex)):
            return {"p": repr(v)}
        if isinstance(v, str):
            return {"p": repr(v) if len(v) <= MAX_STR else repr(v[:MAX_STR]) + "…"}
        n = self.oid(v)
        if n not in heap:
            heap[n] = None  # placeholder breaks cycles
            heap[n] = self.obj(v, heap)
        return {"r": n}

    def obj(self, v, heap):
        t = type(v).__name__
        if isinstance(v, (list, tuple, collections.deque, set, frozenset)):
            items = list(v)
            if isinstance(v, (set, frozenset)):
                try:
                    items.sort()
                except TypeError:
                    items.sort(key=repr)
            return {"k": "seq", "type": t,
                    "items": [self.enc(x, heap) for x in items[:MAX_ITEMS]],
                    "more": max(0, len(items) - MAX_ITEMS)}
        if isinstance(v, dict):
            items = list(v.items())
            return {"k": "dict", "type": t,
                    "items": [[self.enc(a, heap), self.enc(b, heap)] for a, b in items[:MAX_ITEMS]],
                    "more": max(0, len(items) - MAX_ITEMS)}
        if isinstance(v, (types.FunctionType, types.BuiltinFunctionType, types.MethodType)):
            return {"k": "func", "type": t, "name": getattr(v, "__qualname__", repr(v))}
        if isinstance(v, type):
            return {"k": "class", "type": "class", "name": v.__name__}
        if isinstance(v, types.ModuleType):
            return {"k": "other", "type": "module", "repr": v.__name__}
        fields = []
        d = getattr(v, "__dict__", None)
        if isinstance(d, dict):
            fields = list(d.items())
        for cls in type(v).__mro__:
            for s in getattr(cls, "__slots__", ()):
                if hasattr(v, s) and s not in ("__dict__", "__weakref__"):
                    fields.append((s, getattr(v, s)))
        if fields or isinstance(d, dict):
            return {"k": "obj", "type": t,
                    "fields": [[k, self.enc(x, heap)] for k, x in fields]}
        try:
            r = repr(v)
        except Exception:
            r = f"<{t}>"
        return {"k": "other", "type": t, "repr": r[:MAX_STR]}

    # ---------- tracing ----------
    def snap(self, frame, event, arg):
        if len(self.steps) >= MAX_STEPS:
            raise StepLimit
        chain, f = [], frame
        while f is not None:
            if f.f_code.co_filename == FILENAME:
                chain.append(f)
            f = f.f_back
        chain.reverse()
        heap, stack = {}, []
        for f in chain:
            is_mod = f.f_code.co_name == "<module>"
            ns = f.f_globals if is_mod else f.f_locals
            vars_ = []
            for k, v in list(ns.items()):
                if is_mod and (k.startswith("__") or k in HIDDEN or isinstance(v, types.ModuleType)):
                    continue
                vars_.append([k, self.enc(v, heap)])
            stack.append({"name": "Global frame" if is_mod else f.f_code.co_name,
                          "line": f.f_lineno, "vars": vars_})
        step = {"line": frame.f_lineno, "event": event, "stack": stack, "heap": heap,
                "stdout": self.out.getvalue(), "custom": dict(self.custom)}
        if event == "return" and frame.f_code.co_name != "<module>":
            stack[-1]["ret"] = self.enc(arg, heap)
        elif event == "exception":
            step["exc"] = f"{arg[0].__name__}: {arg[1]}"
        self.steps.append(step)

    def global_trace(self, frame, event, arg):
        if frame.f_code.co_filename != FILENAME:
            return None
        return self.local_trace

    def local_trace(self, frame, event, arg):
        if event in ("line", "return", "exception"):
            self.snap(frame, event, arg)
        return self.local_trace

    # ---------- helpers exposed to user code ----------
    def mermaid(self, src, title="diagram"):
        self.custom[str(title)] = str(src)

    def input(self, prompt=""):
        self.out.write(str(prompt))
        try:
            line = next(self.stdin_lines)
        except StopIteration:
            raise EOFError("no more stdin lines (fill in the stdin box)") from None
        self.out.write(line + "\n")
        return line

    def run(self, code):
        try:
            compiled = compile(code, FILENAME, "exec")
        except SyntaxError as e:
            return {"steps": [], "error": f"SyntaxError: {e.msg}", "errorLine": e.lineno}
        g = {"__name__": "__main__", "__builtins__": builtins,
             "mermaid": self.mermaid, "input": self.input}
        error = error_line = None
        sys.stdout = self.out
        sys.settrace(self.global_trace)
        try:
            exec(compiled, g)
        except StepLimit:
            error = f"Stopped after {MAX_STEPS} steps (infinite loop?)"
        except BaseException as e:
            error = f"{type(e).__name__}: {e}"
            tb = e.__traceback__
            while tb is not None:
                if tb.tb_frame.f_code.co_filename == FILENAME:
                    error_line = tb.tb_lineno
                tb = tb.tb_next
        finally:
            sys.settrace(None)
            sys.stdout = sys.__stdout__
        if error and self.steps:
            last = dict(self.steps[-1], event="exception", exc=error, stdout=self.out.getvalue())
            if error_line:
                last["line"] = error_line
            self.steps.append(last)
        return {"steps": self.steps, "error": error, "errorLine": error_line}


def main():
    req = json.loads(sys.stdin.read() or "{}")
    result = Tracer(req.get("stdin", "")).run(req.get("code", ""))
    sys.__stdout__.write(json.dumps(result))


if __name__ == "__main__":
    main()
