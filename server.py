#!/usr/bin/env python3
"""Tiny local server for the visualiser. Stdlib only.

    python3 server.py               # open http://127.0.0.1:8000
    python3 server.py my_tree.py    # preload a file into the editor
"""
import argparse
import json
import pathlib
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
TIMEOUT = 15
INITIAL = ""


class Handler(BaseHTTPRequestHandler):
    def send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(200, "text/html; charset=utf-8", (HERE / "index.html").read_bytes())
        elif self.path == "/initial":
            self.send(200, "text/plain; charset=utf-8", INITIAL.encode())
        else:
            self.send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path != "/run":
            return self.send(404, "text/plain", b"not found")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            # Each run gets a fresh subprocess: isolated state + hard timeout.
            p = subprocess.run([sys.executable, str(HERE / "tracer.py")], input=body,
                               capture_output=True, timeout=TIMEOUT, cwd=HERE)
            out = p.stdout or json.dumps(
                {"steps": [], "error": p.stderr.decode(errors="replace")[-3000:] or "tracer crashed"}).encode()
        except subprocess.TimeoutExpired:
            out = json.dumps({"steps": [], "error": f"Timed out after {TIMEOUT}s"}).encode()
        self.send(200, "application/json", out)

    def log_message(self, *args):
        pass


def main():
    global INITIAL
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="python file to preload into the editor")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    if a.file:
        INITIAL = pathlib.Path(a.file).read_text()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Python visualiser → http://127.0.0.1:{a.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
