from topos.collectors.sec_edgar import SECEdgarCollector
from topos.signals.base import Signal


class Filing13FSignalExtractor:
    """Not implemented yet: a real 13F signal requires diffing a fund's
    holdings against its prior-quarter 13F, which needs historical filing
    storage this MVP doesn't have. The collector call below is wired up so
    the follow-up work is just extraction logic, not plumbing."""

    def __init__(self, collector: SECEdgarCollector | None = None) -> None:
        self._collector = collector or SECEdgarCollector()

    def extract(self, limit: int = 20) -> list[Signal]:
        self._collector.latest_filings("13F-HR", count=limit)
        return []
