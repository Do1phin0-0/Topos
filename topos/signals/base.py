from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Signal:
    timestamp: datetime
    source: str
    ticker: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    # Stable identifier for the underlying filing/disclosure, used to skip
    # re-inserting the same record on every collection run. None for
    # sources that can't produce one (falls back to always-insert).
    external_id: str | None = None
    # "buy" | "sell" | "neutral". Confidence alone only measures conviction
    # strength, not which way the underlying trade points — ranking and
    # portfolio construction need this to avoid going long a ticker that
    # insiders/congress/funds are actually net *selling*.
    direction: str = "neutral"
