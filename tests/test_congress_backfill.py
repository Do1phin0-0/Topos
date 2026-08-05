"""The congressional archive is fully downloaded on every request.

`latest_transactions()` truncates it, which is right for a routine poll
but meant years of already-fetched history were discarded. `all_transactions()`
exposes the full set for backfill.
"""

from unittest.mock import patch

from topos.collectors.congress import CongressTradeCollector


def _record(ticker: str, day: int, chamber: str = "house") -> dict:
    return {
        "ticker": ticker,
        "type": "purchase",
        "amount": "$1,001 - $15,000",
        "representative": "Jane Rep",
        "transaction_date": f"2026-07-{day:02d}",
        "chamber": chamber,
    }


def test_all_transactions_returns_everything_newest_first():
    collector = CongressTradeCollector()
    house = [_record("AAA", 1), _record("BBB", 20)]
    senate = [_record("CCC", 10, "senate")]

    with patch.object(collector, "house_transactions", return_value=house), patch.object(
        collector, "senate_transactions", return_value=senate
    ):
        result = collector.all_transactions()

    assert [r["ticker"] for r in result] == ["BBB", "CCC", "AAA"]


def test_latest_transactions_truncates_but_all_transactions_does_not():
    collector = CongressTradeCollector()
    house = [_record(f"T{i:02d}", (i % 28) + 1) for i in range(50)]

    with patch.object(collector, "house_transactions", return_value=house), patch.object(
        collector, "senate_transactions", return_value=[]
    ):
        assert len(collector.latest_transactions(limit=10)) == 10
        # The history the routine poll throws away is what backfill needs.
        assert len(collector.all_transactions()) == 50
