#!/usr/bin/env python3
"""
Stop the status badge from being force-green, and stop it losing its translation.

The injected Pasarguard bridge ends with this block in every theme:

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

WHY THIS TOUCHES TWO TREES

The Pasarguard themes exist twice in this repo:

    pasarguard-themes/subscription/   the 33 themes that ship in MANIFEST.sha256
    demo/site/pg/                     the 33 themes served by the demo site

They are separate committed copies, not generated from each other, and an
earlier revision of this fix only rewrote the first one. The bug therefore
survived on the demo site, which is where it was actually reported from. Both
trees are rewritten here, and tests/t17_status_badge_test.py scans the whole
repo so a third copy cannot hide the same bug again.

The 3x-ui trees (build/xui-33/, demo/site/xui/) carry no injected bridge and
are left untouched.

Matching is newline-agnostic and output is written with LF.

Two reasons, both learned the hard way here:

  * pasarguard-themes is manifest-hashed and git-committed, so CRLF in the
    checkout makes the release fail its own MANIFEST.sha256 -- that is what
    broke v2.2.2 (see tools/fix-pg-expire-templates.py).

  * demo/site/pg arrives from a Windows checkout as CRLF, because
    core.autocrlf=true and the fixer had never rewritten those files. An
    LF-only search pattern therefore matched zero blocks in the demo tree while
    the tool cheerfully reported "0 rewritten" and the bug survived. So the
    text is normalised to LF before matching, and CRLF is rejected afterwards
    instead of being assumed absent.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TREES = (
    ROOT / "pasarguard-themes" / "subscription",
    ROOT / "demo" / "site" / "pg",
)

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
    # Persian labels, written as literal UTF-8 (not \xNN escapes: this is a
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

# Patterns that must not survive anywhere in the repository.
FORBIDDEN = (
    "var c=map[status]||'#16a34a'",
    "background=c;badge.style.borderColor=c",
    "badge.textContent=status;",
    "map={active:'#16a34a'",
)


def main() -> int:
    total = 0
    for tree in TREES:
        hits = 0
        n_themes = 0
        for p in sorted(tree.glob("*.html")):
            n_themes += 1
            # normalise first: a Windows checkout hands us CRLF, and an
            # LF-only pattern would silently match nothing
            txt = p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
            if OLD not in txt:
                continue
            hits += txt.count(OLD)
            p.write_bytes(txt.replace(OLD, NEW).encode("utf-8"))
        rel = tree.relative_to(ROOT)
        print(f"  {rel}: {hits} block(s) rewritten across {n_themes} theme(s)")
        total += hits

    print(f"total: {total} block(s) rewritten")

    # verify repo-wide, not just in the two trees we know about
    problems = []
    for p in ROOT.rglob("*.html"):
        if ".git" in p.parts:
            continue
        try:
            s = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        for bad in FORBIDDEN:
            if bad in s:
                problems.append(f"{p.relative_to(ROOT)}: still contains {bad!r}")

    if problems:
        print("ERROR:")
        for x in sorted(set(problems)):
            print("  -", x)
        return 1
    print("verified: the force-green status badge is gone from every .html in the repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())