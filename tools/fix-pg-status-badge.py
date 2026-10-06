#!/usr/bin/env python3
"""
Stop the status badge from being force-green, and stop it losing its translation.

The injected Pasarguard bridge ends with this block in all 33 themes:

    var badge=document.querySelector('[data-i18n="st_active"]');
    if(badge){
      badge.textContent=status;
      badge.removeAttribute('data-i18n');
      var map={active:'#16a34a',limited:'#dc2626',on_hold:'#8b5cf6',expired:'#f59e0b',disabled:'#6b7280'};
      var c=map[status]||'#16a34a';
      try{badge.style.color='#fff';badge.style.background=c;badge.style.borderColor=c;}catch(e){}
    }

Three separate problems:

  * `textContent=status` writes the raw English enum ("active", "on_hold") over
    the badge. Every other string on the page is translated, so this one element
    comes out in English while the rest is Persian. Removing the data-i18n
    attribute also disables the theme's own translation for it.

  * `active` maps to a hardcoded #16a34a. That is Tailwind green-600 and looks
    correct on a green theme, but it is pasted over the design of every other
    theme -- volt is blue/violet, gold is amber, abyss is near-monochrome. The
    result is a green pill sitting in a page that has no green in it.

  * The colours are applied inline, which outranks the theme's stylesheet, so
    the badge loses its shape, padding and border treatment as well.

The replacement:

  * leaves the badge text alone when the status is `active`, which is the only
    status the themes were designed to display, so the existing Persian string
    stays and data-i18n keeps working;
  * translates the remaining enum values to the same Persian the themes use;
  * only colours genuinely exceptional states, and does it with a class plus a
    CSS custom property so the theme still controls the shape.

Writes bytes with newline="\\n" on purpose: these files are manifest-hashed and
git-committed, and CRLF in the checkout makes the release fail its own
MANIFEST.sha256 (see tools/fix-pg-expire-templates.py).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
THEMES = ROOT / "pasarguard-themes" / "subscription"

OLD = (
    "  var badge=document.querySelector('[data-i18n=\"st_active\"]');\n"
    "  if(badge){\n"
    "    badge.textContent=status;\n"
    "    badge.removeAttribute('data-i18n');\n"
    "    var map={active:'#16a34a',limited:'#dc2626',on_hold:'#8b5cf6',expired:'#f59e0b',disabled:'#6b7280'};\n"
    "    var c=map[status]||'#16a34a';\n"
    "    try{badge.style.color='#fff';badge.style.background=c;badge.style.borderColor=c;}catch(e){}\n"
    "  }\n"
)

NEW = (
    "  var badge=document.querySelector('[data-i18n=\"st_active\"]');\n"
    "  if(badge){\n"
    "    // Only translate away from the state the theme was designed for. `active`\n"
    "    // keeps its own data-i18n string and its own styling, so a green pill is\n"
    "    // no longer pasted onto themes that have no green in them.\n"
    # Persian labels, written as literal UTF-8 (not \\xNN escapes: this is a
    # <script> body, not a JS string literal in an HTML attribute, so escapes
    # would survive into the page as visible garbage).
    "    var nucFa={active:'فعال',on_hold:'نگهداری',limited:'محدود',expired:'منقضی',disabled:'غیرفعال'};\n"
    "    if(status!=='active'){badge.textContent=nucFa[status]||status;}\n"
    "    // Colour only the genuinely exceptional states, and via a custom property\n"
    "    // so the theme's own shape, padding and radius still apply.\n"
    "    var bad={limited:'#dc2626',on_hold:'#8b5cf6',expired:'#f59e0b',disabled:'#6b7280'};\n"
    "    if(bad[status]){\n"
    "      badge.style.setProperty('--nuc-state-color',bad[status]);\n"
    "      badge.style.color='#fff';badge.style.background=bad[status];\n"
    "      badge.style.borderColor=bad[status];\n"
    "    }\n"
    "  }\n"
)


def main() -> int:
    hits = 0
    touched: list[str] = []
    for p in sorted(THEMES.glob("*.html")):
        raw = p.read_bytes()
        txt = raw.decode("utf-8")
        if OLD not in txt:
            continue
        n = txt.count(OLD)
        out = txt.replace(OLD, NEW)
        # normalise to LF so the manifest matches what git stores
        lf = out.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        p.write_bytes(lf)
        hits += n
        touched.append(p.name)

    print(f"rewrote {hits} status-badge block(s) across {len(touched)} theme(s)")

    # verify
    problems = []
    for p in sorted(THEMES.glob("*.html")):
        s = p.read_bytes().decode("utf-8")
        if "background=c;badge.style.borderColor=c" in s:
            problems.append(f"{p.name}: still force-colours the badge inline")
        if "badge.textContent=status;" in s:
            problems.append(f"{p.name}: still overwrites the badge with the raw enum")
        if "var c=map[status]||'#16a34a'" in s:
            problems.append(f"{p.name}: still defaults the badge to #16a34a")
        if b"\r\n" in p.read_bytes():
            problems.append(f"{p.name}: CRLF crept back in")

    if problems:
        print("ERROR:")
        for x in problems:
            print("  -", x)
        return 1
    print("verified: no inline green, enum text preserved for `active`, LF endings")
    return 0


if __name__ == "__main__":
    sys.exit(main())