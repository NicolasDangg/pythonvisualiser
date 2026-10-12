# Python Visualiser

A small, pythontutor-style stepper for your own Python code, with Mermaid diagrams for data structures.
It has no dependencies: the server and tracer use only the standard library, and Mermaid loads from a CDN.

```bash
python3 server.py              # → http://127.0.0.1:8000
python3 server.py my_bst.py    # preload a file
```

Step with ← / → or the slider. Cmd/Ctrl+Enter runs the code.

## What gets drawn automatically

| Structure | Detected when… |
|---|---|
| Binary tree | object has `left` and `right` attributes |
| N-ary tree | object has a `children` list of objects |
| Linked list | object has `next` (and optionally `prev`) |
| Circular queue | object has a list attribute + `front`/`head` + `rear`/`tail` or `size`/`count` ints |
| Graph | dict whose values are lists/sets of keys (adjacency list); `visited`/`seen` sets colour nodes |
| Array heap | a flat list in a variable named `*heap*` / `*tree*` is drawn as an implicit binary tree |

Node labels come from `val` / `value` / `key` / `data` / `name`. Nodes that a variable (or a wrapper field like `self.head`) points to are highlighted and labelled.

Tick **memory graph** to draw the whole stack and heap as one Mermaid graph.

## Custom diagrams

`mermaid(src, title="diagram")` is available as a built-in. Each call adds or replaces a diagram, and it stays visible on later steps:

```python
mermaid("flowchart LR\n a --> b --> c", title="my pipeline")
```

## Limits

Runs are capped at 1000 steps and 15 s. Each run happens in a fresh subprocess bound to localhost.
The server runs any code you paste, so don't expose it to a network.
