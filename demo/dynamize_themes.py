"""One-shot dynamizer: replace remaining hardcoded demo literals in the
static 3x-ui and PasarGuard subscription themes with live template/JS vars.

Idempotent: files already carrying `<!-- data-nuc-dynamized -->` are skipped.
Audit output for every replacement. Run from repo root:  py demo/dynamize_themes.py
"""
import re, os, glob, sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = "<!-- data-nuc-dynamized -->"

USED = "43.75"
REMAINED = "56.25"
TOTAL = "100"
DATE = r"2026-09-20(?:\s+20:25(?::\d\d)?)?"
TOTALS = lambda: {}


def p(path, *lines):
    print(f"  [{os.path.basename(os.path.dirname(path)) or path}] " + " | ".join(lines))


# ---------------------------------------------------------------- 3x-ui (Go template)
XUI_DIR = os.path.join(ROOT, "themes")
XUI_STATIC = [
    "amber-dark", "amethyst", "azure", "copper", "cyber-lime", "emerald", "forge",
    "graphite", "indigo-dark", "jade", "lagoon", "linen", "magenta", "navy",
    "neon-emerald", "nova", "onyx", "pearl", "royal", "sapphire", "slate",
    "terracotta", "violet",
]
XUI_HEADLESS = {"amethyst", "jade", "magenta", "terracotta", "violet"}  # no <head>/<title>/DOCTYPE
XUI_ANNOUNCE_CALLOUT = [
    ("amber-dark", "callout-text"), ("azure", "callout-text"), ("copper", "callout-text"),
    ("emerald", "callout-text"), ("forge", "callout-text"), ("linen", "callout-text"),
    ("neon-emerald", "callout-text"), ("nova", "callout-text"), ("royal", "callout-text"),
    ("sapphire", "callout-text"), ("pearl", "notice-text"),
]

XUI_BRIDGE = (
    "<script data-nuc=\"dynamize\">(function(){\n"
    "var D={expire:{{ .expire }},enabled:{{ .enabled }},total:{{ .totalByte }},used:({{ .downloadByte }})+({{ .uploadByte }})};\n"
    "function pad(n){return String(n).length<2?'0'+n:n;}\n"
    "function fill(sel,fn){document.querySelectorAll(sel).forEach(fn);}\n"
    "var pct=D.total>0?Math.min(100,D.used/D.total*100):0;\n"
    "fill('[data-nuc-expire]',function(el){if(D.expire>0){var d=new Date(D.expire*1000);el.textContent=d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());}else{el.textContent=\"\\u221E\";}});\n"
    "fill('[data-nuc-days]',function(el){if(D.expire>0){var n=Math.ceil((D.expire*1000-Date.now())/86400000);el.textContent=n>0?String(n).toLocaleString('fa-IR'):'0';}else{el.textContent=\"\\u221E\";}});\n"
    "fill('[data-nuc-pct]',function(el){el.textContent=pct.toFixed(pct%1?1:0);});\n"
    "fill('[data-nuc-pct-rem]',function(el){var r=100-pct;el.textContent=r.toFixed(r%1?1:0);});\n"
    "fill('[data-nuc-width]',function(el){el.setAttribute('data-width',pct);el.style.width=pct+'%';});\n"
    "fill('[data-nuc-width-rem]',function(el){var r=100-pct;el.setAttribute('data-width',r);el.style.width=r+'%';});\n"
    "fill('[data-nuc-int]',function(el){el.textContent=Math.floor(D.used/1073741824);});\n"
    "fill('[data-nuc-dec]',function(el){var g=D.used/1073741824;el.textContent=pad(Math.round((g-Math.floor(g))*100));});\n"
    "fill('[data-nuc-gauge]',function(el){var dsa=parseFloat(el.getAttribute('stroke-dasharray'));if(!dsa)dsa=263.89;el.style.strokeDashoffset=String(dsa*(1-pct/100));});\n"
    "})();</script>"
)

USERNAME_GO = ("{{ range $i, $e := .emails }}{{ if $i }}{{ \", \" }}{{ end }}{{ $e }}{{ end }}")


