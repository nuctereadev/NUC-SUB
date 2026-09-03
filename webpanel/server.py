#!/usr/bin/env python3
"""
NUC-SUB web panel — ultra-lightweight web panel for nucsub (3x-ui theme engine).

A dependency-free Python3 stdlib HTTP server that:
  * serves the static SPA in --base (index.html, app.js, style.css)
  * guards every /api/* route with a bearer token (query ?token= or header)
  * shells out to the nucsub script for privileged actions

Usage:
  python3 server.py --port 8080 --token <tok> --base <webpanel>
                   --cli <path/to/nucsub> --themes <themesDir> --db <xui.db>
"""
import argparse
import hmac
import json
import mimetypes
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ARGS = None

if mimetypes.guess_type("x.woff2")[0] is None:
    mimetypes.add_type("font/woff2", ".woff2")


def run_cli(args, input_data=None):
    try:
        out = subprocess.run(
            [ARGS.cli] + args, capture_output=True, text=True, timeout=60,
            input=input_data, shell=False,
        )
        return {
            "ok": out.returncode == 0,
            "code": out.returncode,
            "stdout": out.stdout or "",
            "stderr": out.stderr or "",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "code": -1, "stdout": "", "stderr": str(e)}


class Handler(BaseHTTPRequestHandler):
    server_version = "nuc-sub-webpanel/2.0.0"

    def log_message(self, *a):
        pass

    # -- routing ---------------------------------------------------------
    def _authorized(self, qs):
        if not ARGS.token:
            return True
        # header:  Authorization: Bearer <tok>
        auth = self.headers.get("Authorization", "")
        if hmac.compare_digest(auth[:7], "Bearer ") and hmac.compare_digest(auth[7:], ARGS.token):
            return True
        # cookie:  token=<tok>  OR  query:  ?token=<tok>
        cookie = self.headers.get("Cookie", "")
        if parser := self._cookie_token(cookie):
            return parser
        q = parse_qs(qs)
        if q.get("token", [None])[0] is not None and hmac.compare_digest(q["token"][0], ARGS.token):
            return True
        return False

    @staticmethod
    def _cookie_token(cookie):
        # cookie:  token=<tok>
        tok = ARGS.token
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("token="):
                return hmac.compare_digest(part[6:], tok)
        return False

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, rel):
        # prevent directory traversal AND symlink escape
        base = os.path.realpath(ARGS.base)
        full = os.path.realpath(os.path.join(base, rel.lstrip("/")))
        if not full.startswith(base + os.sep) and full != base:
            self._send_json({"error": "forbidden"}, 403)
            return
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            self._send_json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, path, qs):
        if path.startswith("/api/"):
            if not self._authorized(qs):
                self._send_json({"error": "unauthorized", "token_required": True}, 401)
                return
            return self._api(path, parse_qs(qs))
        self._send_file(path or "/")

    # -- api -------------------------------------------------------------
    def _api(self, path, q):
        seg = path.rstrip("/").split("/")
        # /api/status  /api/list  /api/reset  /api/apply  /api/remove  /api/themes(json)
        action = seg[-1]
        if action == "status":
            r = run_cli(["status"])
            self._send_json(r)
            return
        if action == "list":
            r = run_cli(["list"])
            self._send_json(r)
            return
        if action == "reset":
            r = run_cli(["reset"])
            self._send_json(r)
            return
        if action == "apply":
            name = (q.get("name") or [""])[0]
            if not name:
                self._send_json({"error": "missing name"}, 400)
                return
            r = run_cli(["apply", name])
            self._send_json(r)
            return
        if action == "remove":
            name = (q.get("name") or [""])[0]
            if not name:
                self._send_json({"error": "missing name"}, 400)
                return
            r = run_cli(["remove", name])
            self._send_json(r)
            return
        if action == "preview":
            name = (q.get("name") or [""])[0]
            if not name:
                self._send_json({"error": "missing name"}, 400)
                return
            r = run_cli(["preview", name, "--json"])
            self._send_json(r)
            return
        self._send_json({"error": "unknown api"}, 404)

    def do_GET(self):
        u = urlparse(self.path)
        self._dispatch(u.path, u.query)

    def do_POST(self):
        self.do_GET()

    # -- misc ------------------------------------------------------------
    def send_error(self, code, message=None, explain=None):
        if code in (404, 403, 401):
            self._send_json({"error": message or str(code)}, code)
            return
        super().send_error(code, message, explain)


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--token")
    ap.add_argument("--base", default=".")
    ap.add_argument("--cli", default="/opt/nuc-sub/cli/nucsub")
    ap.add_argument("--themes")
    ap.add_argument("--db")
    ap.add_argument("--ext-json", action="store_true",
                    help="expose /api/info returning raw ?format=info JSON from the panel")
    ARGS = ap.parse_args()

    srv = ThreadingHTTPServer(("0.0.0.0", ARGS.port), Handler)
    print(f"NUC-SUB web panel listening on :{ARGS.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
