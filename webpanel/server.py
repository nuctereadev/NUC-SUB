#!/usr/bin/env python3
"""
NUC-SUB web panel — ultra-lightweight web panel for nucsub (3x-ui / Pasarguard theme engine).

A dependency-free Python3 stdlib HTTP server that:
  * serves the static SPA in --base (index.html, app.js, style.css)
  * guards every /api/* route with a bearer token (query ?token= or header)
  * shells out to the nucsub script for privileged actions
  * manages per-install settings (telegram channel, brand name, brand logo)
    via config.json — the SAME single source of truth the CLI uses

Usage:
  python3 server.py --port 8080 --token <tok> --base <webpanel>
                   --cli <path/to/nucsub> --themes <themesDir> --db <xui.db>
"""
import argparse
import base64
import hmac
import json
import logging
import mimetypes
import os
import re
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ARGS = None
HOST_PORT = 8080
SETTINGS = {}
SETTINGS_FILE = ""
INSTALL_DIR = ""

LOG = logging.getLogger("nuc-sub-webpanel")

# ---------------------------------------------------------------------------
# Settings persistence (config.json in install dir — shared with the CLI)
# ---------------------------------------------------------------------------
SAFE_SETTINGS_KEYS = {"telegram_channel", "brand_name", "brand_logo"}
BRAND_NAME_MAX = 30
MAX_LOGO_BYTES = 1_048_576            # 1 MiB of decoded image payload
MAX_POST_BODY = 2_400_000             # room for base64(1 MiB) + other fields
TELEGRAM_RE = re.compile(r"^https://t\.me/[A-Za-z0-9_]{5,}$")
# brand name is injected into a single-quoted JS string in themes, and rendered
# via textContent — so no quotes/backslashes/control characters are allowed.
BRAND_NAME_BAD = re.compile(r"['\"\\\x00-\x1f]")

if mimetypes.guess_type("x.woff2")[0] is None:
    mimetypes.add_type("font/woff2", ".woff2")

def _log(msg, *args):
    LOG.warning("[nuc-sub] %s", msg % args if args else msg)

def _settings_path():
    return SETTINGS_FILE

