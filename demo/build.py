#!/usr/bin/env python3
"""
NUC-SUB Live Preview — offline renderer for the 16 subscription themes.

Renders every PasarGuard theme (Jinja2) and every 3x-ui theme (a minimal
Go-template engine) against a FIXED, realistic sample user, then writes a
static site under demo/site/ ready for GitHub Pages.

Run:  python3 demo/build.py
"""
import json
import math
import os
import re
import shutil
import sys
import time
from datetime import UTC, datetime

try:
    import jinja2
except ImportError:
    sys.exit(
        "jinja2 is required. Install it first:  py -m pip install jinja2  (or python3 -m pip install jinja2)\n"
    )

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(DEMO_DIR)
PG_THEMES = os.path.join(REPO, "pasarguard-themes", "subscription")
XUI_THEMES = os.path.join(REPO, "themes")
OUT = os.path.join(DEMO_DIR, "site")

THEME_NAMES = ["arctic", "cyberpunk", "glass", "gradient", "matrix", "minimal", "neon", "sunset"]

"""-------------------------------------------- sample data --------------------------------------------"""
SAMPLE_LINKS = [
    "vless://4f4f2f5a-9b15-4f2c-8db4-56cd11c3d34b@demo-main.example.com:443?type=tcp&security=reality&pbk=DDBCriX8SVdGQEnPfozTtMCOnVej1CSZhk4MY9b1u3A&fp=chrome&sni=cdn.example.com&sid=6ba85179e30d4fc2&spx=%2F&flow=xtls-rprx-vision#VLESS-Reality",
    "vmess://eyJ2IjoiMiIsInBzIjoiVk1FU1MtTG9jYXRpb24iLCJhZGQiOiJkZW1vLW1haW4uZXhhbXBsZS5jb20iLCJwb3J0IjoiNDQzIiwiaWQiOiJjOWM0Zjc4Zi00NTY3LTg5YWItYzBkZWYxMjM0NTY3IiwiYWlkIjoiMCIsIm5ldCI6IndzIiwicGF0aCI6Ii9zbWMiLCJob3N0IjoiY2RuLmV4YW1wbGUuY29tIiwidGxzIjoiIn0=",
    "trojan://demo-token-a1b2c3@demo-main.example.com:443?security=tls&type=ws&path=%2Ftrojan-ws&sni=cdn.example.com#Trojan-WebSocket",
    "ss://YWVzLTI1Ni1nY206ZGVtb3Bhc3N3b3Jk@demo-main.example.com:8388#SS-2022",
    "hysteria2://demo-hy2-password@demo-main.example.com:443?sni=cdn.example.com&insecure=1#Hysteria2",
    "wireguard://demo-wg-key@demo-main.example.com:51820?ip=10.0.0.2%2F32#WireGuard",
]
SAMPLE_EXPIRE = int(time.time()) + 12 * 86400  # 12 days from now
SAMPLE_TOTAL = int(100 * 1024 ** 3)             # 100 GiB
SAMPLE_USED = int(43.75 * 1024 ** 3)            # 43.75 GiB


def _size(n):
    if not n or n <= 0:
        return "0 B"
    names = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = math.floor(math.log(n, 1024))
    s = round(n / math.pow(1024, i), 2)
    return f"{s} {names[i]}"


class _Status:
    value = "active"


class _User:
    username = "demo.user"
    status = _Status()
    data_limit = SAMPLE_TOTAL
    used_traffic = SAMPLE_USED
    expire = SAMPLE_EXPIRE
    hwid_limit = 3
    note = "سلام! این یک اکانت دمو است — حجم، انقضا و لینک‌ها به‌صورت نمونه ثابت هستند."


PG_CONTEXT = {
    "user": _User(),
    "announce": "🔔 در کانال تلگرام عضو شوید: t.me/nuctereadev\nگزارش مشکلات: t.me/nucsub",
    "links": SAMPLE_LINKS,
}

