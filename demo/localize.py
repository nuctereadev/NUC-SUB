#!/usr/bin/env python3
"""
NUC-SUB dependency localization.

Removes every external runtime dependency from the subscription templates so the
whole project renders and functions with the network disabled:

  * Google Fonts <link>/preconnect  -> stripped
  * jsDelivr (Vazirmatn @font-face) -> stripped
  * Tailwind Play CDN script        -> replaced with an inlined, precompiled
                                       Tailwind build (preflight + utilities)
  * api.qrserver.com QR images      -> replaced with a local qrcode call
                                       (window.NucQR -> data:image)
  * remote font names               -> swapped to the locally embedded IranSansX
  * IranSansX (Regular + Bold)      -> inlined as base64 @font-face

Runs for every theme in pasarguard-themes/subscription/ and themes/*/index.html.

Usage:  python3 demo/localize.py          # localize 3x-ui themes (pasarguard
                                         # themes are localized via the converter)
"""
import base64
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ASSETS = os.path.join(REPO, "assets", "fonts", "iran-sans-x")
QR_LIB = os.path.join(HERE, "qrcode-lib.js")
TAILWIND_CSS = os.path.join(HERE, "tailwind", "core.css")

FONT_FILES = {
    400: ("IRANSansX-Regular.woff2", "IranSansX"),
    700: ("IRANSansX-Bold.woff2", "IranSansX"),
}

# Quoted font names to remap to the local IranSansX family.
FONT_REMAP = [
    "'Vazirmatn'",
    '"Vazirmatn"',
    "'DM Sans'",
    '"DM Sans"',
    "'Sora'",
    '"Sora"',
    "'Space Grotesk'",
    '"Space Grotesk"',
    "'Urbanist'",
    '"Urbanist"',
    "'Inter'",
    '"Inter"',
]

QR_API = re.compile(
    r"""([\"']https://api\.qrserver\.com[^\"']*&data=[\"'])\s*\+\s*([^;\r\n]+);?"""
)

TAILWINDCSS = re.compile(
    r"<(?:script|link)\b[^>]*\bcdn\.tailwindcss[^>]*>.*?</(?:script|link)>",
    re.S,
)


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def fontface_style():
    """Inline @font-face block (IranSansX 400 + 700) as base64 data URIs."""
    blocks = []
    for weight, (fn, fam) in FONT_FILES.items():
        data = _b64(os.path.join(ASSETS, fn))
        blocks.append(
            "\n@font-face{font-family:'%s';font-style:normal;font-weight:%d;"
            "font-display:swap;src:url(data:font/woff2;base64,%s) format('woff2')}"
            % (fam, weight, data)
        )
    return (
        "<style id=\"nucFonts\" data-nuc=\"local-fonts\">\n"
        "/* nuc-local fonts: IranSansX 400/700 embedded (offline) */"
        + "".join(blocks)
        + "\n</style>"
    )


def qr_helper():
    """Tiny helper used by the swapped local QR calls."""
    return (
        "\n<script>\n"
        "window.nucQrDataURL=function(t){var Q=window.NucQR,d;if(!Q)return '';"
        "try{d=decodeURIComponent(String(t||''));}catch(e){d=String(t||'');}"
        "if(!d)return '';try{var q=Q(0,'L');q.addData(d);q.make();"
        "return q.createDataURL(4,6);}catch(e){return ''}};\n"
        "</script>\n"
    )


def wrap_qr_lib():
    lib = open(QR_LIB, encoding="utf-8").read()
    return (
        "(function(){\n" + lib + "\n;if(typeof window!=='undefined'){window.NucQR=qrcode;}\n})();\n"
    )


def strip_external(html):
    """Remove remote <link>/<script> references (Google Fonts, jsDelivr ...).
    Position-agnostic on purpose: some Approved drafts put the whole <head> on
    one physical line, so line-anchored regexes are not enough."""
    html = re.sub(
        r'<link\b(?=[^>]*\bhref=[\"\']https?://)[^>]*>', "", html
    )
    return html


def swap_font_names(html):
    for name in FONT_REMAP:
        html = html.replace(name, "'IranSansX'")
    return html


def swap_qrserver(html):
    return QR_API.sub(r"nucQrDataURL(\2);", html)


def swap_tailwind(html):
    if not os.path.isfile(TAILWIND_CSS):
        return html
    with open(TAILWIND_CSS, encoding="utf-8") as f:
        css = f.read()
    block = "<style data-nuc=\"tailwind\">\n" + css + "\n</style>"
    return TAILWINDCSS.sub(block, html)


def inject_fonts(html, style):
    if 'id="nucFonts"' in html:
        return html
    m = re.search(r"<html\b[^>]*>", html)
    if m:
        return html[:m.end()] + "\n" + style + html[m.end():]
    return style + "\n" + html


def inject_helper(html):
    if "nucQrDataURL" in html:
        return html
    js = qr_helper()
    if "</body>" in html:
        return html.replace("</body>", js + "</body>")
    return html + js


def inline_qr_lib(html):
    if "window.NucQR" in html:
        return html
    block = "\n<script data-nuc=\"qrcode-lib\">\n" + wrap_qr_lib() + "\n</script>\n"
    if "</body>" in html:
        return html.replace("</body>", block + "</body>")
    return html + block


def localize_theme(html):
    """Apply every localization step. idempotent."""
    html = strip_external(html)
    html = swap_font_names(html)
    html = swap_qrserver(html)
    html = swap_tailwind(html)
    html = inject_fonts(html, fontface_style())
    html = inline_qr_lib(html)
    html = inject_helper(html)
    return html


def main():
    self_contained_dirs = {"arctic", "cyberpunk", "glass", "matrix", "minimal",
                           "neon", "sunset", "volt"}
    n = 0
    for d in sorted(os.listdir(os.path.join(REPO, "themes"))):
        idx = os.path.join(REPO, "themes", d, "index.html")
        if not os.path.isfile(idx):
            continue
        if d in self_contained_dirs:
            print(f"  skip (already self-contained): {d}")
            continue
        with open(idx, encoding="utf-8") as f:
            html = f.read()
        out = localize_theme(html)
        if out != html:
            with open(idx, "w", encoding="utf-8") as f:
                f.write(out)
            n += 1
            print(f"  localized {d}  {len(html)}->{len(out)}b")
    print(f"localized {n} themes")


if __name__ == "__main__":
    main()