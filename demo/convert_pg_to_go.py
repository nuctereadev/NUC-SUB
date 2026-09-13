"""One-shot: convert PasarGuard Jinja2 subscription themes (pasarguard-themes/subscription/*.html)
into Go templates deployable on the x-ui (Sanaei) sub server (sub_templates/<name>/index.html).

Writes to build/xui-33/<name>/index.html for all 33 pg-named themes. Go render uses the panel's
subPageContext keys: .subTitle .emails .expire .enabled .used .remained .total .totalByte
.downloadByte .uploadByte .links .announce .subSupportUrl .hwidLimit (ghost -> zero).

Run from repo root:  py demo/convert_pg_to_go.py
"""
import re, os, glob

sys_exit = __import__("sys").exit
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_DIR = os.path.join(ROOT, "pasarguard-themes", "subscription")
OUT_DIR = os.path.join(ROOT, "build", "xui-33")
MARKER = "<!-- data-nuc-go-33 -->"
BRIDGE_MARK = '<script data-nuc="dynamize">'

HEADLESS = {"abyss", "dusk", "marine", "ocean", "tide"}

BRIDGE = (
    '<script data-nuc="dynamize">(function(){\n'
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
    "fill('[data-nuc-gb]',function(el){el.textContent=(D.used/1073741824).toFixed(2);});\n"
    "fill('[data-nuc-gb-rem]',function(el){var g=(D.total-D.used)/1073741824;el.textContent=g>0?g.toFixed(2):'0.00';});\n"
    "fill('[data-nuc-gauge]',function(el){var dsa=parseFloat(el.getAttribute('stroke-dasharray'));if(!dsa)dsa=263.89;el.style.strokeDashoffset=String(dsa*(1-pct/100));});\n"
    "})();</script>"
)

# exact pg token -> Go expression (longest-first via explicit order)
TOKEN_MAP = [
    ("{{ ((user.expire - now()) / 86400) | round(0, 'ceil') | int if (user.expire - now()) > 0 else 0 }}",
     "<i data-nuc-days></i>"),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 439.82) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 433.54) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 351.86) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 339.292) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 339.29) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 326.726) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 314.159) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 289.026) | round(2) }}", ""),
    ("{{ ((1 - user.used_traffic / user.data_limit) * 263.89) | round(2) }}", ""),
    ("{{ (user.data_limit - user.used_traffic) | bytesformat }}", "{{ .remained }}"),
    ("{{ ((user.data_limit - user.used_traffic) / 1024 ** 3) | round(2) }}", "<i data-nuc-gb-rem></i>"),
    ("{{ user.used_traffic | bytesformat }}", "{{ .used }}"),
    ("{{ user.data_limit | bytesformat }}", "{{ .total }}"),
    ("{{ user.expire | datetime | tojson }}", "{{ .expire }}"),
    ("{{ user.expire | datetime }}", "<i data-nuc-expire></i>"),
    ("{{ (user.used_traffic / user.data_limit * 100) | round(1) }}", "<i data-nuc-pct></i>"),
    ("{{ (user.used_traffic / 1024 ** 3) | round(2) }}", "<i data-nuc-gb></i>"),
    ("{{ (user.used_traffic / 1024 ** 3) | int }}", "<i data-nuc-int></i>"),
    ("{{ ((user.used_traffic / 1024 ** 3) % 1 * 100) | round | int }}", "<i data-nuc-dec></i>"),
    ("{{ remaining | bytesformat }}", "{{ .remained }}"),
    ("{{ user.used_traffic }}", "{{ .used }}"),
    ("{{ user.data_limit }}", "{{ .total }}"),
    ("{{ link }}", "{{ $link }}"),
    ("{{ links | length }}", "{{ len .links }}"),
    ("{{ announce | replace('\\n', '<br>') }}", "{{ .announce }}"),
    ("{{ announce }}", "{{ .announce }}"),
    ("{{ user.hwid_limit }}", "{{ len .emails }}"),
    ("{{ user.note }}", ""),
    ("{{ user.status.value }}", ""),
]
TOKEN_ORDERED = sorted(TOKEN_MAP, key=lambda kv: -len(kv[0]))

JINJA_MAP = [
    ("{% for link in links %}", "{{ range $i, $link := .links }}"),
    ("{% if announce %}", "{{ if .announce }}"),
    ("{% if links %}", "{{ if .links }}"),
    ("{% if user.expire %}", "{{ if .expire }}"),
    ("{% if user.used_traffic %}", "{{ if .used }}"),
    ("{% if user.data_limit %}", "{{ if .totalByte }}"),
    ("{% if user.hwid_limit is not none %}", "{{ if .hwidLimit }}"),
    ("{% else %}", "{{ else }}"),
    ("{% endif %}", "{{ end }}"),
    ("{% endfor %}", "{{ end }}"),
]

USERNAME_JOIN = ("<i data-nuc-user>{{ range $i, $e := .emails }}{{ if $i }}{{ \", \" }}{{ end }}{{ $e }}{{ end }}</i>")
TITLE_GO = "<title>{{ if .subTitle }}{{ .subTitle }}{{ else }}\u0627\u06a9\u0627\u0646\u062a{{ end }}</title>"