XUI_CONTEXT = {
    "subTitle": "NUC-SUB",
    "emails": ["demo.user"],
    "totalByte": SAMPLE_TOTAL,
    "total": _size(SAMPLE_TOTAL),
    "used": _size(SAMPLE_USED),
    "remained": _size(SAMPLE_TOTAL - SAMPLE_USED),
    "announce": "🔔 در کانال تلگرام عضو شوید: t.me/nuctereadev — گزارش مشکلات: t.me/nucsub",
    "subSupportUrl": "https://t.me/nuctereadev",
    "subJsonUrl": "https://demo.example.com/sub/demo.json",
    "links": SAMPLE_LINKS,
    "expire": SAMPLE_EXPIRE,
    "enabled": True,
    "downloadByte": int(31.5 * 1024 ** 3),
    "uploadByte": int(12.25 * 1024 ** 3),
}


"""-------------------------------------------- Jinja2 (PasarGuard) --------------------------------------------"""
def _jinja_datetime(dt):
    if isinstance(dt, int):
        dt = datetime.fromtimestamp(dt, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def render_pasarguard(theme_name, ctx):
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(PG_THEMES),
        autoescape=False,
    )
    env.filters["bytesformat"] = _size
    env.filters["datetime"] = _jinja_datetime
    env.globals["now"] = time.time
    tpl = env.get_template(f"{theme_name}.html")
    return tpl.render(**ctx)


"""-------------------------------------------- minimal Go-template engine (3x-ui) --------------------------------------------"""
TOK_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)


def _go_truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return bool(v)
    if isinstance(v, (list, tuple, dict, set)):
        return len(v) > 0
    return v is not None


def _go_render_body(body, scope):
    out = []
    i = 0
    while i < len(body):
        m = TOK_RE.search(body, i)
        if not m:
            out.append(body[i:])
            break
        out.append(body[i:m.start()])
        expr = m.group(0)[2:-2].strip()
        i = m.end()
        if not expr or expr.startswith("#"):
            continue
        # range: {{ range $i, $e := .emails }}
        rm = re.match(r"^range\s*\$(\w+)\s*,\s*\$(\w+)\s*:=\s*(.+)$", expr)
        if rm:
            var1, var2, src = rm.group(1), rm.group(2), rm.group(3).strip()
            items = _go_lookup(scope, src) or []
            inner, endpos = _go_slice(body, m.end())
            for idx, item in enumerate(items):
                sub = dict(scope)
                sub[f"${var1}"] = idx
                sub[f"${var2}"] = item
                out.append(_go_render_body(inner, sub))
            i = endpos
            continue
        # if: {{ if ... }} ... {{ else }} ... {{ end }}
        im = re.match(r"^if\s+(.+)$", expr)
        if im:
            cond = _go_truthy(_go_lookup(scope, im.group(1).strip()))
            inner, endpos = _go_slice(body, m.end())
            else_i = re.search(r"\{\{\s*else\s*\}\}", inner, re.DOTALL)
            if cond:
                out.append(_go_render_body(inner[:else_i.start()] if else_i else inner, scope))
            elif else_i:
                out.append(_go_render_body(inner[else_i.end():], scope))
            i = endpos
            continue
        if expr == "else":
            continue
        if expr == "end":
            break
        # variable or literal
        out.append(str(_go_lookup(scope, expr)))
    return "".join(out)


def _go_slice(body, start):
    """Find the matching {{ end }} starting after index `start`; return (inner, end_index_after_end)."""
    depth = 1
    i = start
    while i < len(body):
        m = TOK_RE.search(body, i)
        if not m:
            break
        tok = m.group(0)[2:-2].strip()
        if tok.startswith("range") or tok.startswith("if"):
            depth += 1
        elif tok == "end":
            depth -= 1
            if depth == 0:
                return body[start:m.start()], m.end()
        i = m.end()
    return body[start:], len(body)


def _go_lookup(scope, expr):
    expr = expr.strip()
    if expr.startswith('"') and expr.endswith('"'):
        return expr[1:-1]
    if expr.startswith("$"):
        return scope.get(expr, "")
    if expr.startswith("."):
        key = expr[1:]
        return scope.get("ctx", {}).get(key)
    return scope.get(expr, "")


