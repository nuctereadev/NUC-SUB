#!/usr/bin/env python3
"""
Convert the AI-generated STATIC Pasarguard theme drafts to real Jinja2 templates
for the PasarGuard panel and add them to the repo.

The Approved drafts are beautifully designed but 100% static. This script:
  * picks each theme name from its <title> / filename,
  * rewrites static quota values -> {{ user.* }} / filters,
  * rewrites the 6 hard-coded config blocks into a {% for link in links %} loop
    (it auto-adapts to per-theme markup: config-item, c-row, cfg, config-card ...),
  * makes percent/progress and count dynamic,
  * writes the result into pasarguard-themes/subscription/<name>.html.

Usage:  python3 demo/convert_approved.py [--dry-run]
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

APPROVED = r"C:\Users\Asus\Downloads\طرح های پروژه قالب\Approved"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)          # <repo root>/demo/.. 
DEST = os.path.join(REPO, "pasarguard-themes", "subscription")

# name -> source file. 'orbit' duplicates amber (same source) — we keep amber and
# drop my earlier orbit version; both map to pasarguard_orbit_theme.html.
BATCH = [
    ("slate",   "deepseek_html_20260909_0ee7e5.html"),   # "Minimal Slate"
    ("aria",    "deepseek_html_20260909_dba864.html"),   # "Pearl"
    ("onyx",    "Qwen_html_20260909_zx4jd9roi.html"),    # "Onyx Dashboard"
    ("ember",   "Qwen_html_20260909_f1atf8qdi.html"),    # "Ember - Subscription"
    ("nova",    "Qwen_html_20260909_4qbyylchp.html"),    # "Nova Dashboard"
    ("graphite","Qwen_html_20260909_0n2nf0i9e.html"),    # "Graphite Dashboard"
    ("zenith",  "Qwen_html_20260909_r4016j27g.html"),    # "Zenith Dashboard"
    ("amber",   "pasarguard_orbit_theme.html"),          # "PasarGuard - Orbit"
    ("command", "pasarguard_command_theme.html"),        # "PasarGuard"
    ("gold",    "pasarguard_premium_minimal_theme.html"),# "PasarGuard premium minimal"
    ("indigo",  "pasarguard_subscription_theme3.html"),  # "PasarGuard subscription 3"
    ("lime",    "pasarguard_compact_theme.html"),        # "PasarGuard compact"
    ("mint",    "pasarguard_simple_chic_theme.html"),    # "PasarGuard simple chic"
    ("olive",   "pasarguard_true_minimal_theme.html"),   # "PasarGuard true minimal"
    ("pulse",   "pasarguard_unlocked_theme.html"),       # "PasarGuard pulse"
    ("teal",    "pasarguard_subscription_theme4.html"),  # "PasarGuard subscription 4"
    # ---- second batch: the remaining unique drafts -> 8 + 33 = 41 PG themes ----
    ("azure",   "deepseek_html_20260909_190a7e.html"),   # "NucSub" (blue/cyan)
    ("cobalt",  "deepseek_html_20260909_228d29.html"),   # "Minimal" (royal blue)
    ("lagoon",  "deepseek_html_20260909_30d6f0.html"),   # "Azure Minimal" (teal)
    ("linen",   "deepseek_html_20260909_8bedf6.html"),   # "Linen" (light dark)
    ("stark",   "deepseek_html_20260909_92ec18.html"),   # "Stark" (deep navy)
    ("copper",  "deepseek_html_20260909_cdb2bf.html"),   # "Copper Slate" (brown)
    ("emerald", "deepseek_html_20260909_edd7df.html"),   # "NucSub Clean" (green)
    ("ocean",   "doubao_html_20260909_181243.html"),     # doubao variant 1
    ("marine",  "doubao_html_20260909_201700.html"),     # doubao variant 2
    ("tide",    "doubao_html_20260909_203422.html"),     # doubao variant 3
    ("abyss",   "doubao_html_20260909_204328.html"),     # doubao variant 4
    ("dusk",    "html lang=fa dir=rtl style=margin0.html"),
    ("prisma",  "pasarguard_subscription_rebuilt.html"), # "Subscription rebuilt"
    ("coal",    "Qwen_html_20260909_ik5a4p1jr.html"),    # Qwen graphite a
    ("chrome",  "Qwen_html_20260909_miyicnbdv.html"),    # Qwen graphite b
    ("steel",   "Qwen_html_20260909_opy5hz04b.html"),    # Qwen graphite c
    ("comet",   "Qwen_html_20260909_x0hgdbmwm.html"),    # "Nova Template" (green)
]

RULES = [
    ("demo.user", "{{ user.username }}"),
    ("43.75 GB", "{{ user.used_traffic | bytesformat }}"),
    ("43,75 GB", "{{ user.used_traffic | bytesformat }}"),
    ("56.25 GB", "{{ (user.data_limit - user.used_traffic) | bytesformat }}"),
    ("56,25 GB", "{{ (user.data_limit - user.used_traffic) | bytesformat }}"),
    ("100.0 GB", "{{ user.data_limit | bytesformat }}"),
    ("100 GB", "{{ user.data_limit | bytesformat }}"),
    ("100.0 GiB", "{{ user.data_limit | bytesformat }}"),
    ("100 GiB", "{{ user.data_limit | bytesformat }}"),
    ("2026-09-20 20:25:02", "{{ user.expire | datetime }}"),
    ("2026-09-20T20:25:02", "{{ user.expire | datetime }}"),
    ("2026-09-20 20:25", "{{ user.expire | datetime }}"),
    ("2026-09-20", "{{ user.expire | datetime }}"),
]

PERCENT_SRCS = [
    r"43\.8%", r"43\.8\s*%", r"44%", r"44\s*%",
]
WIDTH_SRCS = [
    ('data-width="43.8"', 'data-width="{{ (user.used_traffic / user.data_limit * 100) | round(1) }}"'),
    ('data-width="43.8%"', 'data-width="{{ (user.used_traffic / user.data_limit * 100) | round(1) }}"'),
    ('style="--p:43.8"', 'style="--p:{{ (user.used_traffic / user.data_limit * 100) | round(1) }}"'),
]

# Any class-carrying block that wraps a link: config-item / config-card / c-row / cfg / node-card / link-card / list-item ...
LINK_BLOCK = re.compile(
    r'<div class="([a-zA-Z0-9_-]*\b(?:config-item|config-card|c-row|cfg|node-card|link-card|list-item|server)[a-zA-Z0-9_-]*)"'
    r'\s+data-link="[^"]*">.*?</div>',
    re.DOTALL,
)
# Any element that carries data-link: config-item / c-row / cfg / config-card / etc.
LINK_BLOCK_ANY = re.compile(
    r'(?P<pre><(?:div|button|a)\s[^>]*data-link="[^"]*"[^>]*>)',
)


def _find_block_end(html, start):
    """Find the index just after the matching closing tag for the block opened at
    `start`. Handles nested div/button/a tags so we never cut a config card early."""
    depth = 1  # we start right AFTER the already-opened outer tag
    i = start
    while i < len(html):
        lt = html.find("<", i)
        if lt < 0:
            return len(html)
        # end tag?
        if html.startswith("</", lt):
            gt = html.find(">", lt)
            name = html[lt + 2: gt].strip().split()[0]
            if name in ("div", "button", "a"):
                depth -= 1
                if depth == 0:
                    return gt + 1
            i = gt + 1
            continue
        # comment?
        if html.startswith("<!--", lt):
            gt = html.find("-->", lt)
            i = (gt + 3) if gt >= 0 else len(html)
            continue
        # opening tag
        gt = html.find(">", lt)
        tag = html[lt + 1: gt]
        name = tag.split()[0].lstrip("!") if tag.split() else ""
        if name.strip("/") in ("div", "button", "a") and not name.startswith("/"):
            depth += 1
        i = gt + 1
    return len(html)


def rewrite_link_blocks(html):
    """Replace every hard-coded per-link block (data-link="...") with a single
    {% for link in links %} iteration. The loop body mirrors the FIRST block's
    full markup. Badge/name/meta text is cleared (the theme fills it via a small
    injected JS that derives protocol + decoded fragment straight from data-link),
    so the cards render correctly with any set of links."""
    blocks = []
    for m in LINK_BLOCK_ANY.finditer(html):
        end = _find_block_end(html, m.end())
        if end > m.end():
            blocks.append((m, end))
    if not blocks:
        return html, False

    m0, _ = blocks[0]
    body = html[m0.end():blocks[0][1]]
    # build a clean opening tag: keep all attributes before the final ">",
    # strip the old data-link and re-insert the Jinja variable before ">".
    opener = re.sub(r'\s+data-link="[^"]*"', "", m0.group("pre")).rstrip(">")
    opener = opener.rstrip() + ' data-link="{{ link }}">'

    # blank every text node that holds the hard-coded protocol label/name so JS
    # can rewrite it from the link; keep the HTML skeleton and classes intact.
    body = re.sub(r">(?:[^<>{}]|{{[^{}]*}})+<", "><", body)

    loop = (
        "{% for link in links %}\n"
        + opener + body.rstrip() + "\n"
        "{% endfor %}\n"
    )
    start = blocks[0][0].start()
    end = blocks[-1][1]
    html = html[:start] + loop + html[end:]

    # inject one small script that fills badge + name + protocol from data-link,
    # appended right before </body> (works with every markup variant).
    js = """
