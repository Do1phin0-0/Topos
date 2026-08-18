import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from topos.collectors.congress import CongressTradeCollector
from topos.signals.base import Signal

_AMOUNT_RE = re.compile(r"[\d,]+")
_NON_TICKERS = {"", "N/A", "--", "NONE"}


def _external_id(record: dict[str, Any], ticker: str) -> str:
    """Stable id for a disclosed transaction. Prefer the PTR link (unique
    per disclosure) combined with the specific ticker/date/type, since one
    PTR can list several transactions; fall back to a content hash for
    records without a link."""
    ptr_link = record.get("ptr_link")
    parts = [
        ptr_link or "",
        ticker,
        str(record.get("transaction_date")),
        str(record.get("type")),
        str(record.get("amount")),
        str(record.get("representative") or record.get("senator") or ""),
        str(record.get("chamber")),
    ]
    if ptr_link:
        return "|".join(parts)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


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


def _parse_timestamp(record: dict[str, Any]) -> datetime:
    raw = record.get("transaction_date") or record.get("disclosure_date")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


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

    return Signal(
        timestamp=_parse_timestamp(record),
        source=f"congress_{record.get('chamber', 'unknown')}",
        ticker=ticker,
        confidence=round(confidence, 3),
        external_id=_external_id(record, ticker),
        direction=direction,
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
    def __init__(self, collector: CongressTradeCollector | None = None) -> None:
        self._collector = collector or CongressTradeCollector()

    def extract(self, limit: int = 200) -> list[Signal]:
        signals = []
        for record in self._collector.latest_transactions(limit=limit):
            signal = extract_congress_signal(record)
            if signal:
                signals.append(signal)
        return signals