class _GoIter(list):
    pass


def render_xui(theme_name, ctx):
    src_path = os.path.join(XUI_THEMES, theme_name, "index.html")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    scope = {"ctx": {k: list(v) if isinstance(v, list) else v for k, v in ctx.items()}}
    return _go_render_body(src, scope)


"""-------------------------------------------- site writer --------------------------------------------"""

def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "pg"), exist_ok=True)

    ok, fail = {}, {}
    for name in THEME_NAMES:
        try:
            html = render_pasarguard(name, PG_CONTEXT)
            with open(os.path.join(OUT, "pg", f"{name}.html"), "w", encoding="utf-8") as f:
                f.write(html)
            ok[f"pg {name}"] = f"{len(html):,} B"
        except Exception as e:
            fail[f"pg {name}"] = str(e)

    for name in THEME_NAMES:
        try:
            html = render_xui(name, XUI_CONTEXT)
            d = os.path.join(OUT, "xui", name)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
                f.write(html)
            # copy the theme's static assets (css/fonts/fa)
            for sub in ("css", "fonts", "fa", "js"):
                s = os.path.join(XUI_THEMES, name, sub)
                if os.path.isdir(s):
                    shutil.copytree(s, os.path.join(d, sub), dirs_exist_ok=True)
            ok[f"xui {name}"] = f"{len(html):,} B"
        except Exception as e:
            fail[f"xui {name}"] = str(e)

    print(f"rendered {len(ok)} themes OK, {len(fail)} failed")
    for k, v in sorted(ok.items()):
        print(f"  OK   {k}  ({v})")
    for k, v in sorted(fail.items()):
        print(f"  FAIL {k}: {v}")

    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(gallery_page())
    print(f"\nwritten to {OUT}")


