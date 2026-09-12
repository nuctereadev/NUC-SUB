#!/usr/bin/env python3
"""Authoritative inventory of remaining demo literals across all themes.

Scans every pasarguard theme (*.html) and every 3x-ui theme (themes/*/index.html)
for hard-coded demo numbers (used/remain/total/percent/dates/traffic) that should
be template variables, printing per-file the exact literal + line + surrounding
context (trimmed). Used to drive the dynamizer and to verify a clean end state.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG = os.path.join(REPO, "pasarguard-themes", "subscription")
XUI = os.path.join(REPO, "themes")

LITERALS = re.compile(
    r"(2026-\d\d-\d\d(?: \d\d:\d\d:\d\d)?|"
    r"43\.75|43\.8|56\.25|56\.2|100(\.0)?|"
    r">\s*43\s*%\s*<|>\s*43\s*<)", re.DOTALL
)

def has_tpl_used(txt):
    return "{{ user.used_traffic" in txt or "{{ .used }}" in txt or "NUC_D" in txt

def scan(paths, kind):
    for p in sorted(paths):
        with open(p, encoding="utf-8") as f:
            lines = f.readlines()
        hits = []
        for ln, line in enumerate(lines, 1):
            for m in LITERALS.finditer(line):
                lit = m.group(0).strip()
                st = max(0, m.start() - 40)
                ctx = line[st:m.end() + 40].strip()
                hits.append(f"    L{ln} {lit!r:26} ...{ctx}")
        if hits:
            name = os.path.basename(p)
            if kind == "xui":
                name = os.path.basename(os.path.dirname(p))
            print(f"## {kind} {name}")
            for h in hits[:14]:
                print(h)
            if len(hits) > 14:
                print(f"    ... ({len(hits) - 14} more)")

def main(which):
    if which in ("pg", "all"):
        scan([os.path.join(PG, f) for f in os.listdir(PG) if f.endswith(".html")], "pg")
    if which in ("xui", "all"):
        scan([os.path.join(XUI, d, "index.html") for d in os.listdir(XUI) if os.path.isdir(os.path.join(XUI, d))], "xui")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")