def volt_specific(txt):
    """volt.html carries status chains, note banner, remaining<0, JS config D + tg placeholder."""
    # status pulse class chain
    txt = re.sub(
        r"class=\"status-pulse \{% if user\.status\.value == 'active' %\}\{% elif user\.status\.value == 'limited' %\}warning\{% elif user\.status\.value == 'expired' or user\.status\.value == 'disabled' %\}inactive\{% elif user\.status\.value == 'on_hold' %\}warning\{% endif %\}\"",
        'class="status-pulse {{ if .enabled }}{{ else }}inactive{{ end }}"', txt)
    # badge class chain
    txt = re.sub(
        r"status-badge-inline \{% if user\.status\.value == 'active' %\}active\{% elif user\.status\.value == 'limited' %\}limited\{% elif user\.status\.value == 'expired' %\}expired\{% elif user\.status\.value == 'on_hold' %\}on_hold\{% elif user\.status\.value == 'disabled' %\}disabled\{% endif %\}",
        "status-badge-inline {{ if .enabled }}active{{ else }}disabled{{ end }}", txt)
    # i18n-status attr
    txt = txt.replace('data-i18n-status="{{ user.status.value }}"',
                      'data-i18n-status="{{ if .enabled }}active{{ else }}disabled{{ end }}"')
    # status text chains (5-branch + else)
    txt = re.sub(
        r"\{% if user\.status\.value == 'active' %\}\u0641\u0639\u0627\u0644\{% elif user\.status\.value == 'limited' %\}\u0645\u062d\u062f\u0648\u062f\{% elif user\.status\.value == 'expired' %\}\u0645\u0646\u0642\u0636\u06cc\{% elif user\.status\.value == 'on_hold' %\}\u062f\u0631 \u0627\u0646\u062a\u0638\u0627\u0631\{% elif user\.status\.value == 'disabled' %\}\u063a\u06cc\u0631\u0641\u0639\u0627\u0644\{% else %\}\{\{ user\.status\.value \}\}\{% endif %\}",
        "{{ if .enabled }}\u0641\u0639\u0627\u0644{{ else }}\u063a\u06cc\u0631\u0641\u0639\u0627\u0644{{ end }}", txt)
    # remain display (gauge stat)
    txt = re.sub(
        r"id=\"remainDisplay\">\{% if user\.data_limit %\}\{% set remaining = user\.data_limit - user\.used_traffic %\}\{% if remaining < 0 %\}0 B\{% else %\}\{\{ remaining \| bytesformat \}\}\{% endif %\}\{% else %\}\u221e\{% endif %\}",
        'id="remainDisplay">{{ if .totalByte }}{{ .remained }}{{ else }}\u221e{{ end }}', txt)
    # expire date cell
    txt = re.sub(
        r"id=\"expireDate\" data-i18n-ex>\{% if user\.expire %\}\{\{ user\.expire \| datetime \}\}\{% else %\}\u221e \u0646\u0627\u0645\u062d\u062f\u0648\u062f\{% endif %\}",
        'id="expireDate" data-i18n-ex>{{ if .expire }}<i data-nuc-expire></i>{{ else }}\u221e \u0646\u0627\u0645\u062d\u062f\u0648\u062f{{ end }}', txt)
    # JS config object
    txt = txt.replace(
        "expire: {% if user.expire %}{{ user.expire | datetime | tojson }}{% else %}null{% endif %},",
        "expire: {{ if .expire }}{{ .expire }}{{ else }}null{{ end }},")
    txt = txt.replace(
        "total: {% if user.data_limit %}{{ user.data_limit }}{% else %}0{% endif %},",
        "total: {{ if .totalByte }}{{ .totalByte }}{{ else }}0{{ end }},")
    txt = txt.replace(
        "used: {% if user.used_traffic %}{{ user.used_traffic }}{% else %}0{% endif %},",
        "used: ({{ .downloadByte }})+({{ .uploadByte }}),")
    # countdown expiry parse: panel provides unix seconds
    txt = txt.replace("var expireDate = new Date(String(D.expire).replace(' ','T'));",
                      "var expireDate = new Date(D.expire*1000);")
    # telegram channel from panel
    txt = txt.replace("var tg = '@@TG_CHANNEL@@';", "var tg = '{{ .subSupportUrl }}';")
    txt = txt.replace('href="@@TG_CHANNEL@@"', 'href="{{ .subSupportUrl }}"')
    # note banner: drop
    txt = re.sub(r"\{% if user\.note %\}[\s\S]*?\{% endif %\}", "", txt)
    txt = txt.replace("{{ user.note }}", "")
    # hwid cheap-unlimited-form: single device row (inner guard already ghost-false)
    txt = re.sub(
        r"\{% if user\.hwid_limit == 0 %\}\u0646\u0627\u0645\u062d\u062f\u0648\u062f\{% else %\}\{\{ user\.hwid_limit \}\} \u062f\u0633\u062a\u06af\u0627\u0647\{% endif %\}",
        "{{ len .emails }} \u062f\u0633\u062a\u06af\u0627\u0647", txt)
    return txt