def load_settings():
    global SETTINGS
    path = _settings_path()
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                SETTINGS = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
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
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(SETTINGS, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o600)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def sniff_image_bytes(raw):
    """Return the real image MIME from magic bytes, or '' if none match."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return ""

ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

def validate_logo_data_url(value):
    """Validate a data:image/...;base64,... logo URL. Returns (ok, err_index, raw_len)."""
    if not value:
        return True, "", 0
    if not value.startswith("data:image/"):
        return False, "invalid", len(value)
    m = re.match(r"^data:(image/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=\r\n]+)$", value)
    if not m:
        return False, "invalid", len(value)
    declared, b64part = m.group(1), m.group(2)
    try:
        raw = base64.b64decode(b64part, validate=True)
    except Exception:  # noqa: BLE001
        return False, "invalid", len(value)
    if not raw:
        return False, "invalid", 0
    if len(raw) > MAX_LOGO_BYTES:
        return False, "too_large", len(raw)
    real = sniff_image_bytes(raw)
    if not real:
        return False, "not_image", len(raw)
    if declared not in ALLOWED_IMAGE_MIMES or declared != real:
        return False, "mime_mismatch", len(raw)
    return True, "", len(raw)

def is_valid_url(url):
    """Basic URL validation for telegram channel."""
    if not url:
        return True  # empty is allowed (clears)
    return bool(TELEGRAM_RE.match(url.strip()))

def is_valid_theme_name(name):
    """Reject anything not a safe bare identifier."""
    return bool(re.match(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$', name))

# ---------------------------------------------------------------------------
# CLI helper
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
        _log("cli %s raised: %r", args, e)
        return {"ok": False, "code": -1, "stdout": "", "stderr": str(e)}

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
    server_version = "nuc-sub-webpanel/2.2.0"

    def log_message(self, *a):
        pass

    # -- auth ---------------------------------------------------------------
    def _authorized(self, qs):
        if not ARGS.token:
            return True
        auth = self.headers.get("Authorization", "")
        if hmac.compare_digest(auth[:7], "Bearer ") and hmac.compare_digest(auth[7:], ARGS.token):
            return True
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
            out = run_cli(["status"])
            out["port"] = HOST_PORT
            self._send_json(out)
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

        if action == "settings":
            if self.command == "POST":
                self._handle_settings_post()
            else:
                # Single source of truth = the shared config.json. Re-read it on
                # every GET so values changed by the CLI (or another process)
                # show up live instead of a stale in-memory snapshot.
                load_settings()
                self._send_json({"ok": True, "settings": dict(SETTINGS)})
            return

        self._send_json({"error": "unknown api"}, 404)

    def _handle_settings_post(self):
        """Handle POST /api/settings — atomically persists shared settings.

        Logs real failure causes to stderr (debug), returns only sanitized
        codes/messages to the client, and keeps the saved values as the single
        source of truth. A theme refresh is *requested* afterwards but a CLI
        hiccup never fails the save itself."""
        content_len = int(self.headers.get("Content-Length", 0) or 0)
        if content_len > MAX_POST_BODY:
            _log("settings POST rejected: payload %dB > %dB", content_len, MAX_POST_BODY)
            self._send_json({"error": "payload_too_large"}, 413)
            return
        if content_len < 1:
            self._send_json({"error": "empty_body"}, 400)
            return
        body = self.rfile.read(content_len)
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            _log("settings POST invalid JSON: %r", e)
            self._send_json({"error": "invalid_json"}, 400)
            return
        if not isinstance(data, dict):
            self._send_json({"error": "expected_object"}, 400)
            return

        # Base the merge on the CURRENT on-disk state, never on a possibly
        # stale in-memory copy: the CLI writes the same config.json, so a panel
        # save must never roll back a value the CLI changed meanwhile.
        load_settings()

        remove_logo = data.get("remove_logo") is True
        remove_tg = data.get("remove_telegram") is True
        updated = {}
        for k, v in data.items():
            if k not in SAFE_SETTINGS_KEYS:
                continue
            if k == "telegram_channel":
                v = str(v).strip()
                if not v:
                    # empty = no change UNLESS removal was explicitly requested
                    if remove_tg:
                        _log("settings POST: removed telegram_channel")
                        SETTINGS[k] = ""
                        updated[k] = ""
                    continue
                if not is_valid_url(v):
                    _log("settings POST rejected telegram_channel: %r", v[:200])
                    self._send_json({"error": "invalid_telegram_url"}, 400)
                    return
                SETTINGS[k] = v
                updated[k] = v
            elif k == "brand_name":
                v = str(v).strip()
                if not v:
                    continue  # empty = no change
                if len(v) > BRAND_NAME_MAX:
                    _log("settings POST rejected brand_name: %d chars (max %d)",
                         len(v), BRAND_NAME_MAX)
                    self._send_json({"error": "brand_name_too_long"}, 400)
                    return
                if BRAND_NAME_BAD.search(v):
                    _log("settings POST rejected brand_name: invalid characters")
                    self._send_json({"error": "brand_name_invalid"}, 400)
                    return
                SETTINGS[k] = v
                updated[k] = v
            elif k == "brand_logo":
                v = str(v).strip()
                if not v:
                    # empty logo = no change UNLESS removal was explicitly requested
                    if remove_logo:
                        SETTINGS[k] = ""
                        updated[k] = ""
                    continue
                ok, err, rawlen = validate_logo_data_url(v)
                if not ok:
                    _log("settings POST rejected brand_logo (%s): %d bytes", err, rawlen)
                    self._send_json({"error": "brand_logo_" + err}, 400)
                    return
                SETTINGS[k] = v
                updated[k] = v

        try:
            save_settings()
        except OSError as e:
            _log("settings POST save failed: %r", e)
            self._send_json({"error": "save_failed"}, 500)
            return

        # One shared re-sync: the CLI reads the same config.json, so a single
        # `refresh` is enough (no per-field CLI writes that could drift).
        warn = None
        if updated:
            res = run_cli(["refresh"])
            if not res["ok"]:
                _log("refresh after save failed: %r", res)
                warn = "theme_refresh_failed"

        self._send_json({"ok": True, "settings": dict(SETTINGS), "updated": updated,
                         "warn": warn})

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


def _resolve_install_dir(base):
    """The install dir is the directory that CONTAINS the webpanel dir.

    (e.g. /opt/nuc-sub when base is /opt/nuc-sub/webpanel) — fall back to the
    base dir itself when base points straight at the install dir."""
    base = os.path.realpath(base)
    if os.path.basename(base) == "webpanel":
        return os.path.dirname(base)
    if os.path.isfile(os.path.join(base, "config.json")):
        return base
    return os.path.dirname(base)


class _ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _bind_with_retry(port, attempts=20, delay=0.5):
    """Bind the requested port, tolerating a restart race.

    On `systemctl restart` the outgoing process can still hold the port for a
    moment, which used to make the panel permanently drift to the next free
    port on every restart. Retry briefly so the panel keeps a stable URL.
    Returns a bound server, or None if the port is taken by something else."""
    last = None
    for _ in range(max(1, attempts)):
        try:
            return _ReusableServer(("0.0.0.0", port), Handler)
        except OSError as e:
            last = e
            time.sleep(delay)
    if last:
        _log("port %d still busy after retries: %r", port, last)
    return None


def main():
    global ARGS, SETTINGS_FILE, HOST_PORT, INSTALL_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--token")
    ap.add_argument("--base", default=".")
    ap.add_argument("--cli", default="")
    ap.add_argument("--themes")
    ap.add_argument("--db")
    ARGS = ap.parse_args()

    INSTALL_DIR = _resolve_install_dir(ARGS.base)
    if not ARGS.cli:
        ARGS.cli = os.path.join(INSTALL_DIR, "cli", "nucsub")

    # config.json sits beside the CLI install — the SAME file the CLI reads.
    SETTINGS_FILE = os.path.join(INSTALL_DIR, "config.json")

    # Migrate any legacy settings that used to land one level up (fixes the
    # historical split where CLI+webpanel wrote different files).
    legacy = os.path.join(os.path.dirname(INSTALL_DIR.rstrip(os.sep)) or os.sep,
                          "config.json")
    if (not os.path.isfile(SETTINGS_FILE)
            and os.path.isfile(legacy)
            and os.path.dirname(legacy) != INSTALL_DIR):
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.chmod(SETTINGS_FILE, 0o600)
            _log("migrated legacy settings from %s", legacy)
        except Exception as e:  # noqa: BLE001
            _log("legacy migration skipped: %r", e)

    load_settings()

    HOST_PORT = ARGS.port
    srv = _bind_with_retry(ARGS.port)
    if srv is None:
        # The requested port is genuinely taken by another service — move on.
        port = find_free_port(ARGS.port + 1, ARGS.port + 100)
        print(f"[nuc-sub] ⚠ port {ARGS.port} is occupied — web panel will use port {port}", flush=True)
        HOST_PORT = port
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    else:
        port = srv.server_address[1]

    # Persist the effective port so the CLI/menus report the real running port.
    try:
        with open(os.path.join(INSTALL_DIR, ".webport"), "w") as f:
            f.write(str(port))
    except OSError:
        pass

    print(f"[nuc-sub] web panel listening on http://0.0.0.0:{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()