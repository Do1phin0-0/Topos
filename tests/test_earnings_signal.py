from unittest.mock import MagicMock

from topos.collectors.sec_edgar import SECEdgarCollector
from topos.signals.earnings import EarningsSignalExtractor


def test_extract_flags_only_item_202_filings_with_resolvable_tickers():
    mock_collector = MagicMock()
    mock_collector.latest_filings.return_value = [
        {"index_url": "https://sec.gov/Archives/edgar/data/123/abc-index.htm", "cik": 123, "filed_at": "2026-08-01T14:31:02-04:00"},
        {"index_url": "https://sec.gov/Archives/edgar/data/456/def-index.htm", "cik": 456, "filed_at": "2026-08-01T14:32:02-04:00"},
        {"index_url": "https://sec.gov/Archives/edgar/data/789/ghi-index.htm", "cik": 789, "filed_at": "2026-08-01T14:33:02-04:00"},
    ]
    mock_collector.ticker_for_cik.side_effect = lambda cik: {123: "ACME", 789: "WIDG"}.get(cik)
    mock_collector.fetch_text.side_effect = lambda url: (
        "Item 2.02 Results of Operations..." if "123" in url else "Item 5.02 Departure of Officer"
    )

    signals = EarningsSignalExtractor(collector=mock_collector).extract(limit=10)

    assert len(signals) == 1
    assert signals[0].ticker == "ACME"
    assert signals[0].source == "sec_8k_earnings"
    # cik=456 has no resolvable ticker, so fetch_text should be skipped for it
    # entirely — only the two filings with resolvable tickers get checked.
    called_urls = [call.args[0] for call in mock_collector.fetch_text.call_args_list]
    assert called_urls == [
        "https://sec.gov/Archives/edgar/data/123/abc-index.htm",
        "https://sec.gov/Archives/edgar/data/789/ghi-index.htm",
    ]


def test_cik_extraction_from_index_url():
    cik = SECEdgarCollector._cik_from_index_url(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123-index.htm"
    )

    assert cik == 320193
    assert SECEdgarCollector._cik_from_index_url("not-a-valid-url") is None
