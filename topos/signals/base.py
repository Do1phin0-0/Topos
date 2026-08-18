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
