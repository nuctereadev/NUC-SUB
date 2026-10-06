#!/usr/bin/env python3
"""
Fix the Pasarguard subscription templates' "days left" expression.

PG v5.4.1 renders a subscription page with Jinja2, passing a datetime for
user.expire (db/models.py: `_expire` is DateTime(timezone=True) and the hybrid
property always returns a datetime) and a datetime for the `now()` global.

Every NUC-SUB theme shipped this:

    {{ ((user.expire - now()) / 86400) | round(0, 'ceil') | int
        if (user.expire - now()) > 0 else 0 }}

`expire - now()` evaluates to a datetime.timedelta. Two things are wrong with the
shipped expression:

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
and the hybrid property in app/db/models.py returns `_expire` with UTC attached.
So the datetime-only arithmetic below matches what the panel actually renders.

Idempotent, and it also cleans up the intermediate `user.days_left` form, which
must not be used: it is a hybrid property on the SQLAlchemy model, not a field
on the Pydantic SubscriptionUserResponse that is actually handed to the
template.
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

# The intermediate form that this script previously wrote.
INTERMEDIATE = re.compile(r"user\.days_left")

# The intermediate form that this script previously wrote: comparison fixed,
# but still missing .total_seconds(), so round() still failed.
PREVIOUS = re.compile(
    r"\(\(user\.expire\s*-\s*now\(\)\)\s*/\s*86400\)\s*"
    r"\|\s*round\(\s*0\s*,\s*['\"]ceil['\"]\s*\)\s*\|\s*int\s+"
    r"if\s*user\.expire\s*>\s*now\(\)\s+else\s+0"
)

rewritten, skipped = [], []

for p in sorted(THEMES.glob("*.html")):
    src = p.read_text(encoding="utf-8")
    out, n0 = PREVIOUS.subn(FIXED, src)
    out, n1 = BROKEN.subn(FIXED, out)
    out, n2 = INTERMEDIATE.subn(FIXED, out)
    n = n0 + n1 + n2
    if n:
        p.write_text(out, encoding="utf-8")
        rewritten.append((p.name, n))
    else:
        skipped.append(p.name)

total = sum(n for _, n in rewritten)
print(f"rewrote {total} occurrence(s) across {len(rewritten)} theme(s)")
if skipped:
    print(f"already correct: {len(skipped)}")

# --- verify ---------------------------------------------------------------
problems = []
for p in sorted(THEMES.glob("*.html")):
    s = p.read_text(encoding="utf-8")
    if re.search(r"\(\s*user\.expire\s*-\s*now\(\)\s*\)\s*>\s*0", s):
        problems.append(f"{p.name}: still compares a timedelta against 0")
    if "user.days_left" in s:
        problems.append(f"{p.name}: still uses user.days_left (not on the Pydantic model)")

if problems:
    print("ERROR:")
    for p in problems:
        print("  -", p)
    sys.exit(1)

print(f"verified: no theme compares timedelta > 0, none uses user.days_left")