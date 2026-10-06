"""Settings persistence test — saving brand settings must actually work.

The panel runs unprivileged (nucsub-web) while the install directory is
root-owned and deliberately not writable, so the atomic tmp+replace write used
to raise PermissionError and every save came back as an internal storage
error. This test covers:

  * save_settings() falling back to an in-place rewrite when the directory
    refuses the .tmp file (the exact production failure);
  * a negative control: the tmp-only writer really does fail, so the test
    catches the fallback disappearing rather than silently passing;
  * every accepted logo format over HTTP, with the type re-declared from the
    bytes instead of trusting the browser's file.type;
  * the 4 MiB logo cap, the matching request-size cap, and unsafe SVG;
  * the frontend, the CLI and the deploy scripts agreeing with the server.

Read-only against the real install: everything runs in a temp directory.
"""
import base64
import builtins
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "webpanel", "server.py")
INDEX = os.path.join(ROOT, "webpanel", "index.html")
CLI = os.path.join(ROOT, "cli", "nucsub")
HARDEN = os.path.join(ROOT, "tests", "t12_harden_deploy.sh")
LIVE = os.path.join(ROOT, "tests", "t12_live_verify.sh")
TOKEN = "t" * 48

fails = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name
          + (("  -- " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        fails.append(name)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# The in-place rewrite inside save_settings() -- the branch that runs when the
# install directory will not take a new file. The negative control below
# deletes exactly this text to rebuild the old, broken writer.
FALLBACK_BLOCK = """\
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
"""

# Tiny, real images. The server validates by magic bytes (that is its stated
# contract), so these are exactly what it inspects.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDw"
    "AEhQGAhKmMIQAAAABJRU5ErkJggg==")
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 8
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
WEBP = b"RIFF" + (20).to_bytes(4, "little") + b"WEBP" + b"VP8 " + b"\x00" * 16
SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">'
       b'<rect width="8" height="8" fill="#08f"/></svg>')
SVG_UNSAFE = (b'<svg xmlns="http://www.w3.org/2000/svg">'
              b'<script>alert(1)</script></svg>')

assert PNG[:8] == b"\x89PNG\r\n\x1a\n"
assert JPEG[:3] == b"\xff\xd8\xff"
assert GIF[:6] in (b"GIF87a", b"GIF89a")
assert WEBP[:4] == b"RIFF" and WEBP[8:12] == b"WEBP"


def data_url(raw, declared="image/png"):
    return "data:%s;base64,%s" % (declared, base64.b64encode(raw).decode("ascii"))


def blocked_tmp_open(real_open):
    """An open() that behaves like the hardened install: the directory is
    root-owned and will not accept a new .tmp file, while config.json itself
    stays writable by the panel."""
    def guarded(file, mode="r", *args, **kwargs):
        name = str(file)
        if name.endswith(".tmp") and any(c in mode for c in "wxa+"):
            raise PermissionError(13, "Permission denied")
        return real_open(file, mode, *args, **kwargs)
    return guarded


# ---------------------------------------------------------------- part 1
def test_save_fallback(tmp):
    print("-- save_settings() survives a read-only install directory")
    sys.path.insert(0, os.path.join(ROOT, "webpanel"))
    import server as srv

    cfg = os.path.join(tmp, "config.json")
    srv.SETTINGS_FILE = cfg
    srv.SETTINGS = {"brand_name": "NUC-SUB",
                    "telegram_channel": "https://t.me/nucsub1",
                    "brand_logo": data_url(PNG)}
    real_open = builtins.open
    builtins.open = blocked_tmp_open(real_open)
    try:
        srv.save_settings()
        err = None
    except OSError as e:
        err = e
    finally:
        builtins.open = real_open

    check("save_settings survives a directory that refuses .tmp", err is None, err)
    if err is not None:
        return
    with real_open(cfg, "r", encoding="utf-8") as f:
        stored = f.read()
    want = json.dumps(srv.SETTINGS, indent=2, ensure_ascii=False)
    check("settings landed in config.json", stored.strip() == want.strip(),
          stored[:120])
    check("no stray config.json.tmp is left behind",
          not os.path.exists(cfg + ".tmp"))