def dynamize_xui(name):
    path = os.path.join(XUI_DIR, name, "index.html")
    txt = open(path, encoding="utf-8").read()
    if MARK in txt:
        print(f"  {name}: already dynamized, skip")
        return
    edits = []

    def rep(pattern, repl, flags=0, count=0):
        nonlocal txt
        txt2 = re.sub(pattern, repl, txt, count=count, flags=flags)
        if txt2 != txt:
            edits.append(len(re.findall(pattern, txt, flags=flags)) if not count else count)
        txt = txt2

    # 2 username
    rep(re.escape("demo.user"), USERNAME_GO)

    # 3 date literal -> bridge "expire" marker
    rep(r">\s*" + DATE + r"\s*<", r"><i data-nuc-expire></i><")

    # 3b days-left -> bridge "days" marker (jade/terracotta/violet)
    if name in ("jade", "terracotta", "violet"):
        rep(r"(۱۲|\b12\b)(\s*روز\s*باقیمانده)", r"<span data-nuc-days></span>\2")
        rep(r"(\s*12\s*)(<span data-i18n=\"(?:day|days)\"[^>]*>)", r"<span data-nuc-days></span> \2")

    # 4 indigo vol split
    rep(r'(<span class="vol-int">)43(</span>)', r"\1 data-nuc-int\2")
    rep(r'(<span class="vol-dec">)75(</span>)', r"\1 data-nuc-dec\2")

    # 5 GB-suffixed values
    rep(r">\s*43\.75\s+GB\s*<", r">{{ .used }}<")
    rep(r">\s*56\.25\s+GB\s*<", r">{{ .remained }}<")
    rep(r">\s*100(?:\.0)?\s+GB\s*<", r">{{ .total }}<")

    # 6 bare values
    rep(r">\s*43\.75\s*<", r">{{ .used }}<")
    rep(r">\s*56\.25\s*<", r">{{ .remained }}<")

    # 7 bare total 100 (context: element content)
    rep(r">\s*100(?:\.0)?\s*<", r">{{ .total }}<")

    # 8 percent
    rep(r">\s*43(?:\.8)?\s*%<", r"><i data-nuc-pct></i>%<")
    rep(r">\s*56\s*%<", r"><i data-nuc-pct-rem></i>%<")

    # 9 data-widths
    rep(r'data-width="43\.8"', 'data-nuc-width=""')
    rep(r'data-width="56\.2"', 'data-nuc-width-rem=""')

    # 10 gauges
    rep(r'data-target="[0-9.]+"', 'data-nuc-gauge=""')

    # 11 empty megabyte unit spans (keep indigo vol-unit)
    if name != "indigo-dark":
        rep(r'(<span class="[a-z-]*unit[a-z-]*"(?:[^>]*)>)GB(</span>)', r"\1\2")

    # 12 device count
    rep(r">\s*3\s*<span data-i18n=\"of\">از</span>\s*3\s*<",
        r"{{ len .emails }}<span data-i18n=\"of\">از</span>{{ len .emails }}<")
    rep(r">\s*3\s*<span data-i18n=\"devices\">دستگاه</span>",
        r"{{ len .emails }} <span data-i18n=\"devices\">دستگاه</span>")
    rep(r">\s*3\s*<", r">{{ len .emails }}<")

    # 13 announce
    for tn, cls in XUI_ANNOUNCE_CALLOUT:
        if name == tn:
            if cls == "notice-text":
                rep(r'(<div class="notice-text">)[\s\S]*?nucsub\s*</div>',
                    r'\1{{ if .announce }}{{ .announce }}{{ end }}</div>')
            else:
                rep(r'(<div class="callout-text">)[\s\S]*?nucsub\s*</div>',
                    r'\1{{ if .announce }}{{ .announce }}{{ end }}</div>', flags=re.DOTALL)
                # some themes put a </p>/<br> structure inside; catch leftovers
                rep(r'(<div class="callout-text">)[\s\S]*?(</div>\s*)</div>',
                    r'\1{{ if .announce }}{{ .announce }}{{ end }}\2')
    if name == "slate":
        rep(r'(<div class="callout-title">[^<]*</div>)[\s\S]*?nucsub',
            r'\1{{ if .announce }}{{ .announce }}{{ end }}')
    if name == "terracotta":
        rep(r'(<p>)[\s\S]*?nucsub\s*(</p>)', r'\1{{ if .announce }}{{ .announce }}{{ end }}\2')

    # 14 title + head
    if name in XUI_HEADLESS:
        head = ('<!DOCTYPE html>\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
                '<title>{{ .subTitle }} - اکانت</title>\n</head>\n')
        rep(r'(<!DOCTYPE html>\s*)?(<html[^>]*>)\n', r"\2\n" + head.replace("\\", "\\\\"))
    else:
        rep(r"<title>[^<]*</title>", "<title>{{ .subTitle }} - اکانت</title>")

    # 15 bridge
    if "NUC_D" not in txt:
        rep(r"</body>", lambda m: XUI_BRIDGE + "\n</body>", count=1)

    txt = txt.replace("<html", MARK[:-3] * 0 or MARK + "\n<html", 1)
    # marker goes right above <html> (or <head>)
    if MARK not in txt:
        txt = txt.replace("<head>", MARK + "\n<head>", 1) if "<head>" in txt else MARK + "\n" + txt
    open(path, "w", encoding="utf-8").write(txt)
    tot = sum(edits)
    print(f"  {name}: {tot} replacements  {MARK}")
    if "{{ len .emails }}" not in txt:
        print(f"    ! no device count rendered")
    if "nucsub" in txt:
        print(f"    ! t.me link still present")
    if re.search(r">\s*(43\.75|56\.25|100(?:\.0)?|43\.8|43|3|" + DATE + r")\s*<", txt):
        print(f"    ! REMAINING LITERALS")


