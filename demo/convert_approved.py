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
    r'(?P<pre><(?:div|button|a)\s[^>]*data-link="[^"]*"[^>]*>)'
    r"(?P<body>.*?)</(?:div|button|a)>",
    re.DOTALL,
)


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


def rewrite_link_blocks(html):
    """Replace every hard-coded per-link <div class="X" data-link="...">...</div>
    with a single {% for link in links %} iteration. Since the JS of each draft
    reads data-link (for copy/QR), we can fill the visible name/protocol via a
    small JS snippet appended before </body> if the template does not already."""
    it = LINK_BLOCK_ANY.finditer(html)
    blocks = list(it)
    if not blocks:
        return html, False
    # Use the FIRST block's inner structure as the loop body (strip its own data-link attr).
    first = blocks[0]
    body = first.group("body")
    # blank the static name/protocol text so JS fills them
    body = re.sub(r'([-]><)?[^<>]*</div>', lambda m: m.group(0), body)
    loop = ("{% for link in links %}\n"
            f"<div class=\"{re.search(r'class=\"([^\"]+)\"', first.group('pre')).group(1)}\" data-link=\"{{{{ link }}}}\">"
            f"{body}</div>\n"
            "{% endfor %}\n")
    # replace from first block start to last block end
    start = blocks[0].start()
    end = blocks[-1].end()
    html = html[:start] + loop + html[end:]
    return html, True


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