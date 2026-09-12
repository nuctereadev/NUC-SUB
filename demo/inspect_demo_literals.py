#!/usr/bin/env python3
"""Report every demo-dataset literal occurrence in the static 3x-ui themes.

Prints theme:line: <40 chars before> <<literal>> <40 chars after> for each of the
known demo values so the dynamization rules can target real display contexts.
"""
import glob, os, re, sys

STATIC = (
    "amber-dark", "amethyst", "azure", "copper", "cyber-lime", "emerald",
    "forge", "graphite", "indigo-dark", "jade", "lagoon", "linen", "magenta",
    "navy", "neon-emerald", "nova", "onyx", "pearl", "royal", "sapphire",
    "slate", "terracotta", "violet",
)

PATS = {
    "USED": re.compile(r"43\.75"),
    "REMAIN": re.compile(r"56\.25"),
    "TOTAL": re.compile(r"(?<![0-9.])100(?![0-9.])"),
    "DATE": re.compile(r"2026[-/.]0?9[-/.]20(?:[- ][0-9:]+)?"),
    "TOTAL_BYTES": re.compile(r"(?<![0-9])100(?: ?GB)", re.I),
    "PCT": re.compile(r"4[34]\.?[0-9]?\s*(?:%|برصد|درصد)"),
    "DAYS": re.compile(r"[۰-۹0-9]+\s*روز باقی"),
}

themes_dir = os.path.join(os.path.dirname(__file__), "..", "themes")

found = {k: [] for k in PATS}
for name in STATIC:
    path = os.path.join(themes_dir, name, "index.html")
    if not os.path.isfile(path):
        continue
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        for key, rx in PATS.items():
            for m in rx.finditer(line):
                lo, hi = max(0, m.start() - 42), min(len(line), m.end() + 42)
                found[key].append(f"{name}:{i}: ...{line[lo:hi].strip()}...")

for key in ("USED", "REMAIN", "TOTAL", "DATE", "TOTAL_BYTES", "PCT", "DAYS"):
    hits = found[key]
    print(f"\n===== {key} ({len(hits)} occurrences) =====")
    for h in hits[:40]:
        print(h)
    if len(hits) > 40:
        print(f"... (+{len(hits) - 40} more)")
    five = [h for h in hits if "الق" in h]
    if five:
        print(f"    [note] looks-like-total-domain: {len(five)}")