def test_negative_control(tmp):
    print("-- negative control: the old tmp-only writer")
    src = read(SERVER)
    check("the fallback block this test relies on is still in server.py",
          FALLBACK_BLOCK in src)
    if FALLBACK_BLOCK not in src:
        return

    # Rebuild save_settings() as it was before the fix: serialise, try the
    # atomic write, and have no second chance.
    broken = src.replace(FALLBACK_BLOCK,
                         "        raise PermissionError(13, 'Permission denied')\n", 1)
    ns = {"__name__": "srv_without_fallback"}
    exec(compile(broken, SERVER + " (without fallback)", "exec"), ns)
    ns["SETTINGS_FILE"] = os.path.join(tmp, "config-old.json")
    ns["SETTINGS"] = {"brand_name": "NUC-SUB"}

    real_open = builtins.open
    builtins.open = blocked_tmp_open(real_open)
    try:
        ns["save_settings"]()
        raised = False
    except OSError:
        raised = True
    finally:
        builtins.open = real_open
    check("the writer without the fallback raises (the bug being guarded)",
          raised)


# ---------------------------------------------------------------- part 2
def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def call(base, path, payload=None, token=TOKEN, timeout=60):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    r = urllib.request.Request(base + path, method="GET" if data is None else "POST",
                               data=data)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    try:
        body = json.loads(raw.decode("utf-8"))
    except ValueError:
        body = {"raw": raw[:300].decode("utf-8", "replace")}
    return status, body


