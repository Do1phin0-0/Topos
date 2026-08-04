from datetime import datetime, timezone

from topos.collectors.sec_edgar import SECEdgarCollector
from topos.signals.base import Signal


class EarningsSignalExtractor:
    """Flags 8-K filings that report Item 2.02 (Results of Operations and
    Financial Condition) — the item issuers use to furnish an earnings
    press release. This is a timing signal (a report just dropped), not a
    beat/miss signal: actual EPS-vs-estimate data needs a paid provider
    (Alpha Vantage, Finnhub, ...) that isn't wired up here."""

    def __init__(self, collector: SECEdgarCollector | None = None) -> None:
        self._collector = collector or SECEdgarCollector()

    def extract(self, limit: int = 40) -> list[Signal]:
        signals: list[Signal] = []
        for filing in self._collector.latest_filings("8-K", count=limit):
            ticker = self._collector.ticker_for_cik(filing.get("cik"))
            if not ticker:
                continue
            if not self._has_item_202(filing["index_url"]):
                continue
            signals.append(
                Signal(
                    timestamp=datetime.now(timezone.utc),
                    source="sec_8k_earnings",
                    ticker=ticker,
                    confidence=0.4,
                    evidence={"filing_url": filing["index_url"], "form_type": "8-K"},
                )
            )
        return signals

    def _has_item_202(self, index_url: str) -> bool:
        try:
            text = self._collector.fetch_text(index_url)
        except Exception:
            return False
        return "2.02" in text
