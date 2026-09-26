#!/usr/bin/env python3
"""Apply the verified Task 11 fixes to ONE theme, then report exactly what
changed. Deliberately one theme per invocation: the requirements forbid a bulk
fix that rewrites every theme at once, and every theme is afterwards verified on
its own through the real renderer.

usage: t11_fix.py <sanaei|pasarguard> <theme>
"""
import os
import re
import sys

PATHS = {
    "sanaei": "themes/%s/index.html",
    "pasarguard": "pasarguard-themes/subscription/%s.html",
}

HIDDEN_OLD = ('<i data-nuc-used style="display:none">{{ .used }}</i>'
              '<i data-nuc-limit style="display:none">{{ .total }}</i>')
# 3x-ui only. Pasarguard has no `.expire` / `.enabled`; it hands the theme an
# authoritative `{{ user.status.value }}` instead, so its runtime is left alone.
HIDDEN_NEW = (HIDDEN_OLD +
              '<i data-nuc-expire-ts style="display:none">{{ .expire }}</i>'
              '<i data-nuc-enabled style="display:none">{{ .enabled }}</i>')

# 3x-ui has no status field, so the state has to be derived here.
#
# Expiry is tested BEFORE enable on purpose: 3x-ui flips a client's enable bit
# off by itself roughly 20s after the expiry passes, so keying "disabled" first
# would make the Expired label unreachable in production and every lapsed
# subscription would read as merely "Disabled". With this order a lapsed client
# reports Expired, and Disabled is reserved for an admin turning off a client
# whose time has not run out.
STATUS_SANAEI = """<script data-nuc="pg-status">
(function(){
var FA={st_exhausted:'اتمام حجم',st_expired:'منقضی',st_disabled:'غیرفعال'};
var EN={st_exhausted:'Data Exhausted',st_expired:'Expired',st_disabled:'Disabled'};
/* volt-style tables spell the quota state 'limited' rather than 'exhausted' */
var SHORT={st_exhausted:'limited',st_expired:'expired',st_disabled:'disabled',st_active:'active'};
function txt(s){var e=document.querySelector(s);return e?(e.textContent||'').trim():'';}
function num(s){var v=parseFloat(txt(s));return isFinite(v)?v:NaN;}
function pgStatus(){
  var exp=num('[data-nuc-expire-ts]'),en=txt('[data-nuc-enabled]'),state='';
  var u=num('[data-nuc-used]'),l=num('[data-nuc-limit]');
  var usedUp=l>0&&u>=l;
  /* x-ui's own disable task switches a client off as soon as its quota runs
     out, and also when it expires, so enable=0 cannot tell those two apart.
     Check the specific cause first: an exhausted or expired client is much
     more useful to the user than the generic "disabled" it was turned into.
     Only a client that is off with quota to spare was disabled by hand. */
  if(exp>0&&exp<=Date.now()/1000){state='st_expired';}
  else if(usedUp){state='st_exhausted';}
  else if(en==='false'||en==='0'){state='st_disabled';}
  if(!state)return;
  var els=document.querySelectorAll('[data-nuc-status-el]');
  if(!els.length)els=document.querySelectorAll('[data-i18n="st_active"]');
  if(!els.length){
    var c=document.querySelectorAll('.info-value.success,.detail-value.success,b.ok,.status-badge-inline,.state,.status-pill,.usage-state,.status-text');
    for(var i=0;i<c.length;i++){var t=(c[i].textContent||'').trim();if(t==='فعال'||t==='Active'){els=[c[i]];break;}}}
  if(!els.length){
    var all=document.querySelectorAll('body *');
    for(var j=0;j<all.length;j++){var n=all[j];if(n.children.length===0){var q=(n.textContent||'').trim();if(q==='فعال'||q==='Active'){els=[n];break;}}}}
  for(var k=0;k<els.length;k++){
    var el=els[k];
    var isEn=/^[A-Za-z]/.test((el.textContent||'').trim());
    /* a table keyed by data-i18n-status must not gain a data-i18n, or its own
       applier would look up a key that table does not define */
    if(el.hasAttribute('data-i18n-status'))el.setAttribute('data-i18n-status',SHORT[state]);
    else el.setAttribute('data-i18n',state);
    el.setAttribute('data-nuc-exhausted','1');
    el.textContent=isEn?EN[state]:FA[state];
    /* keep the cached Persian text in step, or a later language switch would
       restore the stale label */
    if(el._fa!==undefined)el._fa=FA[state];
    try{el.style.color='#ef4444';el.classList.remove('ok','success');el.classList.add('danger');}catch(e){}}
}
pgStatus();
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',pgStatus);}
})();
</script>"""