def test_over_http(tmp):
    print("-- settings + logos over HTTP")
    port = free_port()
    base = "http://127.0.0.1:%d" % port
    proc = subprocess.Popen(
        [sys.executable, os.path.join(tmp, "webpanel", "server.py"),
         "--host", "127.0.0.1", "--port", str(port),
         "--base", os.path.join(tmp, "webpanel")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    up = False
    try:
        for _ in range(80):
            if proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                up = True
                break
            except urllib.error.HTTPError:
                up = True
                break
            except Exception:
                time.sleep(0.25)
        if not up:
            out = proc.communicate(timeout=10)[0]
            check("panel boots against a temp install dir", False, out[-400:])
            return

        code, res = call(base, "/api/settings")
        check("authenticated GET /api/settings -> 200", code == 200, res)
        check("the seeded brand name is readable",
              (res.get("settings") or {}).get("brand_name") == "NUC-SUB", res)

        # Formats. Every payload is DECLARED image/png -- the guess a browser
        # makes when it does not know the file -- so this checks acceptance of
        # the format and the re-declaration from the bytes in one pass.
        last = ""
        for label, raw, mime in (("PNG", PNG, "image/png"),
                                 ("JPEG", JPEG, "image/jpeg"),
                                 ("GIF", GIF, "image/gif"),
                                 ("WEBP", WEBP, "image/webp"),
                                 ("SVG", SVG, "image/svg+xml")):
            code, res = call(base, "/api/settings", {"brand_logo": data_url(raw)})
            check("%s logo accepted (HTTP %d)" % (label, code), code == 200, res)
            last = (res.get("settings") or {}).get("brand_logo", "")
            check("%s stored with the type from its own bytes" % label,
                  last.startswith("data:%s;base64," % mime), last[:70])

        code, res = call(base, "/api/settings")
        check("the saved logo survives a re-read",
              (res.get("settings") or {}).get("brand_logo") == last,
              (res.get("settings") or {}).get("brand_logo", "")[:70])

        # The real form: every field at once, the way the panel sends it.
        combo = {"brand_name": "NUC-SUB",
                 "telegram_channel": "https://t.me/nucsub1",
                 "brand_logo": data_url(SVG)}
        code, res = call(base, "/api/settings", combo)
        check("brand + telegram + logo save together -> 200", code == 200, res)
        check("save reports ok", res.get("ok") is True, res)
        on_disk = json.loads(read(os.path.join(tmp, "config.json")))
        check("all three fields persisted to config.json",
              on_disk.get("brand_name") == "NUC-SUB"
              and on_disk.get("telegram_channel") == "https://t.me/nucsub1"
              and on_disk.get("brand_logo", "").startswith("data:image/svg+xml;base64,"),
              on_disk)

        # Rejections: precise errors, not a 500 and not a silent accept.
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (4 * 1048576)
        code, res = call(base, "/api/settings", {"brand_logo": data_url(big)})
        check("a 4 MiB+1 image is refused as too large",
              code == 400 and res.get("error") == "brand_logo_too_large",
              "%s %s" % (code, res))

        code, res = call(base, "/api/settings", {"brand_logo": "A" * 6_000_010})
        check("a body over the request cap is refused with 413",
              code == 413 and res.get("error") == "payload_too_large",
              "%s %s" % (code, res))

        code, res = call(base, "/api/settings", {"brand_logo": data_url(SVG_UNSAFE)})
        check("an SVG carrying a script is refused",
              code == 400 and res.get("error") == "brand_logo_svg_unsafe",
              "%s %s" % (code, res))

        code, res = call(base, "/api/settings",
                         {"brand_logo": "data:image/png;base64,@@not-base64@@"})
        check("a malformed data URL is refused",
              code == 400 and res.get("error") == "brand_logo_invalid",
              "%s %s" % (code, res))

        code, res = call(base, "/api/settings",
                         {"brand_logo": data_url(b"definitely not an image")})
        check("non-image bytes are refused",
              code == 400 and res.get("error") == "brand_logo_not_image",
              "%s %s" % (code, res))

        # The save that used to fail must not have broken anything else.
        on_disk = json.loads(read(os.path.join(tmp, "config.json")))
        check("earlier settings are still intact after the refusals",
              on_disk.get("brand_name") == "NUC-SUB"
              and on_disk.get("telegram_channel") == "https://t.me/nucsub1",
              on_disk)
    finally:
        try:
            proc.terminate()
            out = proc.communicate(timeout=10)[0]
        except Exception:
            proc.kill()
            out = ""
        if fails:
            print("    server said: %s" % (out or "").strip()[-400:])


# ---------------------------------------------------------------- part 3
def test_contracts():
    print("-- the frontend, the CLI and the deploy scripts agree")
    server_src = read(SERVER)
    check("server logo cap is 4 MiB", "MAX_LOGO_BYTES = 4_194_304" in server_src)
    check("server body cap leaves room for it", "MAX_POST_BODY = 6_000_000" in server_src)

    cli = read(CLI)
    check("CLI file-import cap is 4 MiB", "-gt 4194304" in cli)
    check("CLI data-URL cap matches", "-le 5600000" in cli)
    check("CLI has no 1 MiB logo cap left",
          "1050000" not in cli and "larger than the 1 MiB limit" not in cli)

    html = read(INDEX)
    check("frontend file gate is 4 MiB", "f.size>4*1048576" in html)
    check("frontend editor gate is 4 MiB", "<=4*1048576" in html)
    check("frontend builds the data URL from sniffed bytes",
          "data:'+mime+';base64,'+btoa(" in html)
    check("frontend states the 4 MiB limit",
          "۴ مگابایت" in html and "4 MiB" in html)

    harden = read(HARDEN)
    check("a fresh install creates config.json for the panel",
          "config.json" in harden and "printf '{}\\n' >" in harden)
    check("hardening refuses to run if the panel cannot save",
          "every settings save would fail" in harden)

    live = read(LIVE)
    check("live verification round-trips a settings save",
          "settings save returns 200" in live)
    check("live verification checks the config is writable",
          "can write config.json" in live)
    check("live verification keeps the install tree read-only",
          "install tree stays read-only" in live)


def main():
    tmp = tempfile.mkdtemp(prefix="t21settings")
    try:
        os.makedirs(os.path.join(tmp, "webpanel"), exist_ok=True)
        shutil.copy(SERVER, os.path.join(tmp, "webpanel", "server.py"))
        with open(os.path.join(tmp, ".webpanel-token"), "w", encoding="utf-8") as f:
            f.write(TOKEN)
        os.chmod(os.path.join(tmp, ".webpanel-token"), 0o600)
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"brand_name": "NUC-SUB"}, f, indent=2)

        test_save_fallback(tmp)
        test_negative_control(tmp)
        test_over_http(tmp)
        test_contracts()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d checks failed" % len(fails))
    if fails:
        for f in fails:
            print("  FAIL " + f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