def dynamize_all_xui():
    print("=== XUI (3x-ui) static themes ===")
    for name in XUI_STATIC:
        dynamize_xui(name)


# ---------------------------------------------------------------- Pasarguard (Jinja2)
PG_DIR = os.path.join(ROOT, "pasarguard-themes", "subscription")
# themes whose numeric literals sit next to an explicit unit span -> show GB number
PG_GBFORMULA = {"amber", "gold", "lime", "mint", "olive", "pulse"}
PG_HEADLESS = {"abyss", "dusk", "marine", "ocean", "tide"}
PG_GUAGE_DASH = {
    "azure": "289.026", "comet": "439.82", "emerald": "314.159", "nova": "439.82",
    "ocean": "326.726", "onyx": "351.86", "prisma": "433.54", "pulse": "263.89",
    "tide": "339.292", "zenith": "339.29",
}

PCT_TPL = "{{ (user.used_traffic / user.data_limit * 100) | round(1) }}%"
USED_TPL = "{{ user.used_traffic | bytesformat }}"
TOTAL_TPL = "{% if user.data_limit %}{{ user.data_limit | bytesformat }}{% else %}∞{% endif %}"
GB_USED_TPL = "{{ (user.used_traffic / 1024 ** 3) | round(2) }}"
GB_REM_TPL = "{{ ((user.data_limit - user.used_traffic) / 1024 ** 3) | round(2) }}"
DAYS_TPL = "{{ ((user.expire - now()) / 86400) | round(0, 'ceil') | int if (user.expire - now()) > 0 else 0 }}"