# Pasarguard renders the plan size with the idiom its own `en` dict already uses.
PG_QUOTA_FA = ("{% if user.data_limit %}{{ user.data_limit | bytesformat }}"
               "{% else %}∞{% endif %}")

log = []


def note(m):
    log.append(m)


def fix_escaped_newlines(doc):
    """Remove the stray literal \\n that sits between top-level blocks.

    Positions inside <script>/<style> are skipped, so a legitimate JS escape
    such as '\\n' in a string is never touched. The lookahead is evaluated
    against the real document, which matters because these artefacts sit
    immediately before a tag."""
    protected = [(m.start(), m.end()) for m in
                 re.finditer(r"(?is)<(script|style)\b[^>]*>.*?</\1>", doc)]

    def inside(i):
        return any(a <= i < b for a, b in protected)

    out, last, n = [], 0, 0
    for m in re.finditer(r"\\n(?=<)", doc):
        if inside(m.start()):
            continue
        out.append(doc[last:m.start()])
        last = m.end()
        n += 1
    out.append(doc[last:])
    return "".join(out), n


def fix_unit(doc):
    """Drop a hardcoded unit span glued to a value that already carries a unit."""
    pat = re.compile(
        r"(?P<a>\{\{\s*\.(?:used|total|remained|download|upload)\s*\}\}\s*</span>\s*)"
        r"<span(?P<attrs>[^>]*)>\s*(?P<unit>GB|MB|KB|TB)\s*</span>")
    n = len(pat.findall(doc))
    if n:
        doc = pat.sub(lambda m: m.group("a"), doc)
    return doc, n


def fix_quota(doc, kind):
    """Replace a hardcoded plan size in a total/quota phrase.

    The unit suffix goes too: `.total` / `|bytesformat` already carry one, so
    keeping ' گیگابایت' would just re-introduce the duplicate-unit bug."""
    value = "{{ .total }}" if kind == "sanaei" else PG_QUOTA_FA
    total = [0]

    def repl(m):
        ctx = doc[max(0, m.start() - 110):m.end() + 70]
        if not re.search(r"total|of_total|کل حجم|quota|capacity", ctx, re.I):
            return m.group(0)
        total[0] += 1
        return value

    doc = re.sub(r"\d+(?:\.\d+)?\s*گیگابایت", repl, doc)
    doc = re.sub(r"\d+(?:\.\d+)?\s*GB(?=\s*(?:کل|total))", repl, doc)
    return doc, total[0]


KEYS = {
    "fa": {"st_exhausted": "اتمام حجم",
           "st_expired": "منقضی",
           "st_disabled": "غیرفعال"},
    "en": {"st_exhausted": "Data Exhausted",
           "st_expired": "Expired",
           "st_disabled": "Disabled"},
}
# Some themes quote the dict values with ', others with ". Capture both, and
# keep whichever quote the file already uses.
ACTIVE = re.compile(r"(st_active\s*:\s*(['\"]))([^'\"]*)(['\"])")


def _object_end(doc, i):
    """Index just past the '}' closing the object that starts at doc[i] == '{'.

    Quote-aware, so a brace inside a string does not end the scan early."""
    depth, j, quote = 0, i, None
    while j < len(doc):
        c = doc[j]
        if quote:
            if c == "\\":
                j += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(doc)


def add_i18n(doc):
    """Make sure every language dict carries the three status labels.

    Some themes only declared st_active, so the old runtime could set the
    exhausted text but applyLang() had no entry to restore it on a language
    switch. Anchored on st_active, which every dict has."""
    blocks = list(re.finditer(r'(?s)<script data-nuc="pg-status">.*?</script>', doc))

    bounds, prev = [], 0
    for m in blocks:
        bounds.append((prev, m.start()))
        prev = m.end()
    bounds.append((prev, len(doc)))

    pieces, added = [], 0
    for n, (a, b) in enumerate(bounds):
        seg, count = _apply_active(doc[a:b])
        pieces.append(seg)
        added += count
        if n < len(blocks):
            pieces.append(blocks[n].group(0))
    note("i18n: inserted %d status label(s)" % added)
    return "".join(pieces)


