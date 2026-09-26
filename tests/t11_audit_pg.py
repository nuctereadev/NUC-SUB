#!/usr/bin/env python3
"""Static check for the Pasarguard templates.

They cannot be render-verified without a Pasarguard panel, so at minimum the
file must contain no escaped attribute quotes, no smuggled bar markup, no
stray literal \\n in body text, no hardcoded plan size, and every {% %} block
must still be balanced.
"""
import glob
import os
import re
import sys

try:
    from jinja2 import Environment
    from jinja2.exceptions import TemplateSyntaxError
    HAVE_JINJA = True
except ImportError:
    HAVE_JINJA = False

# Pasarguard registers its own filters on top of Jinja2. Stock Jinja2 has to be
# told about them or every template fails to compile for the wrong reason; these
# stubs only exist so the parser reaches the rest of the file.
PG_FILTERS = ("bytesformat", "alt", "card", "mask")


def _env():
    env = Environment()
    for name in PG_FILTERS:
        env.filters.setdefault(name, lambda v, *a, **k: v)
    return env


bad = 0
files = sorted(glob.glob("pasarguard-themes/subscription/*.html"))
for path in files:
    name = os.path.basename(path)
    doc = open(path, encoding="utf-8", errors="replace").read()
    problems = []

    # the panel renders these with Jinja2, so actually compile one: this catches
    # unclosed blocks and bad filters that delimiter counting cannot
    if HAVE_JINJA:
        try:
            _env().from_string(doc)
        except TemplateSyntaxError as e:
            problems.append("jinja2: line %s %s" % (e.lineno, e.message))
        except Exception as e:                          # noqa: BLE001
            problems.append("jinja2: %s" % e)

    if re.search(r'=\\"', doc):
        problems.append("escaped attribute quote")
    if 'data-width="<i data-nuc-pct></i>"' in doc:
        problems.append("smuggled bar markup")
    if re.search(r"(?i)از\s*\d+(?:\.\d+)?\s*گیگابایت\s*کل", doc):
        problems.append("hardcoded plan size")
    body = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", "", doc)
    if "\\n<" in body:
        problems.append("stray \\n in body")
    # Template delimiters must balance in the markup only: JS is full of stray
    # braces, so counting them across the whole file is meaningless.
    for open_t, close_t in (("{%", "%}"), ("{{", "}}")):
        if body.count(open_t) != body.count(close_t):
            problems.append("unbalanced %s%s (%d/%d)"
                            % (open_t, close_t, body.count(open_t), body.count(close_t)))
    # a conditional must not have lost its else/endif pairing
    if body.count("{% if") != body.count("{% endif"):
        problems.append("if/endif mismatch (%d/%d)"
                        % (body.count("{% if"), body.count("{% endif")))
    if re.search(r'(?is)<(script|style)\b[^>]*>.*?</\1>', doc) is None:
        problems.append("no script/style closed properly")

    if problems:
        bad += 1
        print("%-14s FAIL: %s" % (name, "; ".join(problems)))
    else:
        print("%-14s ok" % name)
print("\n%d/%d pasarguard templates clean" % (len(files) - bad, len(files)))
sys.exit(1 if bad else 0)
