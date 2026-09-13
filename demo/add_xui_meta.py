#!/usr/bin/env python3
"""Wire real per-user data into every 3x-ui theme so the Sanaei panel renders the
same information as the PasarGuard themes:

  * note callouts that currently echo `.announce` (or static demo copy) now render
    `{{ if .note }}{{ .note }}{{ end }}`;
  * device-limit rows that currently show `{{ len .emails }}` now show `{{ .hwidLimit }}`
    (gracefully falling back to the email count when the field is absent);
  * `@@TG_CHANNEL@@` telegram buttons in the shared "minimal-family" themes are bound
    to `.subSupportUrl` so they actually work on a real panel;
  * a small `.nuc-strip` component covers whichever of note/device-limit/telegram the
    theme does not already render natively.

Idempotent: a theme that already contains `.nuc-strip` is skipped.

Run:  py -X utf8 demo/add_xui_meta.py
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES = os.path.join(REPO, "themes")

SKIP = {"volt"}  # volt already renders note + device-limit + telegram natively

STRIP_CSS = """<style>
.nuc-strip{display:flex;flex-direction:column;gap:8px;margin:14px 0;width:100%}
.nuc-chip{display:flex;align-items:center;gap:8px;padding:10px 14px;border-radius:var(--radius,12px);background:var(--surface,var(--card,var(--bg,#131218)));border:1px solid var(--border,var(--line,#ffffff1f));color:var(--text,var(--text-primary,var(--fg,#e6e6eb)));font-size:13px;line-height:1.6;text-decoration:none;word-break:break-word;box-sizing:border-box}
.nuc-chip b{color:var(--accent,var(--neon-purple,var(--primary,#8b5cf6)));font-weight:700;white-space:nowrap}
.nuc-chip .nuc-tg{font-weight:700;color:var(--accent,var(--neon-purple,var(--primary,#8b5cf6)));text-decoration:none}
</style>"""


def strip_markup(note, device, tg):
    parts = []
    if note:
        parts.append(
            '{{ if .note }}<div class="nuc-chip"><b>یادداشت:</b><span>{{ .note }}</span></div>{{ end }}'
        )
    if device:
        parts.append(
            '{{ if .hwidLimit }}<div class="nuc-chip"><b>محدودیت دستگاه:</b><span>{{ .hwidLimit }} دستگاه</span></div>{{ end }}'
        )
    if tg:
        parts.append(
            '{{ if .subSupportUrl }}<a class="nuc-chip" href="{{ .subSupportUrl }}" target="_blank" rel="noopener"><b class="nuc-tg">کانال تلگرام</b><span style="direction:ltr;unicode-bidi:embed">{{ .subSupportUrl }}</span></a>{{ end }}'
        )
    return '<div class="nuc-strip">' + "".join(parts) + "</div>\n"


RE_NOTE_TOKEN = re.compile(
    r"\{\{\s*if\s+\.announce\s*\}\}\s*\{\{\s*\.announce\s*\}\}\s*\{\{\s*end\s*\}\}"
)
RE_STATIC_NOTE = re.compile(r'data-i18n="note_text">.{0,320}?</div>', re.S)
RE_DEV_LABEL = re.compile(r'data-i18n="device_limit"')
RE_LEN_EMAILS = re.compile(r"\{\{\s*len\s+\.emails\s*\}\}")
RE_BROKEN_VALUE = re.compile(r'class="value"\{\{')
RE_NOTE_ANNOUNCE = re.compile(r'class="callout[^>"]*\bnote[^"]*"')

CONFIG_ANCHORS = [
    'class="configs-header"',
    'class="configs-one"',
    'class="configs-grid"',
    'class="configs-list"',
    'class="config-grid',
    'class="config-list',
    'class="links-head"',
    'class="links-',
    'class="config',
    'class="wrapper">',
]


def config_anchor(body):
    best = None
    for pat in CONFIG_ANCHORS:
        i = body.find(pat)
        if i != -1 and (best is None or i < best):
            best = i
    if best is None:
        return None
    # walk back to the start of the enclosing tag so the strip is NOT injected
    # inside a partially-open <div class="..."> (which would break that element)
    j = best
    while j > 0 and body[j] != "<":
        j -= 1
    if j > 0 and body[j] == "<" and body[j + 1 : j + 2] != "/":
        return j
    return best


def fix_note_callouts(body):
    """Anything inside a note callout that echoes .announce (or static copy) -> .note."""
    out = body
    pos = 0
    while pos < len(out):
        m = RE_NOTE_ANNOUNCE.search(out, pos)
        if not m:
            break
        i = m.start()
        nm = RE_NOTE_TOKEN.search(out, i, i + 1600)
        if nm:
            repl = "{{ if .note }}{{ .note }}{{ end }}"
            out = out[: nm.start()] + repl + out[nm.end() :]
            pos = i + 1
        else:
            pos = i + 1
    out = RE_STATIC_NOTE.sub(
        lambda g: "class=\"callout-text\">{{ if .note }}{{ .note }}{{ end }}</div>",
        out,
        count=1,
    )
    # remove stale dict pointer if it survived on other elements
    out = out.replace('data-i18n="note_text"', "")
    return out


def wire_device_rows(body):
    out = body
    pos = 0
    while pos < len(out):
        lab = RE_DEV_LABEL.search(out, pos)
        if not lab:
            break
        vm = RE_LEN_EMAILS.search(out, lab.end(), lab.end() + 600)
        if vm:
            repl = "{{ if .hwidLimit }}{{ .hwidLimit }}{{ else }}{{ len .emails }}{{ end }}"
            out = out[: vm.start()] + repl + out[vm.end() :]
            pos = vm.end()
        else:
            pos = lab.start() + 1
    out = RE_BROKEN_VALUE.sub('class="value">{{', out)
    return out


def bind_tg_channel(html):
    out = html.replace(
        '"@@TG_CHANNEL@@"',
        '"{{ if .subSupportUrl }}{{ .subSupportUrl }}{{ end }}"',
    )
    out = out.replace(
        "'@@TG_CHANNEL@@'",
        "'{{ if .subSupportUrl }}{{ .subSupportUrl }}{{ end }}'",
    )
    return out


def main():
    themes = sorted(
        d for d in os.listdir(THEMES) if os.path.isdir(os.path.join(THEMES, d))
    )
    changed = []
    skipped = []
    for theme in themes:
        path = os.path.join(THEMES, theme, "index.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        if ".nuc-strip" in html:
            skipped.append((theme, "already processed"))
            continue
        if theme in SKIP:
            skipped.append((theme, "skip-list"))
            continue

        html = bind_tg_channel(html)

        hold = html.split("<body", 1)
        body = hold[1] if len(hold) == 2 else ""
        body = fix_note_callouts(body)
        body = wire_device_rows(body)

        note_native = bool(
            re.search(
                r'class="callout note"|callout-note|data-i18n="note_text"|class="callout-text"|footer-note',
                body,
            )
        )
        device_native = bool(RE_DEV_LABEL.search(body))
        tg_native = bool(re.search(r"tgBtn|@@TG_CHANNEL@@", body))

        chips = strip_markup(
            note=not note_native, device=not device_native, tg=not tg_native
        )

        anchor = config_anchor(body)
        if anchor is not None:
            body = body[:anchor] + STRIP_CSS + chips + body[anchor:]
        else:
            body = body.replace("</body>", STRIP_CSS + chips + "</body>")

        html = hold[0] + "<body" + body

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        changed.append(
            f"{theme}: note={not note_native}, device={not device_native}, tg={not tg_native}, anchor={'y' if anchor is not None else 'fallback'}"
        )

    print("\n".join(changed))
    print(f"\nchanged={len(changed)}  skipped={len(skipped)}")
    for s in skipped:
        print("  skip:", s[0], "-", s[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())