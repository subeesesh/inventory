"""
Time helpers.

`datetime.utcnow()` is deprecated; this returns the same naive-UTC value the
database columns already store, so existing rows and comparisons are unchanged.
"""

from datetime import datetime, date, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_today() -> date:
    return utcnow().date()
