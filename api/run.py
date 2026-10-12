"""Vercel Python function: POST /run (rewritten to /api/run) -> JSON trace.

Same contract as server.py's /run; tracer.py is bundled via vercel.json includeFiles.
proxy.js already gates every request; the session check here is a second layer so the
code-running endpoint stays closed even if the middleware is ever skipped.
"""
import hashlib
import hmac
import json
import os
import pathlib
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler

TRACER = pathlib.Path(__file__).resolve().parent.parent / "tracer.py"
TIMEOUT = 10
COOKIE = "pv_session"


def valid_session(cookie_header):
    secret = os.environ.get("AUTH_SECRET")
    if not secret:
        return False
    for part in (cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name != COOKIE:
            continue
        exp, _, sig = value.partition(".")
        if not exp.isdigit() or int(exp) < time.time():
            return False
        want = hmac.new(secret.encode(), exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, want)
    return False


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not valid_session(self.headers.get("Cookie")):
            return self.reply(401, json.dumps({"steps": [], "error": "Not logged in. Reload the page to log in."}).encode())
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            # Subprocess, not in-process: tracer swaps sys.stdout, which would clash across concurrent requests.
            p = subprocess.run([sys.executable, str(TRACER)], input=body,
                               capture_output=True, timeout=TIMEOUT)
            out = p.stdout or json.dumps(
                {"steps": [], "error": p.stderr.decode(errors="replace")[-3000:] or "tracer crashed"}).encode()
        except subprocess.TimeoutExpired:
            out = json.dumps({"steps": [], "error": f"Timed out after {TIMEOUT}s"}).encode()
        self.reply(200, out)

    def reply(self, status, out):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)
