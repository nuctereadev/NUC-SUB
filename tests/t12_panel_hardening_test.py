"""Task 12 regression test — web panel hardening.

Boots server.py on an ephemeral port against a temp install dir and asserts
the security fixes behave as intended. Read-only against the real install.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "webpanel", "server.py")
TOKEN = "t" * 48

fails = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  -- " + detail) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def req(url, method="GET", token=None, body=None, ctype=None, extra=None):
    r = urllib.request.Request(url, method=method, data=body)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if ctype:
        r.add_header("Content-Type", ctype)
    for k, v in (extra or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def main():
    tmp = tempfile.mkdtemp(prefix="t12panel")
    os.makedirs(os.path.join(tmp, "webpanel"), exist_ok=True)
    shutil.copy(SERVER, os.path.join(tmp, "webpanel", "server.py"))
    shutil.copy(os.path.join(ROOT, "webpanel", "index.html"),
                os.path.join(tmp, "webpanel", "index.html"))
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"brand_name": "NUC-SUB"}, f)
    with open(os.path.join(tmp, ".webpanel-token"), "w", encoding="utf-8") as f:
        f.write(TOKEN)
    os.chmod(os.path.join(tmp, ".webpanel-token"), 0o600)

    port = 18711
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(tmp, "webpanel", "server.py"),
         "--port", str(port), "--base", os.path.join(tmp, "webpanel")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.25)
        else:
            print("FAIL  panel did not start")
            return 1

        # --- auth ---------------------------------------------------------
        s, h, _ = req(base + "/api/status")
        check("API rejects missing token (401)", s == 401, "got %s" % s)
        s, _, _ = req(base + "/api/status", token="wrong" * 12)
        check("API rejects bad token (401)", s == 401, "got %s" % s)
        s, _, _ = req(base + "/api/status", token=TOKEN)
        check("API accepts valid token (200)", s == 200, "got %s" % s)

        # --- FIX: token must NOT be accepted via query string --------------
        s, _, _ = req(base + "/api/status?token=" + TOKEN)
        check("token in query string is rejected", s == 401, "got %s" % s)
        s, _, _ = req(base + "/api/status", extra={"Cookie": "token=" + TOKEN})
        check("token in cookie still accepted (documented path)", s == 200, "got %s" % s)

        # --- FIX: security headers ----------------------------------------
        s, h, _ = req(base + "/")
        csp = h.get("Content-Security-Policy", "")
        check("CSP present on static file", "default-src 'self'" in csp, csp)
        check("CSP has object-src 'none'", "object-src 'none'" in csp, csp)
        check("CSP has base-uri 'none'", "base-uri 'none'" in csp, csp)
        check("CSP has frame-ancestors 'none'", "frame-ancestors 'none'" in csp, csp)
        check("Referrer-Policy is no-referrer",
              h.get("Referrer-Policy") == "no-referrer", h.get("Referrer-Policy"))
        check("HSTS present", "max-age" in h.get("Strict-Transport-Security", ""),
              h.get("Strict-Transport-Security"))
        check("X-Frame-Options DENY", h.get("X-Frame-Options") == "DENY")
        check("no-store cache header", h.get("Cache-Control") == "no-store")

        s, h, _ = req(base + "/api/status", token=TOKEN)
        check("security headers also on JSON responses",
              "default-src 'self'" in h.get("Content-Security-Policy", ""))

        # --- FIX: no Python version disclosure ----------------------------
        s, h, _ = req(base + "/")
        srv = h.get("Server", "")
        check("Server header hides Python version", "Python" not in srv, srv)
        check("Server header keeps product name", "nuc-sub-webpanel" in srv, srv)

        # --- FIX: HEAD works instead of 501 -------------------------------
        s, h, _ = req(base + "/", method="HEAD")
        check("HEAD on static file returns 200", s == 200, "got %s" % s)
        s, _, _ = req(base + "/api/status", method="HEAD", token=TOKEN)
        check("HEAD on API does not serve a body (4xx, not 200)",
              400 <= s < 500, "got %s" % s)

        # --- FIX: settings POST requires application/json ------------------
        payload = json.dumps({"brand_name": "NUC-SUB"}).encode()
        s, _, _ = req(base + "/api/settings", method="POST", token=TOKEN,
                      body=payload, ctype="text/plain")
        check("settings POST without JSON content-type is 415", s == 415, "got %s" % s)
        s, _, _ = req(base + "/api/settings", method="POST", token=TOKEN,
                      body=payload, ctype="application/json; charset=utf-8")
        check("settings POST with JSON content-type accepted", s == 200, "got %s" % s)

        # --- FIX: malformed Content-Length must not 500 --------------------
        r = urllib.request.Request(base + "/api/settings", method="POST", data=payload)
        r.add_header("Authorization", "Bearer " + TOKEN)
        r.add_header("Content-Type", "application/json")
        r.add_header("Content-Length", "not-a-number")
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                s = resp.status
        except urllib.error.HTTPError as e:
            s = e.code
        except Exception:
            s = 500
        check("malformed Content-Length handled (not a crash)", s in (400, 411, 413), "got %s" % s)

        # --- path traversal still blocked ----------------------------------
        s, _, _ = req(base + "/../config.json")
        check("path traversal blocked", s in (403, 404), "got %s" % s)
        s, _, _ = req(base + "/%2e%2e/%2e%2e/etc/passwd")
        check("encoded path traversal blocked", s in (403, 404), "got %s" % s)

        # --- public bind + token as the gate --------------------------------
        out = subprocess.run(
            [sys.executable, os.path.join(tmp, "webpanel", "server.py"), "--help"],
            capture_output=True, text=True, timeout=20)
        check("--host flag exists", "--host" in out.stdout, out.stdout[:200])
        ssrc = open(SERVER, encoding="utf-8").read()
        check("default host is every interface",
              'os.environ.get("NUC_SUB_WEB_HOST", "0.0.0.0")' in ssrc)
        check("loopback is still reachable as an explicit opt-in",
              'NUC_SUB_WEB_HOST=127.0.0.1' in ssrc)
        check("source does not hardcode the bind past the flag default",
              'ThreadingHTTPServer(("0.0.0.0"' not in ssrc)
# A public bind is only defensible because these hold. Assert them here
        # so flipping the default can never quietly become "open to everyone".
        # Each is anchored to the code that enforces it: a bare "return False
        # appears somewhere" check passes even when the guard itself is flipped.
        failclosed = re.search(r"if not expected:(.*?)return (True|False)", ssrc, re.S)
        check("auth fails closed when no usable token exists",
              failclosed is not None and failclosed.group(2) == "False",
              "the missing-token path does not return False")
        check("auth compares the token with a constant-time compare",
              "hmac.compare_digest" in ssrc)
        # parse_qs is legitimately used for other API parameters, so the real
        # invariant is narrower: the token must be read only from the
        # Authorization header or the cookie, never from the query string.
        m = re.search(r"def _authorized\(self\):(.*?)\n    def ", ssrc, re.S)
        auth_body = m.group(1) if m else ""
        # the body documents *why* the query form is rejected, so match code
        # lines only -- otherwise the explanation trips its own assertion
        auth_code = "\n".join(ln for ln in auth_body.splitlines()
                              if ln.strip() and not ln.strip().startswith("#"))
        check("token is read from the Authorization header",
              'self.headers.get("Authorization"' in auth_code, auth_code[:160])
        check("token is read from the cookie",
              'self.headers.get("Cookie"' in auth_code)
        check("token is never read from the query string",
              bool(auth_code) and not re.search(r"\b(qs|query|parse_qs)\b",
                                                auth_code),
              "the auth path touches the query string")
        check("the CLI defaults the bind to public too",
              "${NUC_SUB_WEB_HOST:-0.0.0.0}" in
              open(os.path.join(ROOT, "cli", "nucsub"), encoding="utf-8").read())

        # --- privilege separation wiring -----------------------------------
        src = open(SERVER, encoding="utf-8").read()
        check("run_cli escalates via sudo when unprivileged",
              '"sudo", "-n", ARGS.cli' in src)
        check("run_cli never uses a shell", "shell=True" not in src)

        # --- frontend regressions ------------------------------------------
        html = open(os.path.join(ROOT, "webpanel", "index.html"), encoding="utf-8").read()
        check("showToast no longer assigns innerHTML with message",
              "t.innerHTML=(err?" not in html)
        check("statusbar escapes the active theme name",
              "${esc(active||t('status.value.default'))}" in html)
        check("reset is called with POST", "api('reset',{method:'POST'})" in html)
        check("external links are noreferrer", 'rel="noopener noreferrer"' in html
              and 'rel="noopener"' not in html)
        check("no ?token= usage left in frontend", "token=" not in html.split("I18N")[-1]
              or "?token=" not in html)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if fails:
        print("%d FAILED: %s" % (len(fails), ", ".join(fails)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
