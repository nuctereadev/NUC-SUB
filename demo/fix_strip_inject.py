# -*- coding: utf-8 -*-
"""Repair defects introduced by the first add_xui_meta.py run:

  1. the .nuc-strip block was injected in the MIDDLE of an opening tag
     (e.g. `<div <style>...`); move it to just after the container's full
     opening tag;
  2. RE_STATIC_NOTE left a duplicated class attr in emerald;
  3. RE_STATIC_NOTE left a `</div>` closing a `<span>` in jade;
  4. note callouts using `class="callout-text"` (or any callout container)
     that still echo `.announce` now render `.note`;
  5. jade got a duplicate note chip (it has a native footer-note).

Idempotent. Run:  py -X utf8 demo/fix_strip_inject.py
"""
import io
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES = os.path.join(REPO, "themes")


def fix_anchor_split(html):
    # `<div <style>\n.nuc-strip{...}</style><div class="nuc-strip">...</div> class="config-list...">`
    pat = re.compile(
        r"((?:<[a-z][a-z0-9]*)\s?)"
        r"(<style>\s*\.nuc-strip.*?</div>\s*)"
        r"(class=[\"'][^\"']*[\"'][^>]*>)",
        re.S,
    )

    def repl(m):
        return m.group(1) + m.group(3) + "\n" + m.group(2)

    out = pat.sub(repl, html, count=1)
    # in case the style was on its own line and the partial open tag is a bare `<div `:
    out = re.sub(
        r"(<[a-z][a-z0-9]*)\n(<style>\s*\.nuc-strip.*?</div>\s*\n?)"
        r"(class=[\"'][^\"']*[\"'][^>]*>)",
        lambda g: g.group(1) + " " + g.group(3).rstrip() + "\n" + g.group(2),
        out,
        count=1,
        flags=re.S,
    )
    return out


def fix_dup_class(html):
    return re.sub(
        r'class="([^"]+)"\s+class="\1"', r'class="\1"', html, count=1
    )


def fix_span_div(html):
    # a `</div>` that closes a `<span ...>` (RE_STATIC_NOTE injected '</div>')
    return re.sub(
        r"(<span[^>]*?class=\"[^\"]*callout-text[^\"]*\"[^>]*>\{\{ if \.note \}\}\{\{ \.note \}\}\{\{ end \}\})</div>",
        r"\1</span>",
        html,
        count=1,
    )


def callout_announce_to_note(html):
    # inside any element whose class contains 'callout', turn the .announce echo
    # into the .note echo (parity with the pasarguard note banner).
    pat = re.compile(
        r"(<[a-z][a-z0-9]*[^>]*class=\"[^\"]*callout[^\"]*\"[^>]*>.*?)"
        r"(\{\{\s*if\s+\.announce\s*\}\}\s*\{\{\s*\.announce\s*\}\}\s*\{\{\s*end\s*\}\})",
        re.S,
    )

    def repl(m):
        return m.group(1) + "{{ if .note }}{{ .note }}{{ end }}"

    return pat.sub(repl, html)


NOTE_CHIP = (
    '{{ if .note }}<div class="nuc-chip"><b>یادداشت:</b><span>{{ .note }}</span></div>{{ end }}'
)


def drop_note_chip(html):
    return html.replace(NOTE_CHIP, "")


def load(p):
    return io.open(p, encoding="utf-8").read()


def save(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def main():
    themes = sorted(
        d for d in os.listdir(THEMES) if os.path.isdir(os.path.join(THEMES, d))
    )
    changed = []
    for theme in themes:
        path = os.path.join(THEMES, theme, "index.html")
        html = load(path)
        orig = html
        before = html
        html = fix_anchor_split(html)
        html = fix_dup_class(html)
        html = fix_span_div(html)
        html = callout_announce_to_note(html)
        if theme == "jade":
            html = drop_note_chip(html)
        if html != before:
            save(path, html)
            marks = []
            if html != orig and "<style>\n.nuc-strip" in html and "class=\"nuc-strip\"" in html:
                pass
            changed.append(
                (theme, "anchor-split" if fix_anchor_split(orig) != orig else "",)
            )
            changed[-1] = (
                theme,
                ",".join(
                    t
                    for t in (
                        "anchor" if "<style>\n.nuc-strip" in html and html.find("<style>") < html.find("class=\"nuc-strip\"") else "",
                        "dup-class" if "class=\"callout-text\" class=" in html else "",
                        "note-chip-removed" if theme == "jade" else "",
                    )
                    if t
                ),
                # count of announce tokens left inside callouts
                len(re.findall(r"callout[^\"]*\"[^>]*>\s*\{\{ if \.announce \}\}", html)),
            )
    print("themes changed: %d" % len(changed))
    for c in changed:
        print("  %-12s %s leftover_announce_in_callouts=%d" % c)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())