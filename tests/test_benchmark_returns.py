"""Returns have to be measured against something.

The 60-day report showed every score bucket earning roughly +3% and read
like success. Over three months of a rising market that is the market's
return, available to anyone who buys an index fund and does nothing. A
validation report that cannot separate the two will approve a strategy
that loses money relative to doing nothing.

The dangerous failure is not an error — it is a plausible number. So the
rule enforced here: if the benchmark leg is unmeasurable, the answer is
None, never a quiet fall back to the absolute return.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from topos.backtesting.prices import (
    BENCHMARK_TICKER,
    backfill_ticker,
    excess_forward_return,
    forward_return,
    has_benchmark_history,
)
from topos.collectors.prices import Bar
from topos.db.models import Base

_START = date(2026, 1, 5)


class _Stub:
    def __init__(self, closes):
        self._closes = closes

    def daily_bars(self, ticker):
        return [
            Bar(date=_START + timedelta(days=i), open=c, high=c, low=c, close=c, volume=2e6)
            for i, c in enumerate(self._closes)
        ]


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bench.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _flat_growth(start: float, per_bar: float, count: int = 40) -> list[float]:
    price, closes = start, []
    for _ in range(count):
        price *= 1 + per_bar
        closes.append(round(price, 4))
    return closes


def test_a_stock_matching_the_market_has_no_excess_return(db):
    # Both up 1% a bar. The stock made money; it added nothing.
    backfill_ticker(db, "AAPL", collector=_Stub(_flat_growth(100, 0.01)))
    backfill_ticker(db, BENCHMARK_TICKER, collector=_Stub(_flat_growth(400, 0.01)))

    absolute = forward_return(db, "AAPL", _START, 20)
    excess = excess_forward_return(db, "AAPL", _START, 20)

    assert absolute > 0.20  # looks like a triumph
    assert excess == pytest.approx(0.0, abs=1e-9)  # and is worth nothing


def test_beating_the_market_shows_a_positive_excess(db):
    backfill_ticker(db, "AAPL", collector=_Stub(_flat_growth(100, 0.012)))
    backfill_ticker(db, BENCHMARK_TICKER, collector=_Stub(_flat_growth(400, 0.01)))

    assert excess_forward_return(db, "AAPL", _START, 20) > 0


def test_a_gain_that_trails_the_market_is_reported_as_a_loss(db):
    # The case the whole thing exists for: +17% reads as success and is
    # a loss against an index that returned +22%.
    backfill_ticker(db, "AAPL", collector=_Stub(_flat_growth(100, 0.008)))
    backfill_ticker(db, BENCHMARK_TICKER, collector=_Stub(_flat_growth(400, 0.01)))

    assert forward_return(db, "AAPL", _START, 20) > 0
    assert excess_forward_return(db, "AAPL", _START, 20) < 0


def test_no_benchmark_history_yields_none_rather_than_the_absolute_return(db):
    backfill_ticker(db, "AAPL", collector=_Stub(_flat_growth(100, 0.01)))

    assert forward_return(db, "AAPL", _START, 20) is not None
    # Falling back here would relabel market drift as skill.
    assert excess_forward_return(db, "AAPL", _START, 20) is None


def test_no_asset_history_yields_none(db):
    backfill_ticker(db, BENCHMARK_TICKER, collector=_Stub(_flat_growth(400, 0.01)))

    assert excess_forward_return(db, "NOPE", _START, 20) is None


def test_benchmark_history_is_detectable_before_a_report_runs(db):
    assert has_benchmark_history(db) is False

    backfill_ticker(db, BENCHMARK_TICKER, collector=_Stub(_flat_growth(400, 0.01)))

    assert has_benchmark_history(db) is True


def test_a_short_benchmark_window_does_not_produce_a_partial_comparison(db):
    # The benchmark has only 10 bars; a 20-day window cannot be measured
    # against it, so neither leg may be reported.
    backfill_ticker(db, "AAPL", collector=_Stub(_flat_growth(100, 0.01, count=40)))
    backfill_ticker(db, BENCHMARK_TICKER, collector=_Stub(_flat_growth(400, 0.01, count=10)))

    assert excess_forward_return(db, "AAPL", _START, 20) is None
