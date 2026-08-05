from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Signal:
    """One observation from one source about one ticker.

    `timestamp` is when *we* observed the signal; `event_date` is when the
    underlying event actually happened (the insider's trade date, the
    filing date, the article's publication date). Backtesting measures
    forward returns from `event_date` — measuring from observation time
    would measure a window in which the market had already reacted, so
    the two are deliberately kept separate rather than collapsed.

    `dedup_key` is the signal's stable natural identity, so re-running
    ingestion over the same upstream data updates rather than duplicates.
    Both fields are required: a defaulted event date or a generated-unique
    dedup key would silently reintroduce the bugs they exist to prevent.
    """

    timestamp: datetime
    event_date: date
    dedup_key: str
    source: str
    ticker: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
