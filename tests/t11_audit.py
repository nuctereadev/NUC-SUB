#!/usr/bin/env python3
"""Confirm every theme carries the pieces the status fix depends on:
  * both language dicts declare st_exhausted / st_expired / st_disabled
  * the pg-status runtime derives disabled / expired / exhausted
  * the hidden expire/enabled data exists
  * no unescaped attribute quotes, no smuggled bar markup, no stray body \\n
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t11_fix import ACTIVE, KEYS, _object_end  # noqa: E402

ROWS = []
for path in sorted(glob.glob("themes/*/index.html")):
    name = os.path.basename(os.path.dirname(path))
    doc = open(path, encoding="utf-8", errors="replace").read()
    # the pg-status runtime carries its own lookup tables; those are not the
    # theme's language dictionaries
    dict_doc = re.sub(r'(?s)<script data-nuc="pg-status">.*?</script>', "", doc)

    problems = []

    # --- language dicts -------------------------------------------------
    # A theme with no i18n table at all is legitimate: it either hardcodes the
    # Persian label (cobalt) or renders the state server-side with Go
    # conditionals (volt). Those rely on the runtime's text fallback instead.
    dicts = 0
    for m in ACTIVE.finditer(dict_doc):
        start = dict_doc.rfind("{", 0, m.start())
        if start < 0:
            continue
        body = dict_doc[start:_object_end(dict_doc, start)]
        is_fa = any("\u0600" <= ch <= "\u06ff" for ch in m.group(3))
        lang = "fa" if is_fa else "en"
        dicts += 1
        missing = [k for k in KEYS[lang] if not re.search(r"\b%s\s*:" % k, body)]
        if missing:
            problems.append("%s dict missing %s" % (lang, ",".join(missing)))

    has_i18n_table = bool(re.search(r"\b(const|var|let)\s+i18n\s*=", dict_doc))
    if dicts and dicts < 2:
        problems.append("only %d lang dict(s) found" % dicts)
    if dicts == 0 and not has_i18n_table:
        mode = "server-side" if 'data-i18n-status' in doc else "hardcoded label"
        print("%-9s no i18n table (%s) - runtime text fallback applies"
              % (name, mode))

    # --- runtime --------------------------------------------------------
    m = re.search(r'(?s)<script data-nuc="pg-status">(.*?)</script>', doc)
    if not m:
        problems.append("no pg-status runtime")
    else:
        rt = m.group(1)
        for need in ("st_disabled", "st_expired", "data-nuc-expire-ts",
                     "data-nuc-enabled"):
            if need not in rt:
                problems.append("runtime missing %s" % need)
    if "data-nuc-expire-ts" not in doc:
        problems.append("no hidden expire/enabled data")

    # --- pre-existing markup defects ------------------------------------
    if re.search(r'([a-zA-Z-]+)=\\"', doc):
        problems.append("escaped attribute quote")
    if 'data-width="<i data-nuc-pct></i>"' in doc:
        problems.append("smuggled bar markup")
    body = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", "", doc)
    if "\\n<" in body:
        problems.append("stray \\n in body")

    ROWS.append((name, dicts, problems))

bad = 0
for name, dicts, problems in ROWS:
    if problems:
        bad += 1
        print("%-9s dicts=%d  FAIL: %s" % (name, dicts, "; ".join(problems)))
    else:
        print("%-9s dicts=%d  ok" % (name, dicts))
print("\n%d/%d themes clean" % (len(ROWS) - bad, len(ROWS)))
sys.exit(1 if bad else 0)