<script>
(function(){
  function dec(s){try{return decodeURIComponent(s);}catch(e){return s;}}
  var cards=document.querySelectorAll('[data-link]');
  cards.forEach(function(card,i){
    var link=(card.getAttribute('data-link')||'').replace(/&amp;/g,'&');
    var m=link.match(/^([a-z0-9]+):\\/\\//i);
    var proto=m?m[1].toLowerCase():'unknown';
    var frag=link.split('#');
    var name=frag.length>1&&frag[1]?dec(frag[1]):(i18n&&i18n.configN?i18n.configN:'Config')+' '+(i+1);
    var badge=card.querySelector('.proto-badge,.c-badge,.config-protocol-icon,.link-badge,.protocol-badge');
    if(badge){
      badge.className=badge.className.split(' ')[0]+' proto-'+proto;
      if(!badge.textContent.trim()) badge.textContent=proto.slice(0,4).toUpperCase();
    }
    var nameEl=card.querySelector('.config-name,.c-name,.cfgname,.link-name,.node-name,.config-name,.cfg-nm');
    if(nameEl) nameEl.textContent=name;
    var protoEl=card.querySelector('.config-meta span,.c-meta span,.cfgmeta em,.config-protocol-text,.link-type,.cfg-meta span');
    if(protoEl&&!protoEl.textContent.trim()) protoEl.textContent=proto.toUpperCase();
  });
})();
</script>
"""
    if "</body>" in html:
        html = html.replace("</body>", js + "</body>")
    else:
        html += "\n" + js
    return html, True


def rewrite_statics(html):
    for a, b in RULES:
        html = html.replace(a, b)
    for p in PERCENT_SRCS:
        html = re.sub(p, "{{ (user.used_traffic / user.data_limit * 100) | round(1) }}%", html)
    for a, b in WIDTH_SRCS:
        html = html.replace(a, b)
    # live link-count (markup varies: mod-count / configs-count / count)
    html = re.sub(r'class="(mod-count|configs-count|count|badge-count)"[^>]*>\d+',
                  r'class="\1" >{{ links | length }}', html)
    return html


def add_dynamic_js(html):
    """Each draft already wires copy/QR to document.querySelectorAll('.config-item')
    or similar. If the draft reads a specific selector, keep it. We just make sure
    the QR first-node guard exists (avoid null on empty link list)."""
    if "if(!links.length)" in html or "if (links.length)" in html:
        return html
    # safe default: guard before QR
    html = html.replace(
        "const first = document.querySelector('.config-item');",
        "const first = document.querySelector('.config-item'); if(!first) return;",
    )
    return html


def main():
    dry = "--dry-run" in sys.argv
    os.makedirs(DEST, exist_ok=True)
    print(f"approved : {APPROVED}")
    print(f"dest     : {DEST}" + ("  [DRY-RUN]" if dry else ""))
    for name, src in BATCH:
        sp = os.path.join(APPROVED, src)
        if not os.path.isfile(sp):
            print(f"  ?? missing {src}")
            continue
        with open(sp, encoding="utf-8", errors="replace") as f:
            html = f.read()
        out = rewrite_statics(html)
        out, found = rewrite_link_blocks(out)
        out = add_dynamic_js(out)
        dest = os.path.join(DEST, f"{name}.html")
        if dry:
            print(f"  [dry] {name:<10} <- {src:<45} links_loop={found} {len(html)}->{len(out)}b")
        else:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(out)
            print(f"  wrote {name}.html  links_loop={found}  {len(out)}b")


if __name__ == "__main__":
    main()