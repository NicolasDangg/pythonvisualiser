"""Vercel Python function: POST /run (rewritten to /api/run) -> JSON trace.

Same contract as server.py's /run; tracer.py is bundled via vercel.json includeFiles.
"""
import json
import pathlib
import subprocess
import sys
from http.server import BaseHTTPRequestHandler

TRACER = pathlib.Path(__file__).resolve().parent.parent / "tracer.py"
TIMEOUT = 10


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            # Subprocess, not in-process: tracer swaps sys.stdout, which would clash across concurrent requests.
            p = subprocess.run([sys.executable, str(TRACER)], input=body,
                               capture_output=True, timeout=TIMEOUT)
            out = p.stdout or json.dumps(
                {"steps": [], "error": p.stderr.decode(errors="replace")[-3000:] or "tracer crashed"}).encode()
        except subprocess.TimeoutExpired:
            out = json.dumps({"steps": [], "error": f"Timed out after {TIMEOUT}s"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)
