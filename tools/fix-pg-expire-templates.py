#!/usr/bin/env python3
"""
Fix the Pasarguard templates' "days left" expression.

PG v5.4.1 renders a subscription page with Jinja2, passing a datetime for
user.expire (db/models.py: `_expire` is DateTime(timezone=True) and the hybrid
property always returns a datetime) and a datetime for the `now()` global.

Every NUC-SUB theme shipped this:

    {{ ((user.expire - now()) / 86400) | round(0, 'ceil') | int
        if (user.expire - now()) > 0 else 0 }}

`expire - now()` evaluates to a datetime.timedelta. Two things are wrong with the
shipped expression, and either one is fatal:

  * `timedelta / int` yields *another timedelta*, not a float, so `round()` then
    raised "must be real number, not datetime.timedelta";
  * ordering a timedelta against an int is not supported either, so the
    conditional raised "TypeError: '>' not supported between instances of
    'datetime.timedelta' and 'int'".

Either one made the page return HTTP 500, for every user whose expire is set.
Users without expire took the `{% else %}` branch and rendered fine, which is
why it looked intermittent and survived review.

The fix calls `.total_seconds()` to get a real float, and compares the two
datetimes directly (`user.expire > now()`) instead of comparing a timedelta
against 0.

Per PG's contract user.expire is always a timezone-aware datetime or None:
`validated_user()` in app/operation/subscription.py assigns `db_user.expire`,
and the hybrid property in app/db/models.py returns _expire with UTC attached.
So the datetime-only arithmetic below matches what the panel actually renders.

Idempotent, and it also cleans up the intermediate `user.days_left` form, which
must not be used: it is a hybrid property on the SQLAlchemy model, not a field
on the Pydantic SubscriptionUserResponse that is actually handed to the
template.

NOTE ON LINE ENDINGS: these files are written with newline="\\n" on purpose.
Path.write_text() uses the platform default, which on Windows turns every "\\n"
into "\\r\\n". MANIFEST.sha256 is then generated over the CRLF bytes while git
stores LF, so every published theme hash disagrees with its manifest entry and
`nucsub update` refuses the release. Shipping LF keeps the tree, the manifest
and the git blob byte-identical.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
THEMES = ROOT / "pasarguard-themes" / "subscription"

FIXED = ("(((user.expire - now()).total_seconds()) / 86400) | round(0, 'ceil') | int "
         "if user.expire > now() else 0")

# The shipped broken expression (whitespace tolerant).
BROKEN = re.compile(
    r"\(\(user\.expire\s*-\s*now\(\)\)\s*/\s*86400\)\s*"
    r"\|\s*round\(\s*0\s*,\s*['\"]ceil['\"]\s*\)\s*\|\s*int\s+"
    r"if\s*\(user\.expire\s*-\s*now\(\)\)\s*>\s*0\s+else\s+0"
)

# The intermediate form that this script previously wrote: comparison fixed,
# but still missing .total_seconds(), so round() still failed.
PREVIOUS = re.compile(
    r"\(\(user\.expire\s*-\s*now\(\)\)\s*/\s*86400\)\s*"
    r"\|\s*round\(\s*0\s*,\s*['\"]ceil['\"]\s*\)\s*\|\s*int\s+"
    r"if\s*user\.expire\s*>\s*now\(\)\s+else\s+0"
)

# The dead-end that must not ship: absent from the Pydantic model.
INTERMEDIATE = re.compile(r"user\.days_left")

rewritten, relf = [], []

for p in sorted(THEMES.glob("*.html")):
    raw = p.read_bytes()
    src = raw.decode("utf-8")
    out, n0 = PREVIOUS.subn(FIXED, src)
    out, n1 = BROKEN.subn(FIXED, out)
    out, n2 = INTERMEDIATE.subn(FIXED, out)
    n = n0 + n1 + n2
    if n:
        rewritten.append((p.name, n))
    # Always normalise to LF: the file is manifest-hashed and git-committed, so
    # CRLF here silently breaks `nucsub update` for every user.
    lf = out.replace("\r\n", "\n").replace("\r", "\n")
    if lf.encode("utf-8") != raw:
        p.write_bytes(lf.encode("utf-8"))
        relf.append(p.name)

total = sum(n for _, n in rewritten)
print(f"rewrote {total} occurrence(s) across {len(rewritten)} theme(s)")
print(f"normalised to LF: {len(relf)} theme(s)")
if not rewritten:
    print("already correct: all themes")

# --- verify ---------------------------------------------------------------
problems = []
for p in sorted(THEMES.glob("*.html")):
    raw = p.read_bytes()
    s = raw.decode("utf-8")
    if b"\r\n" in raw:
        problems.append(f"{p.name}: contains CRLF; manifest/git would disagree")
    if re.search(r"\(\s*user\.expire\s*-\s*now\(\)\s*\)\s*>\s*0", s):
        problems.append(f"{p.name}: still compares a timedelta against 0")
    if "user.days_left" in s:
        problems.append(f"{p.name}: still uses user.days_left (not on the Pydantic model)")

if problems:
    print("ERROR:")
    for p in problems:
        print("  -", p)
    sys.exit(1)

print(f"verified: LF endings, no timedelta-vs-int compare, no user.days_left")