def dynamize_pg(name):
    path = os.path.join(PG_DIR, f"{name}.html")
    txt = open(path, encoding="utf-8").read()
    if MARK in txt:
        print(f"  {name}: already dynamized, skip")
        return
    edits = []

    def rep(pattern, repl, flags=0, count=0):
        nonlocal txt
        txt2 = re.sub(pattern, repl, txt, count=count, flags=flags)
        if txt2 != txt:
            n = len(re.findall(pattern, txt, flags=flags)) if not count else count
            edits.append(n)
        txt = txt2

    # gauges first
    if name in PG_GUAGE_DASH:
        dash = PG_GUAGE_DASH[name]
        tgt = ('data-target="{% if user.data_limit %}{{ ((1 - user.used_traffic / user.data_limit) * '
               + dash + ') | round(2) }}{% else %}0{% endif %}"')
        rep(r'data-target="[0-9.]+"', tgt)

    if name in PG_GBFORMULA:
        rep(r">\s*43\.75\s*<", f">{GB_USED_TPL}<")
        rep(r">\s*56\.25\s*<", f">{GB_REM_TPL}<")
    else:
        rep(r">\s*43\.75\s*<", f">{USED_TPL}<")
        rep(r">\s*56\.25\s*<", f">{TOTAL_TPL[:0]}{{ (user.data_limit - user.used_traffic) | bytesformat }}<")

    # percents
    rep(r">\s*43(?:\.8)?\s*%<", f">{PCT_TPL}<")

    # vol-int/dec split (steel)
    if name == "steel":
        rep(r'(<span class="vol-int">)43(</span>)',
            r'\1{{ (user.used_traffic / 1024 ** 3) | int }}\2')
        rep(r'(<span class="vol-dec">)75(</span>)',
            r'\1{{ ((user.used_traffic / 1024 ** 3) % 1 * 100) | round | int }}\2')

    # bare totals
    rep(r">\s*100(?:\.0)?\s*<", f">{TOTAL_TPL}<")

    # device count
    rep(r">\s*3\s*<span data-i18n=\"of\">از</span>\s*3\s*<",
        r"{{ user.hwid_limit }}<span data-i18n=\"of\">از</span>{{ user.hwid_limit }}<")
    rep(r"(·\s*)3(\s*<br)", r"\1{{ user.hwid_limit }}\2")
    rep(r">\s*3\s*<", r">{{ user.hwid_limit }}<")

    # days
    rep(r"(>)\s*(12|۱۲)\s*(<span data-i18n=\"day\">)", r"\1" + DAYS_TPL + r"\3")
    rep(r"(>)\s*(12|۱۲)\s*(<span data-i18n=\"days\">)", r"\1" + DAYS_TPL + r"\3")
    rep(r"(>)\s*(12|۱۲)(\s*روز\s*باقیمانده\s*<)", r"\1" + DAYS_TPL + r"\3")

    # announce (container-inner replacement; handles indented multi-line + <p> boxes)
    rep(r'(<div class="callout-text">)[\s\S]*?t\.me/nucsub\s*</div>',
        r'\1{% if announce %}{{ announce }}{% endif %}</div>')
    rep(r'(<div class="notice-text">)[\s\S]*?t\.me/nucsub\s*</div>',
        r'\1{% if announce %}{{ announce }}{% endif %}</div>')
    rep(r'(<div class="note-text">)[\s\S]*?t\.me/nucsub\s*</div>',
        r'\1{% if announce %}{{ announce }}{% endif %}</div>')
    rep(r'(<p>)[\s\S]*?t\.me/nucsub\s*</p>',
        r'\1{% if announce %}{{ announce }}{% endif %}</p>')

    # title
    if name in PG_HEADLESS:
        head = ("<!DOCTYPE html>\n<head>\n<meta charset=\"utf-8\">\n"
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                "<title>{{ user.username }} - NUC-SUB</title>\n</head>\n")
        rep(r"(<!DOCTYPE html>\s*)?(<html[^>]*>)\n", r"\2\n" + head)
    else:
        rep(r"<title>[^<]*</title>", "<title>{{ user.username }} - NUC-SUB</title>")

    txt = (MARK + "\n" + txt) if MARK not in txt else txt
    open(path, "w", encoding="utf-8").write(txt)
    tot = sum(edits)
    print(f"  {name}: {tot} replacements  {MARK}")
    if re.search(r">\s*(43\.75|56\.25|100(?:\.0)?|43\.8|43|100|12|3)\s*<", txt):
        print(f"    ! REMAINING LITERALS: {re.findall(r'>\\s*(?:43\\.75|56\\.25|100(?:\\.0)?|43\\.8|43|100|12|3)\\s*<', txt)[:6]}")


def dynamize_all_pg():
    print("=== PasarGuard themes ===")
    for p in sorted(glob.glob(os.path.join(PG_DIR, "*.html"))):
        dynamize_pg(os.path.basename(p)[:-5])


if __name__ == "__main__":
    dynamize_all_xui()
    dynamize_all_pg()
    print("\ndone")