"""Parsing for the assorted timestamp formats the upstream feeds use.

Each sentiment source hands back item-level times in a different shape —
RSS uses RFC 2822, Reddit uses a Unix epoch float, X/Twitter uses ISO
8601 — and all three were previously discarded in favour of "today".
"""

from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


def parse_rfc2822(raw: str | None) -> datetime | None:
    """RSS `pubDate`, e.g. 'Mon, 05 Aug 2026 14:31:02 GMT'."""
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_epoch(raw: Any) -> datetime | None:
    """Reddit `created_utc`, a Unix timestamp as a float."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_iso8601(raw: str | None) -> datetime | None:
    """X/Twitter `created_at`, e.g. '2026-08-05T14:31:02.000Z'."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None


def latest_date(timestamps: list[datetime | None]) -> date | None:
    """The most recent parseable date in a batch, or None if nothing
    parsed.

    A rolling sentiment aggregate is dated by its freshest underlying
    item rather than by the moment we happened to scan. If the newest
    article about a ticker is five days old, the sentiment "event"
    happened five days ago — re-reading the same articles today adds no
    information, and crediting today's date would both overstate the
    signal's freshness and let a stale reading claim a forward return
    starting from a day it knew nothing new about.
    """
    dates = [ts.date() for ts in timestamps if ts is not None]
    return max(dates) if dates else None
