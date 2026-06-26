from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a naive UTC datetime for compatibility with existing DB fields."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcnow_iso() -> str:
    """Return an ISO-8601 UTC timestamp with an explicit timezone marker."""
    return utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
