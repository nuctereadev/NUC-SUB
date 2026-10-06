#!/usr/bin/env python3
"""
Guard the injected Pasarguard status badge against three regressions.

The bridge that NUC-SUB injects into every theme ended with:

    badge.textContent=status;
    badge.removeAttribute('data-i18n');
    var map={active:'#16a34a',limited:'#dc2626',on_hold:'#8b5cf6',...};
    var c=map[status]||'#16a34a';
    badge.style.color='#fff';badge.style.background=c;badge.style.borderColor=c;

which meant, on a real page:

  * the badge read "active" in English while the rest of the page was Persian,
    because the raw PG enum overwrote the translated string;
  * an #16a34a pill (Tailwind green-600) was pasted onto every theme, including
    volt, gold and abyss, which have no green anywhere in their palette;
  * the inline background/borderColor outranked the theme stylesheet, so the
    badge also lost the theme's shape and padding.

This test scans the WHOLE repository rather than a known list of directories.
That is the whole point: the Pasarguard themes are committed twice, once as
pasarguard-themes/subscription/ (shipped in MANIFEST.sha256) and once as
demo/site/pg/ (served by the demo site). The first version of the fix rewrote
only the shipped tree, the bug survived on the demo site, and it was reported
from there. A test that only looked at the directory being fixed would have
passed again.

The 3x-ui trees carry no injected bridge, so they legitimately contain none of
these strings and are covered by the same repo-wide scan.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# both committed copies of the Pasarguard themes
TREES = (
    ROOT / "pasarguard-themes" / "subscription",
    ROOT / "demo" / "site" / "pg",
)

# manifest-hashed tree: CRLF here breaks `nucsub update` on the server
SHIPPED = ROOT / "pasarguard-themes"

FORBIDDEN = {
    "the hardcoded green for the healthy state":
        "var c=map[status]||'#16a34a'",
    "the inline background/borderColor override":
        "background=c;badge.style.borderColor=c",
    "the raw enum written over the badge":
        "badge.textContent=status;",
    "the map that defaults active to green":
        "map={active:'#16a34a'",
}

EXPECTED_LABELS = {
    "active": "فعال",
    "on_hold": "نگهداری",
    "limited": "محدود",
    "expired": "منقضی",
    "disabled": "غیرفعال",
}

failures: list[str] = []
checked = 0

# ---- 1. repo-wide: the bug must not exist anywhere, including a future copy
for p in sorted(ROOT.rglob("*.html")):
    if ".git" in p.parts:
        continue
    try:
        s = p.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        continue
    for why, bad in FORBIDDEN.items():
        if bad in s:
            failures.append(f"{p.relative_to(ROOT)}: {why}")

# ---- 2. per-tree: every theme carries the fix and readable labels
for tree in TREES:
    themes = sorted(tree.glob("*.html"))
    if not themes:
        failures.append(f"{tree.relative_to(ROOT)}: no themes found")
        continue
    for p in themes:
        checked += 1
        src = p.read_bytes().decode("utf-8")

        if "\\xd8" in src or "\\u06" in src:
            failures.append(
                f"{p.relative_to(ROOT)}: Persian labels stored as JS escapes, "
                f"which render as mojibake in a <script> body")

        m = re.search(r"var nucFa=\{([^}]*)\};", src)
        if not m:
            failures.append(f"{p.relative_to(ROOT)}: no nucFa label map found")
        else:
            for key, label in EXPECTED_LABELS.items():
                if f"{key}:'{label}'" not in m.group(1):
                    failures.append(
                        f"{p.relative_to(ROOT)}: label map missing/garbled "
                        f"{key} -> {label}")

        if not re.search(r"if\(status!=='active'\)\{badge\.textContent", src):
            failures.append(
                f"{p.relative_to(ROOT)}: `active` no longer keeps the theme's own text")

# ---- 3. shipped tree must stay LF so the manifest verifies on the server
for p in sorted(SHIPPED.rglob("*")):
    if p.is_file() and b"\r\n" in p.read_bytes():
        failures.append(f"{p.relative_to(ROOT)}: CRLF line endings")

print(f"scanned every .html in the repo; checked {checked} Pasarguard themes "
      f"across {len(TREES)} trees")

if failures:
    uniq = sorted(set(failures))
    print(f"\nFAIL: {len(uniq)} problem(s)")
    for f in uniq[:20]:
        print("  -", f)
    if len(uniq) > 20:
        print(f"  ... and {len(uniq) - 20} more")
    sys.exit(1)

print("PASS  no force-green status badge anywhere; labels are literal UTF-8")