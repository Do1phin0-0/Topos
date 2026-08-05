from datetime import date, datetime, timezone

from topos.collectors.sec_edgar import SECEdgarCollector
from topos.signals.base import Signal


def _parse_filed_date(raw: str | None) -> date | None:
    """The atom feed's `updated` field, e.g. '2026-08-05T14:31:02-04:00'."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


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
            # The filing date is the event: the market learns the results
            # when the 8-K drops, not when we happen to scrape it.
            event_date = _parse_filed_date(filing.get("filed_at"))
            if event_date is None:
                continue
            signals.append(
                Signal(
                    timestamp=datetime.now(timezone.utc),
                    event_date=event_date,
                    dedup_key=f"sec_8k_earnings:{filing['index_url']}",
                    source="sec_8k_earnings",
                    ticker=ticker,
                    confidence=0.4,
                    evidence={
                        "filing_url": filing["index_url"],
                        "form_type": "8-K",
                        "filed_at": filing.get("filed_at"),
                    },
                )
            )
        return signals

    def _has_item_202(self, index_url: str) -> bool:
        try:
            text = self._collector.fetch_text(index_url)
        except Exception:
            return False
        return "2.02" in text
