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


def _discover_theme_names():
    """The two panels no longer always share names — auto-discover instead of a
    hard-coded list so replacing/adding a theme is zero-touch."""
    pg = sorted(
        f[: -len(".html")]
        for f in os.listdir(PG_THEMES)
        if f.endswith(".html")
    )
    xui = sorted(
        d
        for d in os.listdir(XUI_THEMES)
        if os.path.isdir(os.path.join(XUI_THEMES, d))
    )
    return pg, xui

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

    pg_names, xui_names = _discover_theme_names()
    json_pg = json.dumps(pg_names, ensure_ascii=False)
    json_xui = json.dumps(xui_names, ensure_ascii=False)

    ok, fail = {}, {}
    for name in pg_names:
        try:
            html = render_pasarguard(name, PG_CONTEXT)
            with open(os.path.join(OUT, "pg", f"{name}.html"), "w", encoding="utf-8") as f:
                f.write(html)
            ok[f"pg {name}"] = f"{len(html):,} B"
        except Exception as e:
            fail[f"pg {name}"] = str(e)

    for name in xui_names:
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

    # Copy the hand-edited gallery (source of truth) instead of regenerating it,
    # so the user's customizations survive every build. Two placeholders get the
    # live theme lists injected so adding/renaming a theme is zero-touch.
    gallery_src = os.path.join(DEMO_DIR, "gallery.html")
    if os.path.isfile(gallery_src):
        with open(gallery_src, encoding="utf-8") as f:
            gallery_html = f.read()
    else:
        gallery_html = gallery_page()  # fallback template
    gallery_html = gallery_html.replace("__THEMES_PG__", json_pg)
    gallery_html = gallery_html.replace("__THEMES_XUI__", json_xui)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(gallery_html)
    print(f"\nwritten to {OUT}")


def gallery_page():
    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NUC-SUB Live Preview — ۱۶ تم سابسکریپشن</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{height:100%}}
body{{font-family:Vazirmatn,'Segoe UI',Tahoma,sans-serif;background:#0f0d1d;color:#f5f2ff;display:flex;flex-direction:column;overflow:hidden}}
.topbar{{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.08);background:rgba(13,11,30,.9);z-index:5}}
.logo{{width:36px;height:36px;border-radius:11px;background:linear-gradient(135deg,#facc15,#f59e0b);display:flex;align-items:center;justify-content:center;font-weight:900;color:#1a1a1a;font-size:17px}}
h1{{font-size:17px;font-weight:800;white-space:nowrap}}
h1 b{{background:linear-gradient(135deg,#facc15,#f59e0b);-webkit-background-clip:text;background-clip:text;color:transparent}}
.tabs{{display:flex;gap:6px}}

.tabs button{{padding:7px 14px;border-radius:9px;border:1px solid rgba(255,255,255,.10);background:transparent;color:rgba(245,242,255,.7);cursor:pointer;font-family:inherit;font-size:12px;font-weight:700}}
.tabs button.on{{background:linear-gradient(135deg,#facc15,#f59e0b);color:#1a1a1a;border-color:transparent}}
.selwrap{{position:relative}}
.selfirst{{position:absolute;right:0;top:100%;margin-top:8px;z-index:20;min-width:190px}}
.selfirst select{{width:100%;padding:9px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.12);background:#1b1830;color:#f5f2ff;font-family:inherit;font-size:13px;cursor:pointer}}
.head-right{{flex:1;display:flex;justify-content:flex-end;align-items:center;gap:10px}}
.head-right a{{color:#facc15;text-decoration:none;font-size:12px;font-weight:700;white-space:nowrap}}
.stage{{flex:1;display:flex;min-height:0}}
{{/* full-screen theme render */}}
.stage iframe{{flex:1;width:100%;height:100%;border:0;background:#fff}}
.hidden{{display:none!important}}
@media(max-width:700px){{
  h1{{font-size:14px}}
  .tabs button{{padding:6px 9px;font-size:11px}}
}}
</style>
</head>
<body>
  <div class="topbar">
    <div class="logo">N</div>
    <h1>NUC-SUB <b>Live Preview</b></h1>
    <div class="tabs">
      <button id="tab-pg" class="on" onclick="setTab('pg')">PasarGuard</button>
      <button id="tab-xui" onclick="setTab('xui')">3x-ui</button>
    </div>
    <div class="selwrap">
      <div class="selfirst">
        <select id="themeSel" onchange="pickSel(this.value)">
          <!-- pages are filled by build.py -->
        </select>
      </div>
    </div>
    <div class="head-right">
      <a id="openLink" href="#" target="_blank" rel="noopener">باز در تب جدید ↗</a>
    </div>
  </div>
  <div class="stage">
    <iframe id="frame" title="theme preview"></iframe>
  </div>
<select id="optTpl" class="hidden"></select>
<script>
var THEMES = {{
  pg: __THEMES_PG__,
  xui: __THEMES_XUI__
}};
var state={{}};
function p2label(p){{ return p==='pg' ? 'PasarGuard' : '3x-ui'; }}
function buildSel(p){{
  var sel=document.getElementById('themeSel');
  var cur = sel.value;
  sel.options.length=0;
  THEMES[p].forEach(function(n){{
    var o=document.createElement('option');
    o.value=p+':'+n; o.textContent=n;
    sel.appendChild(o);
  }});
  if(cur && cur.split(':')[0]===p) sel.value=cur;
  else sel.value=sel.options[0] ? sel.options[0].value : '';
}}
function setHref(){{
  var s=(state.p||'pg')+(state.n ? '/'+(state.p==='pg'?state.n+'.html':state.n+'/index.html') : '');
  var a=document.getElementById('openLink');
  a.href=s;
}}
function pickSel(v){{
  if(!v) return;
  var parts=v.split(':'); var p=parts[0], n=parts[1];
  state.p=p; state.n=n;
  var f=document.getElementById('frame');
  f.src = p==='pg' ? 'pg/'+n+'.html' : 'xui/'+n+'/index.html';
  document.getElementById('openLink').href = f.src;
  document.querySelectorAll('.tabs button').forEach(function(b){{
    b.className = b.id==='tab-'+p ? 'on' : '';
  }});
  var sel=document.getElementById('themeSel');
  if(sel.value!==v) sel.value=v;
}}
function setTab(p){{
  document.getElementById('tab-pg').className=p==='pg'?'on':'';
  document.getElementById('tab-xui').className=p==='xui'?'on':'';
  state.p=p;
  buildSel(p);
  pickSel(document.getElementById('themeSel').value || (p+':'+THEMES[p][0]));
}}
setTab('pg');
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()