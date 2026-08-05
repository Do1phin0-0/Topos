import re
from datetime import date, datetime, timezone
from typing import Any

from topos.collectors.house_clerk import HouseClerkCollector
from topos.signals.base import Signal

_AMOUNT_RE = re.compile(r"[\d,]+")
_NON_TICKERS = {"", "N/A", "--", "NONE"}


def _amount_midpoint(amount_str: str | None) -> float:
    if not amount_str:
        return 0.0
    numbers = [int(n.replace(",", "")) for n in _AMOUNT_RE.findall(amount_str)]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def _direction(txn_type: str | None) -> str:
    if not txn_type:
        return "neutral"
    txn_type = txn_type.lower()
    if "purchase" in txn_type:
        return "buy"
    if "sale" in txn_type:
        return "sell"
    return "neutral"


def _parse_event_date(record: dict[str, Any]) -> date | None:
    """The date the member actually traded. A record we can't date is
    dropped rather than stamped with today's date — backdating it would
    corrupt any forward return measured from it."""
    raw = record.get("transaction_date") or record.get("disclosure_date")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def extract_congress_signal(record: dict[str, Any]) -> Signal | None:
    ticker = (record.get("ticker") or "").strip().upper()
    if ticker in _NON_TICKERS:
        return None

    direction = _direction(record.get("type"))
    if direction == "neutral":
        return None

    midpoint = _amount_midpoint(record.get("amount"))
    size_weight = min(midpoint / 250_000, 1.0) * 0.4
    confidence = max(0.0, min(1.0, 0.25 + size_weight))

    owner = record.get("representative") or record.get("senator") or "unknown"

    event_date = _parse_event_date(record)
    if event_date is None:
        return None

    chamber = record.get("chamber", "unknown")

    return Signal(
        timestamp=datetime.now(timezone.utc),
        event_date=event_date,
        # A disclosed transaction carries no stable upstream id, so
        # identity is the disclosure itself: who traded what, which way,
        # when. Re-parsing a filing therefore cannot double-insert it.
        dedup_key=f"congress_{chamber}:{owner}:{ticker}:{event_date.isoformat()}:{direction}",
        source=f"congress_{chamber}",
        ticker=ticker,
        confidence=round(confidence, 3),
        evidence={
            "member": owner,
            "chamber": record.get("chamber"),
            "direction": direction,
            "amount_range": record.get("amount"),
            "amount_midpoint_usd": midpoint,
            "disclosure_date": record.get("disclosure_date"),
            "ptr_link": record.get("ptr_link"),
        },
    )


class CongressSignalExtractor:
    """Live congressional signals, read from the House Clerk archive.

    The archive is a whole year at a time rather than a recent-items feed,
    which sounds wasteful for an hourly poll and isn't: downloaded reports
    are cached on disk, so each run fetches only filings that appeared
    since the last one. The first run of a year is the expensive one.
    """

    def __init__(self, collector: HouseClerkCollector | None = None) -> None:
        self._collector = collector or HouseClerkCollector()

    def extract(self, limit: int = 200) -> list[Signal]:
        records = self._collector.all_transactions([date.today().year])

        signals = []
        for record in records[:limit]:
            signal = extract_congress_signal(record)
            if signal:
                signals.append(signal)
        return signals