def gallery_page():
    cards = []
    for name in THEME_NAMES:
        cards.append(
            f"""<button class="card" onclick="pick('pg','{name}',this)" data-p="pg" data-n="{name}"><span class="p">PasarGuard</span><span class="t">{name}</span></button>"""
        )
    for name in THEME_NAMES:
        cards.append(
            f"""<button class="card" onclick="pick('xui','{name}',this)" data-p="xui" data-n="{name}"><span class="p">3x-ui</span><span class="t">{name}</span></button>"""
        )
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NUC-SUB Live Preview — ۱۶ تم سابسکریپشن</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:Vazirmatn,'Segoe UI',Tahoma,sans-serif;background:radial-gradient(1100px 620px at 18% -10%,rgba(139,92,246,.16),transparent 60%),radial-gradient(900px 560px at 88% 12%,rgba(245,158,11,.10),transparent 55%),linear-gradient(160deg,#0d0b1e,#16132e);min-height:100vh;color:#f5f2ff;padding:26px 18px 40px}}
.wrap{{max-width:1080px;margin:0 auto}}
.head{{display:flex;align-items:center;gap:14px;margin-bottom:8px;flex-wrap:wrap}}
.logo{{width:44px;height:44px;border-radius:13px;background:linear-gradient(135deg,#facc15,#f59e0b);display:flex;align-items:center;justify-content:center;font-weight:900;color:#1a1a1a;font-size:20px;box-shadow:0 8px 22px rgba(245,158,11,.30)}}
h1{{font-size:22px;font-weight:800}}
h1 b{{background:linear-gradient(135deg,#facc15,#f59e0b);-webkit-background-clip:text;background-clip:text;color:transparent}}
.sub{{color:rgba(245,242,255,.55);font-size:13px;margin:2px 0 22px}}
.layout{{display:grid;grid-template-columns:300px 1fr;gap:20px;align-items:start}}
.side{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.09);border-radius:18px;padding:14px;position:sticky;top:20px}}
.tab{{display:flex;gap:8px;margin-bottom:12px}}
.tab button{{flex:1;padding:9px 0;border-radius:10px;border:1px solid rgba(255,255,255,.10);background:transparent;color:rgba(245,242,255,.7);cursor:pointer;font-family:inherit;font-size:12px;font-weight:700}}
.tab button.on{{background:linear-gradient(135deg,#facc15,#f59e0b);color:#1a1a1a;border-color:transparent}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.card{{border:1px solid rgba(255,255,255,.10);background:rgba(255,255,255,.03);border-radius:12px;padding:11px;cursor:pointer;text-align:right;font-family:inherit;transition:all .18s;color:#f5f2ff}}
.card:hover{{border-color:#facc15;transform:translateY(-1px)}}
.card.on{{border-color:#f59e0b;background:rgba(245,158,11,.10)}}
.card .p{{display:block;font-size:9px;letter-spacing:.5px;color:rgba(245,242,255,.45);margin-bottom:5px}}
.card .t{{font-size:13px;font-weight:800}}
.stage{{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.09);border-radius:18px;padding:18px;min-height:640px}}
.phone{{max-width:375px;margin:0 auto;border:10px solid #191826;border-radius:36px;box-shadow:0 24px 60px rgba(0,0,0,.5);overflow:hidden;height:700px;position:relative}}
.phone iframe{{width:100%;height:100%;border:0;display:block}}
.cur{{display:flex;align-items:center;justify-content:space-between;max-width:375px;margin:14px auto 0;font-size:12px;color:rgba(245,242,255,.6)}}
.cur a{{color:#facc15;text-decoration:none;font-weight:700}}
.footer{{text-align:center;margin-top:26px;font-size:11px;color:rgba(245,242,255,.4)}}
.footer a{{color:rgba(245,242,255,.7);text-decoration:none}}
@media(max-width:820px){{.layout{{grid-template-columns:1fr}}.side{{position:static}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="logo">N</div>
    <h1>NUC-SUB <b>Live Preview</b></h1>
  </div>
  <div class="sub">۸ تم PasarGuard + ۸ تم 3x-ui — پیش‌نمایش با داده‌ی ثابت (بدون نیاز به سرور)</div>
  <div class="layout">
    <div class="side">
      <div class="tab">
        <button id="tab-pg" class="on" onclick="setTab('pg')">PasarGuard</button>
        <button id="tab-xui" onclick="setTab('xui')">3x-ui</button>
      </div>
      <div class="cards" id="cards">{''.join(cards)}</div>
    </div>
    <div class="stage">
      <div class="phone"><iframe id="frame" title="preview"></iframe></div>
      <div class="cur"><span id="cur">یک قالب را از سمت راست انتخاب کنید</span></div>
    </div>
  </div>
  <div class="footer">NUC-SUB Live Preview — پروژه‌ی متن‌باز | <a href="https://github.com/nuctereadev/NUC-SUB" target="_blank" rel="noopener">GitHub</a></div>
</div>
<script>
var state={{}};
function pick(p,n,el){{
  document.querySelectorAll('.card').forEach(function(c){{c.classList.remove('on')}});
  el.classList.add('on');
  var f=document.getElementById('frame');
  f.src=(p==='pg'?'pg/':'xui/')+n+(p==='pg'?'.html':'/index.html');
  document.getElementById('cur').innerHTML='<span>'+ (p==='pg'?'PasarGuard':'3x-ui') +' / <b>'+n+'</b></span><a href="'+f.src+'" target="_blank" rel="noopener">باز در تب جدید ↗</a>';
  state.p=p; state.n=n; state.autoPick=0;
}}
function setTab(p){{
  document.getElementById('tab-pg').className=p==='pg'?'on':'';
  document.getElementById('tab-xui').className=p==='xui'?'on':'';
  document.querySelectorAll('.card').forEach(function(c){{
    c.style.display=(c.getAttribute('data-p')===p)?'':'none';
  }});
  var first=document.querySelector('.card[data-p="'+p+'"]');
  if(first && state.autoPick!==0){{ first.click(); }}
  state.autoPick=1;
}}
setTab('pg');
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()