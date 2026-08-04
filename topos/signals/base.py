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
