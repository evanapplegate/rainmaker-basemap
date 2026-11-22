#!/usr/bin/env python3
"""ReliefKit server, stdlib only. http://localhost:8765"""
import json
import os
import subprocess
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import job as jobmod  # noqa: E402
from pipeline import util  # noqa: E402

JOBS = {}
FONTS_DIR = os.path.normpath(os.path.join(util.ROOT, "..", "fonts"))
WEB = os.path.join(util.ROOT, "web")
MIME = {".html": "text/html; charset=utf-8", ".otf": "font/otf",
        ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            return self._file(os.path.join(WEB, "index.html"))
        if p.startswith("/fonts/"):
            name = os.path.basename(p)
            return self._file(os.path.join(FONTS_DIR, name))
        if p.startswith("/api/jobs/"):
            jid = p.split("/")[3]
            st = JOBS.get(jid)
            if not st:
                return self._send(404, {"error": "no such job"})
            q = self.path.split("?")
            since = 0
            if len(q) > 1 and "since=" in q[1]:
                since = int(q[1].split("since=")[1].split("&")[0])
            return self._send(200, {
                "status": st["status"], "log": st["log"][since:], "n": len(st["log"]),
                "dir": (st["result"] or {}).get("dir"),
                "adobe": (st["result"] or {}).get("adobe")})
        self._send(404, {"error": "nope"})

    def do_POST(self):
        p = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if p == "/api/jobs":
            params = json.loads(raw)
            jid = uuid.uuid4().hex[:8]
            state = {"id": jid, "status": "running", "log": [], "result": None}
            JOBS[jid] = state

            def work():
                try:
                    state["result"] = jobmod.run_job(params, lambda m: state["log"].append(str(m)))
                    state["status"] = "done"
                except Exception as ex:
                    state["log"].append("ERROR: %s" % ex)
                    state["log"].append(traceback.format_exc()[-1500:])
                    state["status"] = "error"

            threading.Thread(target=work, daemon=True).start()
            return self._send(200, {"id": jid})
        if p.startswith("/api/jobs/") and p.endswith("/open"):
            jid = p.split("/")[3]
            st = JOBS.get(jid) or {}
            d = (st.get("result") or {}).get("dir")
            if d and os.path.isdir(d):
                if sys.platform == "darwin":
                    subprocess.Popen(["open", d])
                elif os.name == "nt":
                    os.startfile(d)  # noqa: S606
                return self._send(200, {"ok": True})
            return self._send(404, {"ok": False})
        self._send(404, {"error": "nope"})


if __name__ == "__main__":
    print("ReliefKit  ->  http://localhost:8765")
    ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
