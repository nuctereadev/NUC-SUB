#!/usr/bin/env python3
"""Inject @@BRAND_NAME@@/@@BRAND_LOGO@@ tokens into themes with brand sections.

Idempotent — safe to re-run. Look for the tokens by class name in BODY only.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PG_DIR = os.path.join(REPO, "pasarguard-themes", "subscription")
XUI_DIR = os.path.join(REPO, "themes")

CSS_RULE = (
    "\n    .nuc-brand-logo{display:none!important;max-height:32px;max-width:32px;"
    "object-fit:contain;border-radius:6px;vertical-align:middle;margin-left:6px}"
    "\n    .nuc-brand-logo[src]:not([src='']):not([src='data:;base64,'])"
    "{display:inline-block!important}"
    "\n    .nuc-brand-name{font-size:11px;color:var(--text-secondary,var(--muted,#999));"
    "font-weight:400;margin-top:2px}"
)


def patch_theme(path):
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    original = html

    if 'class="brand-dot"' not in html and 'class="brand-icon"' not in html:
        return False

    # 1. CSS once, before </style>
    if ".nuc-brand-logo" not in html:
        idx = html.rfind("</style>")
        if idx > 0:
            html = html[:idx] + CSS_RULE + "\n  " + html[idx:]

    # 2. Logo img in body (class="nuc-brand-logo" img)
    if 'class="nuc-brand-logo"' not in html:
        m = re.search(r'(<div\s+class="brand-dot"\s*>\s*</div>)', html)
        if m:
            tag = m.group(1) + '\n      <img src="@@BRAND_LOGO@@" alt="" class="nuc-brand-logo">'
            html = html[:m.start()] + tag + html[m.end():]
        else:
            # brand-icon: insert after the closing </div> of the icon
            m = re.search(r'(<div\s+class="brand-icon"[^>]*>\s*.*?</div>)', html, re.S)
            if m:
                tag = '\n      <img src="@@BRAND_LOGO@@" alt="" class="nuc-brand-logo">'
                html = html[:m.end()] + tag + html[m.end():]

    # 3. Brand name line inside brand-text (or replace static brand-name span)
    if '<p class="nuc-brand-name">' not in html and '<span class="nuc-brand-name">' not in html:
        bt = html.find('class="brand-text"')
        if bt >= 0:
            h1 = html.find("</h1>", bt)
            if h1 >= 0:
                nxt = h1 + len("</h1>")
                brand_line = '\n        <p class="nuc-brand-name">@@BRAND_NAME@@</p>'
                html = html[:nxt] + brand_line + html[nxt:]
        else:
            # static brand-name element, e.g. <span class="brand-name">Onyx</span>
            # or <div class="brand-name">Ember</div>
            m = re.search(
                r'(<(?:span|div)\s+class="brand-name"[^>]*>)[^<]*(</(?:span|div)>)', html
            )
            if m:
                html = html[:m.start()] + m.group(1) + "@@BRAND_NAME@@" + m.group(2) + html[m.end():]

    if html != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return True
    return False


def main():
    count = 0
    for fn in os.listdir(PG_DIR):
        if fn.endswith(".html") and patch_theme(os.path.join(PG_DIR, fn)):
            print(f"  patched: {fn}")
            count += 1
    for name in sorted(os.listdir(XUI_DIR)):
        path = os.path.join(XUI_DIR, name, "index.html")
        if os.path.isfile(path) and patch_theme(path):
            print(f"  patched: themes/{name}")
            count += 1
    print(f"\nTotal: {count} theme(s) patched")
    return 0


if __name__ == "__main__":
    sys.exit(main())