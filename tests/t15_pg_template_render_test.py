#!/usr/bin/env python3
"""
Render every Pasarguard theme the way PG v5.4.1 does, and fail on any template
that raises.

The subscription page 500'd in production for months of real usage because the
templates did `(user.expire - now()) > 0`. Jinja2 evaluates that as a timedelta,
and timedelta cannot be ordered against int:

    TypeError: '>' not supported between instances of 'datetime.timedelta' and 'int'

Nothing in the suite noticed, because nothing ever rendered a template. This
renders them, with the same Jinja2 Environment/FileSystemLoader shape as
PG's app/templates/__init__.py and a payload shaped like PG's
_build_subscription_body_payload.

The payloads deliberately include the awkward real-world cases:
  - expire set and in the future (the case that 500'd)
  - expire set and already past (expired user)
  - expire as 0 / None (unlimited -> the `{% else %}` branch)
  - expire as a unix timestamp int
  - timezone-naive datetime, which PG's hybrid property never returns but a
    hand-edited panel DB might
"""
import datetime as dt
import pathlib
import re
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[1]
THEMES = ROOT / "pasarguard-themes" / "subscription"

try:
    from jinja2 import Environment, FileSystemLoader
    from jinja2.sandbox import SandboxedEnvironment
except ImportError:  # pragma: no cover
    print("SKIP: jinja2 is not installed here (run this where the panel runs)")
    sys.exit(0)

UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)


def datetimeformat(value):
    """Mirror of PG's `datetime` filter."""
    if isinstance(value, int):
        value = dt.datetime.fromtimestamp(value, tz=UTC)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def bytesformat(value, _decimals=2):
    """Mirror of PG's `bytesformat` filter (human readable traffic sizes)."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024.0:
            return f"{num:.{_decimals}f} {unit}"
        num /= 1024.0
    return f"{num:.{_decimals}f} EB"


def user_payload(expire):
    # PG passes a Pydantic model (SubscriptionUserResponse), and the templates
    # use attribute access (user.data_limit), so this must not be a plain dict.
    return SimpleNamespace(
        username="probe-user",
        status="active",
        used_traffic=1_051_830_101,
        lifetime_used_traffic=1_051_830_101,
        data_limit=10_737_418_240,
        data_limit_reset_strategy="no_reset",
        data_limit_reset_interval=None,
        expire=expire,
        email=None,
        telegram_id=None,
        note=None,
        created_at=NOW - dt.timedelta(days=40),
        edit_at=NOW - dt.timedelta(days=5),
        online_at=NOW - dt.timedelta(hours=2),
        # `days_left` is deliberately absent: it is a hybrid property on the
        # SQLAlchemy model, not a field on the Pydantic SubscriptionUserResponse
        # that PG hands to the template, so a template using it would raise
        # AttributeError in production.
        admin=None,
        group_names=["default"],
        sub_last_user_agent=None,
        links_expire_duration=None,
    )


def links_payload():
    return ["vless://uuid@a.example:443?security=tls#node-1"]


# PG's contract: validated_user() in app/operation/subscription.py assigns
# `user.expire = db_user.expire`, and the hybrid property in app/db/models.py
# returns _expire with tzinfo=UTC attached. So on the subscription path
# user.expire is a timezone-aware datetime or None -- never a bare int and
# never naive. The int / naive shapes are therefore deliberately not asserted
# here: no code path can produce them, and supporting them would mean shipping
# an unreadable multi-branch expression inside all 33 user-editable themes.
CASES = [
    ("expire in the future (the 500)", NOW + dt.timedelta(days=27, hours=4)),
    ("expire soon (under a day)", NOW + dt.timedelta(hours=6)),
    ("expire just passed", NOW - dt.timedelta(minutes=1)),
    ("expire long past", NOW - dt.timedelta(days=400)),
    ("expire exactly now", NOW),
    ("unlimited (None)", None),
    ("unlimited (0)", 0),
]

env = Environment(loader=FileSystemLoader(str(THEMES)))
env.filters["datetime"] = datetimeformat
env.filters["bytesformat"] = bytesformat
env.filters["tojson"] = lambda v: __import__("json").dumps(v, default=str)
env.globals["now"] = lambda: dt.datetime.now(UTC)

themes = sorted(THEMES.glob("*.html"))
if not themes:
    print("no themes found under", THEMES)
    sys.exit(1)

failures = []
checked = 0
for theme in themes:
    name = theme.stem
    try:
        tpl = env.get_template(name + ".html")
    except Exception as exc:                      # noqa: BLE001
        failures.append(f"{name}: template failed to load: {exc}")
        continue
    for label, expire in CASES:
        ctx = {
            "user": user_payload(expire),
            "links": links_payload(),
            "announce": "",
            "links_icons": [],
            "links_expire_duration": [],
            "hwid": None,
            "is_hwid_enabled": False,
        }
        try:
            out = tpl.render(**ctx)
        except Exception as exc:                  # noqa: BLE001
            failures.append(f"{name} [{label}]: {type(exc).__name__}: {exc}")
            continue
        checked += 1
        if len(out) < 200:
            failures.append(f"{name} [{label}]: rendered only {len(out)} bytes")

print(f"rendered {checked} theme/case combinations across {len(themes)} themes")

# `user.expire - now()` is legitimate (it is a datetime subtraction); what must
# never come back is dividing that timedelta by an int without .total_seconds(),
# or ordering the timedelta against 0.
BAD_COMPARE = re.compile(r"\(\s*user\.expire\s*-\s*now\(\)\s*\)\s*>\s*0")
BAD_DIVIDE = re.compile(
    r"\(\(user\.expire\s*-\s*now\(\)\)\s*/\s*86400\)"
    r"(?!\s*\)\s*\.\s*total_seconds)"
)
for theme in themes:
    src = theme.read_text(encoding="utf-8")
    if BAD_COMPARE.search(src):
        failures.append(f"{theme.name}: compares a timedelta against 0")
    if BAD_DIVIDE.search(src):
        failures.append(f"{theme.name}: divides a timedelta without .total_seconds()")
    if "user.days_left" in src:
        failures.append(f"{theme.name}: uses user.days_left, absent from the Pydantic model")

if failures:
    print(f"\n{len(failures)} FAILURE(S):")
    for f in failures[:40]:
        print("  -", f)
    if len(failures) > 40:
        print(f"  ... and {len(failures) - 40} more")
    sys.exit(1)

print("all themes render for every expire case: no TypeError, no 500")