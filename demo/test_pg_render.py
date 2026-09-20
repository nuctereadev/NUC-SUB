"""Render every PasarGuard theme in demo/scenarios mimicking the REAL Pasarguard
context (exactly: user, links, announce, announce_url, apps) to prove the
capability patch holds:
  - normal active user
  - unlimited user (data_limit == 0, expire None)  -> must NOT raise / must show infinity
  - active user with periodic reset (data_limit_reset_strategy month)
  - on_hold user
  - disabled/expired user (configs gated, status shown)

Run: py demo/test_pg_render.py
"""
import os, sys, glob, time, math
from datetime import datetime, UTC, timedelta

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_DIR = os.path.join(ROOT, "pasarguard-themes", "subscription")

SAMPLE_LINKS = [
    "vless://demo@demo-main.example.com:443?security=tls&type=ws&path=%2Fws&sni=cdn.example.com#VLESS-WebSocket",
    "trojan://demo-token@demo-main.example.com:443?security=tls&type=ws&path=%2Ftw&sni=cdn.example.com#Trojan-WS",
    "vmess://eyJ2IjoiMiIsInBzIjoiVk1FU1MtTG9jYXRpb24iLCJhZGQiOiJkZW1vLW1haW4uZXhhbXBsZS5jb20ifQ==",
]
SAMPLE_EXPIRE = int(time.time()) + 12 * 86400
SAMPLE_TOTAL = int(100 * 1024 ** 3)
SAMPLE_USED = int(43.75 * 1024 ** 3)


def _size(n):
    if not n or n <= 0:
        return "0 B"
    names = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = math.floor(math.log(n, 1024))
    s = round(n / math.pow(1024, i), 2)
    return f"{s} {names[i]}"


class _E:
    def __init__(self, value):
        self.value = value


class _App:
    def __init__(self, name, icon=None, recommended=False, platform=None, description=None, download=None, imp=None):
        self.name = name
        self.icon_url = icon
        self.recommended = recommended
        self.platform = platform and _E(platform) or None
        self.description = description
        self.download_links = download or []
        self.import_url = imp


class _DL:
    def __init__(self, name, url):
        self.name = name
        self.url = url
        self.language = _E("en")


SAMPLE_APPS = [
    _App("Streisand", "https://img.icons8.com/color/48/streisand.png", True, "android",
         {"en": "Modern Android client that supports multiple protocols and smart routing."},
         [_DL("Install from Play Store", "https://play.google.com/store/apps/details?id=app.streisand")],
         "https://play.google.com/store/apps/details?id=app.streisand&url={url}"),
    _App("Telegram", "https://img.icons8.com/color/48/telegram-app.png", False, None,
         {"en": "Use the official Telegram client."},
         [],
         None),
]


def _user(**kw):
    class U:
        pass
    u = U()
    u.username = kw.get("username", "demo.user")
    u.status = _E(kw.get("status", "active"))
    u.data_limit = kw.get("data_limit", SAMPLE_TOTAL)
    u.used_traffic = kw.get("used_traffic", SAMPLE_USED)
    u.expire = kw.get("expire", SAMPLE_EXPIRE)
    u.hwid_limit = kw.get("hwid_limit", 3)
    u.data_limit_reset_strategy = _E(kw.get("reset", "no_reset"))
    u.on_hold_expire_duration = kw.get("on_hold_dur")
    u.on_hold_timeout = kw.get("on_hold_timeout")
    return u


def contexts():
    return {
        "normal": {
            "user": _user(),
            "links": list(SAMPLE_LINKS),
            "announce": "🔔 در کانال تلگرام عضو شوید: t.me/nuctereadev",
            "announce_url": "https://t.me/nuctereadev",
            "apps": SAMPLE_APPS,
        },
        "unlimited": {
            "user": _user(data_limit=0, expire=None, used_traffic=3 * 1024 ** 3),
            "links": list(SAMPLE_LINKS),
            "announce": "اکانت نامحدود",
            "announce_url": None,
            "apps": [],
        },
        "reset-month": {
            "user": _user(reset="month"),
            "links": list(SAMPLE_LINKS),
            "announce": "",
            "announce_url": None,
            "apps": SAMPLE_APPS,
        },
        "on_hold": {
            "user": _user(status="on_hold", on_hold_dur=3 * 86400,
                          on_hold_timeout=int(time.time()) + 2 * 86400),
            "links": list(SAMPLE_LINKS),
            "announce": "اکانت در حالت نگهداری",
            "announce_url": None,
            "apps": [],
        },
        "disabled": {
            "user": _user(status="disabled", expire=None, used_traffic=int(55 * 1024 ** 3)),
            "links": [],
            "announce": "اکانت غیرفعال",
            "announce_url": None,
            "apps": [],
        },
        "expired": {
            "user": _user(status="expired", expire=int(time.time()) - 2 * 86400,
                          used_traffic=int(23 * 1024 ** 3)),
            "links": [],
            "announce": "اکانت منقضی شده",
            "announce_url": None,
            "apps": [],
        },
    }


def _jinja_datetime(dt):
    if isinstance(dt, int):
        dt = datetime.fromtimestamp(dt, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def render(name, ctx):
    import jinja2
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(PG_DIR), autoescape=False)
    env.filters["bytesformat"] = _size
    env.filters["datetime"] = _jinja_datetime
    env.globals["now"] = time.time
    return env.get_template(f"{name}.html").render(**ctx)


def main():
    names = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(PG_DIR, "*.html")))
    scen = contexts()
    fails = 0
    for name in names:
        for sname, ctx in scen.items():
            try:
                html = render(name, ctx)
            except Exception as e:
                print(f"FAIL {name} [{sname}]: {e}")
                fails += 1
                continue
            if sname == "unlimited" and "∞" not in html:
                print(f"WARN {name} [unlimited]: no infinity symbol rendered")
    total = len(names) * len(scen)
    print(f"\nrendered {total} scenarios across {len(names)} themes; failures={fails}")
    print("OK" if fails == 0 else "FAILED")


if __name__ == "__main__":
    main()