def convert(name):
    path = os.path.join(PG_DIR, f"{name}.html")
    txt = open(path, encoding="utf-8").read()
    if name == "volt":
        txt = volt_specific(txt)
    # consume gauge data-target attributes wholesale first
    txt = re.sub(r'data-target="\{% if user\.data_limit %\}\{\{ \(\(1 - user\.used_traffic[^"]*"',
                 'data-nuc-gauge=""', txt)
    # exact token replacements
    for a, b in TOKEN_ORDERED:
        txt = txt.replace(a, b)
    # jinja control substitutes
    for a, b in JINJA_MAP:
        txt = txt.replace(a, b)
    # leftover eq-0 blocks (non-volt)
    txt = re.sub(r"\{% if user\.hwid_limit == 0 %\}[\s\S]*?\{% else %\}([\s\S]*?)\{% endif %\}",
                 r"\1", txt)
    # title
    txt = re.sub(r"<title>[\s\S]*?</title>", TITLE_GO, txt, count=1)
    # remaining username occurrences -> emails join
    txt = txt.replace("{{ user.username }}", USERNAME_JOIN)
    # attributes accidentally housing a data-nuc placeholder -> normalize
    def _fix_attrs(m):
        before = m.group(0)
        if "data-width" in before and "data-nuc-pct" in before:
            return 'data-nuc-width=""'
        nuc = re.search(r"data-nuc-([a-z-]+)", before)
        if nuc:
            return f'data-nuc-{nuc.group(1)}=""'
        return before
    txt = re.sub(r'[\w-]+="[^"]*<i data-nuc-[^>]*>"', _fix_attrs, txt)
    # html/template hygiene: an action dangling at the end of a start-tag attr
    # (pg sources carry `<div class="val"{{ hwid }}<span ...>` sloppy markup)
    txt = re.sub(r'"(?=\{\{ len \.emails \}\}\s*<)', '">', txt)
    # html/template: JSON-escaped attribute quotes in pg sources (`data-i18n=\"of\"`)
    txt = re.sub(r'(<[^>]*?)data-i18n=\\"([^"\\]*)\\"', r'\1data-i18n="\2"', txt)
    # remove any residual jinja/tokens
    leftovers = []
    for m in re.findall(r"\{\%[^%]*\%\}|\{\{ user\.|data-target=\"\{%", txt):
        if m not in leftovers:
            leftovers.append(m)
    # headless themes: inject std head
    head = ("<!DOCTYPE html>\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            + TITLE_GO + "\n</head>")
    if name in HEADLESS and "<head>" not in txt:
        txt = re.sub(r"(<html[^>]*>)", r"\1\n" + head, txt, count=1)
    # bridge injection before </body>
    if BRIDGE_MARK not in txt and "</body>" in txt:
        txt = txt.replace("</body>", BRIDGE + "\n</body>", 1)
    txt = (MARKER + "\n" + txt) if MARKER not in txt else txt
    return txt, leftovers


def tag_balance(txt):
    tags = re.findall(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\"[^\"]*\"|'[^']*'|[^'\"<>])*?)(/?)>", txt)
    depth = {}
    for close, tag, attrs, selfclose in tags:
        if selfclose or tag in ("br", "img", "input", "meta", "link", "hr", "wbr"):
            continue
        depth.setdefault(tag, 0)
        if close:
            depth[tag] -= 1
        else:
            depth[tag] += 1
    bad = {k: v for k, v in depth.items() if v != 0}
    return bad


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    issues = []
    for path in sorted(glob.glob(os.path.join(PG_DIR, "*.html"))):
        name = os.path.basename(path)[:-5]
        txt, leftovers = convert(name)
        out = os.path.join(OUT_DIR, name, "index.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w", encoding="utf-8").write(txt)
        bad = tag_balance(txt)
        flags = []
        if leftovers:
            flags.append("LEFTOVER:" + str(leftovers))
        if bad:
            flags.append("TAGBAL:" + str(bad))
        if "{{ range" not in txt:
            flags.append("NO-RANGE")
        if BRIDGE_MARK not in txt:
            flags.append("NO-BRIDGE")
        if "demo.example.com" in txt:
            flags.append("DEMO")
        if "nucsub" in txt:
            flags.append("NUCSUB")
        if "{{ user." in txt or "{%" in txt:
            flags.append("RAW-JINJA")
        status = "OK" if not flags else "WARN: " + " ".join(flags)
        print(f"  {name}: {status}")
        if flags:
            issues.append((name, flags))
    print(f"\noutput: {OUT_DIR}  themes={len(glob.glob(os.path.join(OUT_DIR,'*')))}")
    if issues:
        print("ISSUES:")
        for n, f in issues:
            print("  ", n, f)


if __name__ == "__main__":
    main()