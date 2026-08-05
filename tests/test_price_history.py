from datetime import date

import pytest
from sqlalchemy import delete

from topos.backtesting.prices import (
    average_dollar_volume,
    backfill_ticker,
    backfill_tickers,
    forward_return,
    get_bars,
)
from topos.collectors.prices import Bar, parse_stooq_csv
from topos.db.models import PriceBar
from topos.db.session import SessionLocal, init_db

_VALID_CSV = """Date,Open,High,Low,Close,Volume
2026-07-01,10.0,10.5,9.8,10.2,1000000
2026-07-02,10.2,10.9,10.1,10.8,1200000
2026-07-03,10.8,11.2,10.7,11.0,900000
"""


def test_parse_stooq_csv_reads_full_bars():
    bars = parse_stooq_csv(_VALID_CSV)

    assert len(bars) == 3
    assert bars[0] == Bar(
        date=date(2026, 7, 1), open=10.0, high=10.5, low=9.8, close=10.2, volume=1000000.0
    )
    assert bars[-1].close == 11.0


def test_parse_stooq_csv_sorts_oldest_first():
    reversed_csv = """Date,Open,High,Low,Close,Volume
2026-07-03,10.8,11.2,10.7,11.0,900000
2026-07-01,10.0,10.5,9.8,10.2,1000000
"""

    bars = parse_stooq_csv(reversed_csv)

    assert [b.date for b in bars] == [date(2026, 7, 1), date(2026, 7, 3)]


def test_parse_stooq_csv_handles_error_body_and_bad_rows():
    # Stooq returns a plain-text body, not a CSV, for unknown symbols.
    assert parse_stooq_csv("Exceeded the daily hits limit") == []
    assert parse_stooq_csv("") == []

    partial = """Date,Open,High,Low,Close,Volume
2026-07-01,10.0,10.5,9.8,10.2,1000000
2026-07-02,N/D,N/D,N/D,N/D,N/D
"""
    bars = parse_stooq_csv(partial)
    assert len(bars) == 1
    assert bars[0].date == date(2026, 7, 1)


class _StubCollector:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars
        self.calls = 0

    def daily_bars(self, ticker: str) -> list[Bar]:
        self.calls += 1
        return self._bars


def _bar(day: int, close: float, volume: float = 1_000_000.0) -> Bar:
    return Bar(
        date=date(2026, 7, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
    )


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    session.execute(delete(PriceBar).where(PriceBar.ticker == "ZZZTEST"))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(PriceBar).where(PriceBar.ticker == "ZZZTEST"))
        session.commit()
        session.close()


def test_backfill_inserts_then_dedupes_on_rerun(db):
    collector = _StubCollector([_bar(1, 10.0), _bar(2, 11.0)])

    assert backfill_ticker(db, "ZZZTEST", collector=collector) == 2
    # Same upstream data on a second run must not duplicate rows.
    assert backfill_ticker(db, "ZZZTEST", collector=collector) == 0
    assert len(get_bars(db, "ZZZTEST")) == 2


def test_backfill_adds_only_new_bars(db):
    backfill_ticker(db, "ZZZTEST", collector=_StubCollector([_bar(1, 10.0)]))

    inserted = backfill_ticker(
        db, "ZZZTEST", collector=_StubCollector([_bar(1, 10.0), _bar(2, 11.0)])
    )

    assert inserted == 1
    assert [b.date for b in get_bars(db, "ZZZTEST")] == [date(2026, 7, 1), date(2026, 7, 2)]


def test_backfill_tickers_survives_one_failing_ticker(db):
    class _Exploding:
        def daily_bars(self, ticker: str) -> list[Bar]:
            if ticker == "BOOM":
                raise RuntimeError("simulated upstream failure")
            return [_bar(1, 10.0)]

    results = backfill_tickers(db, ["BOOM", "ZZZTEST"], collector=_Exploding())

    assert results["BOOM"] == 0
    assert results["ZZZTEST"] == 1


def test_forward_return_measures_trading_day_horizon(db):
    backfill_ticker(
        db,
        "ZZZTEST",
        collector=_StubCollector([_bar(1, 100.0), _bar(2, 105.0), _bar(3, 110.0)]),
    )

    # 2 trading days from the first bar: 100 -> 110
    assert forward_return(db, "ZZZTEST", date(2026, 7, 1), 2) == pytest.approx(0.10)
    # 1 trading day: 100 -> 105
    assert forward_return(db, "ZZZTEST", date(2026, 7, 1), 1) == pytest.approx(0.05)


def test_forward_return_enters_at_next_session_when_date_has_no_bar(db):
    # Signal dated the 2nd, but the market's first open session is the 3rd.
    backfill_ticker(db, "ZZZTEST", collector=_StubCollector([_bar(3, 100.0), _bar(4, 120.0)]))

    assert forward_return(db, "ZZZTEST", date(2026, 7, 2), 1) == pytest.approx(0.20)


def test_forward_return_is_none_without_enough_history(db):
    backfill_ticker(db, "ZZZTEST", collector=_StubCollector([_bar(1, 100.0), _bar(2, 105.0)]))

    # An unmeasurable horizon must be None, never a fabricated 0%.
    assert forward_return(db, "ZZZTEST", date(2026, 7, 1), 5) is None
    assert forward_return(db, "ZZZTEST", date(2026, 7, 1), 2) is None


def test_forward_return_is_none_for_unknown_ticker(db):
    assert forward_return(db, "NOSUCHTICKER", date(2026, 7, 1), 5) is None


def test_average_dollar_volume_weights_price_not_just_share_count(db):
    backfill_ticker(
        db,
        "ZZZTEST",
        collector=_StubCollector([_bar(1, 10.0, volume=1000.0), _bar(2, 20.0, volume=1000.0)]),
    )

    # (10*1000 + 20*1000) / 2
    assert average_dollar_volume(db, "ZZZTEST") == pytest.approx(15_000.0)
    assert average_dollar_volume(db, "NOSUCHTICKER") is None
