import re
from datetime import datetime
from typing import Any

_AMOUNT_RE = re.compile(r"[\d,]+")
_NON_TICKERS = {"", "N/A", "--", "NONE"}


def _amount_midpoint(amount_str: str | None) -> float:
    if not amount_str:
        return 0.0
    numbers = [int(n.replace(",", "")) for n in _AMOUNT_RE.findall(amount_str)]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def _transaction_type(raw_type: str | None) -> str | None:
    if not raw_type:
        return None
    raw_type = raw_type.lower()
    if "purchase" in raw_type:
        return "purchase"
    if "sale" in raw_type:
        return "sale"
    return None  # exchanges and anything else aren't a directional signal


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def normalize_congress_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """Turns one raw House/Senate Stock Watcher record into
    CongressionalTrade fields, or None if it's not a usable directional
    trade (missing ticker, or a non-purchase/sale transaction type)."""
    ticker = (record.get("ticker") or "").strip().upper()
    if ticker in _NON_TICKERS:
        return None

    transaction_type = _transaction_type(record.get("type"))
    if transaction_type is None:
        return None

    transaction_date = _parse_date(record.get("transaction_date"))
    if transaction_date is None:
        return None

    return {
        "chamber": record.get("chamber", "unknown"),
        "member": record.get("representative") or record.get("senator") or "unknown",
        "ticker": ticker,
        "transaction_type": transaction_type,
        "transaction_date": transaction_date,
        "disclosure_date": _parse_date(record.get("disclosure_date")),
        "amount_range": record.get("amount"),
        "amount_midpoint_usd": _amount_midpoint(record.get("amount")),
        "source_url": record.get("ptr_link"),
    }
