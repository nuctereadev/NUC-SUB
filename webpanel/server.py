#!/usr/bin/env python3
"""
NUC-SUB web panel — ultra-lightweight web panel for nucsub (3x-ui theme engine).

A dependency-free Python3 stdlib HTTP server that:
  * serves the static SPA in --base (index.html, app.js, style.css)
  * guards every /api/* route with a bearer token (query ?token= or header)
  * shells out to the nucsub script for privileged actions
  * manages per-install settings (telegram channel, etc.) via config.json

Usage:
  python3 server.py --port 8080 --token <tok> --base <webpanel>
                   --cli <path/to/nucsub> --themes <themesDir> --db <xui.db>
"""
import argparse
import fcntl
import hmac
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ARGS = None
SETTINGS = {}
SETTINGS_FILE = ""

if mimetypes.guess_type("x.woff2")[0] is None:
    mimetypes.add_type("font/woff2", ".woff2")

# ---------------------------------------------------------------------------
# Settings persistence (config.json in install dir)
# ---------------------------------------------------------------------------
SAFE_SETTINGS_KEYS = {"telegram_channel"}

def _settings_path():
    return SETTINGS_FILE

def load_settings():
    global SETTINGS
    path = _settings_path()
    if path and os.path.isfile(path):
        try:
            with open(path, "r") as f:
                SETTINGS = json.load(f)
        except (json.JSONDecodeError, OSError):
            SETTINGS = {}
    else:
        SETTINGS = {}

def save_settings():
    path = _settings_path()
    if not path:
        return
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(SETTINGS, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o600)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run_cli(args, input_data=None):
    """Run nucsub CLI and return structured result. Validates args for safety."""
    if not os.path.isfile(ARGS.cli):
        return {"ok": False, "code": -1, "stdout": "", "stderr": "nucsub not found"}
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

def is_valid_theme_name(name):
    """Reject anything not a safe bare identifier."""
    return bool(re.match(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$', name))

def is_valid_url(url):
    """Basic URL validation for telegram channel."""
    if not url:
        return True  # empty is allowed (clears)
    return bool(re.match(r'^https://t\.me/[A-Za-z0-9_]{5,}$', url.strip()))

def find_free_port(start=8080, end=9999):
    """Find a free TCP port in range [start, end)."""
    for port in range(start, end):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.close()
            return port
        except OSError:
            continue
    return start  # fallback

# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "nuc-sub-webpanel/2.1.0"

    def log_message(self, *a):
        pass

    # -- auth ---------------------------------------------------------------
    def _authorized(self, qs):
        if not ARGS.token:
            return True
        # header:  Authorization: Bearer <tok>
        auth = self.headers.get("Authorization", "")
        if hmac.compare_digest(auth[:7], "Bearer ") and hmac.compare_digest(auth[7:], ARGS.token):
            return True
        # cookie:  token=<tok>  OR  query:  ?token=<tok>
        cookie = self.headers.get("Cookie", "")
        if self._cookie_token(cookie):
            return True
        q = parse_qs(qs)
        qt = q.get("token", [None])[0]
        if qt is not None and hmac.compare_digest(qt, ARGS.token):
            return True
        return False

    def _cookie_token(self, cookie):
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("token="):
                return hmac.compare_digest(part[6:], ARGS.token)
        return False

    # -- responses ----------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, rel):
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

    # -- routing ------------------------------------------------------------
    def _dispatch(self, path, qs):
        if path.startswith("/api/"):
            if not self._authorized(qs):
                self._send_json({"error": "unauthorized", "token_required": True}, 401)
                return
            return self._api(path, parse_qs(qs))
        self._send_file(path or "/")

    # -- api ----------------------------------------------------------------
    def _api(self, path, q):
        seg = path.rstrip("/").split("/")
        action = seg[-1]

        if action == "status":
            self._send_json(run_cli(["status"]))
            return

        if action == "list":
            self._send_json(run_cli(["list"]))
            return

        if action == "reset":
            self._send_json(run_cli(["reset"]))
            return

        if action == "apply":
            name = (q.get("name") or [""])[0]
            if not name or not is_valid_theme_name(name):
                self._send_json({"error": "invalid or missing name"}, 400)
                return
            self._send_json(run_cli(["apply", name]))
            return

        if action == "remove":
            name = (q.get("name") or [""])[0]
            if not name or not is_valid_theme_name(name):
                self._send_json({"error": "invalid or missing name"}, 400)
                return
            self._send_json(run_cli(["remove", name]))
            return

        if action == "preview":
            name = (q.get("name") or [""])[0]
            if not name or not is_valid_theme_name(name):
                self._send_json({"error": "invalid or missing name"}, 400)
                return
            self._send_json(run_cli(["preview", name, "--json"]))
            return

        if action == "settings":
            if self.command == "POST":
                self._handle_settings_post()
            else:
                self._send_json({"ok": True, "settings": SETTINGS})
            return

        self._send_json({"error": "unknown api"}, 404)

    def _handle_settings_post(self):
        """Handle POST /api/settings — update settings dict."""
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 4096:
            self._send_json({"error": "payload too large"}, 413)
            return
        body = self.rfile.read(content_len)
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._send_json({"error": "invalid json"}, 400)
            return
        if not isinstance(data, dict):
            self._send_json({"error": "expected object"}, 400)
            return

        updated = {}
        for k, v in data.items():
            if k not in SAFE_SETTINGS_KEYS:
                continue
            if k == "telegram_channel":
                v = str(v).strip()
                if v and not is_valid_url(v):
                    self._send_json({"error": "invalid telegram URL (must be https://t.me/username)"}, 400)
                    return
                SETTINGS[k] = v
                updated[k] = v
            else:
                SETTINGS[k] = v
                updated[k] = v

        save_settings()
        self._send_json({"ok": True, "settings": SETTINGS, "updated": updated})

    # -- HTTP methods -------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        self._dispatch(u.path, u.query)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/"):
            if not self._authorized(u.query):
                self._send_json({"error": "unauthorized", "token_required": True}, 401)
                return
            return self._api(u.path, parse_qs(u.query))
        self._send_json({"error": "method not allowed"}, 405)

    def send_error(self, code, message=None, explain=None):
        if code in (404, 403, 401):
            self._send_json({"error": message or str(code)}, code)
            return
        super().send_error(code, message, explain)


def main():
    global ARGS, SETTINGS_FILE
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

    # Load settings from config.json (sibling to --base or in install dir)
    install_dir = os.path.dirname(os.path.dirname(os.path.realpath(ARGS.base)))
    SETTINGS_FILE = os.path.join(install_dir, "config.json")
    load_settings()

    # Find a free port if the requested one is occupied
    port = ARGS.port
    test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        test.bind(("0.0.0.0", port))
    except OSError:
        port = find_free_port(port + 1, port + 100)
        print(f"⚠ Port {ARGS.port} occupied — using port {port} instead", flush=True)
    finally:
        test.close()

    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"NUC-SUB web panel listening on :{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
