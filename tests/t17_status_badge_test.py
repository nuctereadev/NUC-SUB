#!/usr/bin/env python3
"""
Guard the injected Pasarguard status badge against three regressions.

The bridge script that NUC-SUB injects into every theme ended with:

    badge.textContent=status;
    badge.removeAttribute('data-i18n');
    var map={active:'#16a34a',limited:'#dc2626',...};
    var c=map[status]||'#16a34a';
    badge.style.color='#fff';badge.style.background=c;badge.style.borderColor=c;

which meant, on a real page:

  * the badge read "active" in English while the rest of the page was Persian,
    because the raw PG enum overwrote the translated string;
  * an #16a34a pill (Tailwind green-600) was pasted onto every theme, including
    volt, gold and abyss, which have no green anywhere in their palette;
  * the inline background/borderColor outranked the theme stylesheet, so the
    badge also lost the theme's shape and padding.

This test asserts the fixed behaviour so a rebuild cannot silently reintroduce
it. It is a source-level check on purpose: these strings live inside a <script>
body and cannot be evaluated without a browser, but the three regressions are
all textual.

Also verifies the Persian labels are stored as literal UTF-8. An earlier
revision emitted them as JS \\xNN escapes inside a <script> body, where escapes
are not interpreted, and the page showed 'Ø¡ÙØ§Ù„' instead of 'فعال'.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
THEMES = ROOT / "pasarguard-themes" / "subscription"

themes = sorted(THEMES.glob("*.html"))
if not themes:
    print("FAIL: no themes found under", THEMES)
    sys.exit(1)

failures: list[str] = []

EXPECTED_LABELS = {
    "active": "فعال",
    "on_hold": "نگهداری",
    "limited": "محدود",
    "expired": "منقضی",
    "disabled": "غیرفعال",
}

for p in themes:
    raw = p.read_bytes()
    if b"\r\n" in raw:
        failures.append(f"{p.name}: CRLF line endings")
    src = raw.decode("utf-8")

    # 1. no hardcoded green for the healthy state
    if "var c=map[status]||'#16a34a'" in src:
        failures.append(f"{p.name}: still defaults the status badge to #16a34a")
    if "background=c;badge.style.borderColor=c" in src:
        failures.append(f"{p.name}: still force-colours the badge inline")

    # 2. the raw enum must never be written over the badge
    if "badge.textContent=status;" in src:
        failures.append(f"{p.name}: still overwrites the badge with the raw enum")

    # 3. the labels must be real UTF-8, not \\xNN escapes
    if "\\xd8" in src or "\\u06" in src:
        failures.append(f"{p.name}: Persian labels stored as JS escapes, "
                        f"which render as mojibake in a <script> body")
    m = re.search(r"var nucFa=\{([^}]*)\};", src)
    if not m:
        failures.append(f"{p.name}: no nucFa label map found")
    else:
        body = m.group(1)
        for key, label in EXPECTED_LABELS.items():
            if f"{key}:'{label}'" not in body:
                failures.append(f"{p.name}: label map missing/garbled {key} -> {label}")

    # 4. active must not be recoloured at all
    if not re.search(r"if\(status!=='active'\)\{badge\.textContent", src):
        failures.append(f"{p.name}: `active` no longer keeps the theme's own text")

print(f"checked {len(themes)} Pasarguard themes")

if failures:
    print(f"\nFAIL: {len(failures)} problem(s)")
    for f in failures[:20]:
        print("  -", f)
    if len(failures) > 20:
        print(f"  ... and {len(failures) - 20} more")
    sys.exit(1)

print("PASS  status badge is no longer force-green, and stays translated")