def _apply_active(seg):
    """Insert the missing status labels after each st_active entry."""
    res, last, n = [], 0, 0
    for m in ACTIVE.finditer(seg):
        start = seg.rfind("{", 0, m.start())
        if start < 0:
            continue
        body = seg[start:_object_end(seg, start)]
        val, quote = m.group(3), m.group(2)
        is_fa = any("\u0600" <= ch <= "\u06ff" for ch in val)
        lang = "fa" if is_fa else "en"
        missing = [k for k in KEYS[lang] if not re.search(r"\b%s\s*:" % k, body)]
        if not missing:
            continue
        q = '"' if quote == '"' else "'"
        extra = ", ".join("%s: %s%s%s" % (k, q, KEYS[lang][k], q) for k in missing)
        n += len(missing)
        res.append(seg[last:m.end()])
        res.append(", " + extra)
        last = m.end()
    res.append(seg[last:])
    return "".join(res), n


def fix_status_hooks(doc):
    """Let the status runtime reach a label that is rendered server-side.

    Themes such as volt decide the label with a Go conditional on .enabled, so
    the markup carries no data-i18n hook the runtime could find. Mark those
    elements explicitly."""
    n = [0]

    def repl(m):
        n[0] += 1
        return m.group(0).replace("data-i18n-status=", "data-nuc-status-el data-i18n-status=", 1)

    doc = re.sub(r"<(\w+)([^>]*?)data-i18n-status=([^>]*)>", repl, doc)
    return doc, n[0]


def fix_escaped_quotes(doc):
    """Repair HTML attributes whose quotes were written as \\\" .

    A pair has to be unwrapped together: fixing only the opening side turns
    target=\\"_blank\\" into target="_blank\\", which still leaves a stray
    backslash inside the value. The value pattern is bounded by quotes so a
    legitimate \\n inside a JS string further down the file is untouched."""
    pair_pat = r'=\\"([^"<>]*?)\\"'
    paired = len(re.findall(pair_pat, doc))
    if paired:
        doc = re.sub(pair_pat, r'="\1"', doc)
    leftover = len(re.findall(r'=\\"', doc))
    if leftover:
        doc = re.sub(r'=\\"', '="', doc)
    n = paired + leftover
    if n:
        note("fatal: unescaped %d attribute quote(s)" % n)
    return doc


def fix_brand(doc):
    """Nine themes inherited the upstream 'PasarGuard' header from a different
    product, which is wrong on both panels: every one of these templates already
    puts NUC-SUB in its <title>, so the visible name contradicts it. The 'PG'
    monogram in amber/lime goes with it."""
    n = doc.count("PasarGuard")
    if n:
        doc = doc.replace("PasarGuard", "NUC-SUB")
        note("brand: %d 'PasarGuard' label(s) now read NUC-SUB" % n)
    m = len(re.findall(r">PG<", doc))
    if m:
        doc = doc.replace(">PG<", ">NS<")
        note("brand: %d 'PG' monogram(s) now read NS" % m)
    return doc


def fix(doc, kind):
    doc = fix_escaped_quotes(doc)
    doc = fix_brand(doc)

    n = doc.count('data-width="<i data-nuc-pct></i>"')
    if n:
        doc = doc.replace('data-width="<i data-nuc-pct></i>"', "data-nuc-width")
        note("bar: %d bar(s) now driven by data-nuc-width" % n)

    doc, n = fix_unit(doc)
    if n:
        note("unit: removed %d duplicated unit span(s)" % n)

    doc, n = fix_quota(doc, kind)
    if n:
        note("quota: replaced %d hardcoded plan size(s)" % n)

    doc, n = fix_escaped_newlines(doc)
    if n:
        note("escapes: removed %d literal \\n from body text" % n)

    # 3x-ui only: Pasarguard supplies its own authoritative status string, and
    # guessing at its enum without a live panel would be worse than leaving it.
    if kind == "sanaei":
        if HIDDEN_OLD in doc and "data-nuc-expire-ts" not in doc:
            doc = doc.replace(HIDDEN_OLD, HIDDEN_NEW, 1)
            note("status: exposed expire/enabled to the runtime")
        m = re.search(r'(?s)<script data-nuc="pg-status">.*?</script>', doc)
        if m and "st_disabled" not in m.group(0):
            doc = doc[:m.start()] + STATUS_SANAEI + doc[m.end():]
            note("status: runtime now handles expired / disabled / exhausted")
        doc, n = fix_status_hooks(doc)
        if n:
            note("status: hooked %d server-rendered status element(s)" % n)
        doc = add_i18n(doc)
    return doc


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in PATHS:
        print(__doc__)
        return 2
    kind, theme = sys.argv[1], sys.argv[2]
    path = PATHS[kind] % theme
    if not os.path.exists(path):
        print("!! no such theme file: %s" % path)
        return 1
    before = open(path, encoding="utf-8").read()
    after = fix(before, kind)
    if after != before:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(after)
    print("%-10s %s" % (theme, "; ".join(log) if log else "no change needed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
