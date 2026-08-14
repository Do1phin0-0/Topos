from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from topos.backtesting.evaluate import evaluate_signals
from topos.backtesting.prices import apply_cost, backfill_ticker
from topos.backtesting.research import multi_vs_single_source
from topos.collectors.prices import Bar
from topos.db.models import PriceBar, RankedOpportunity
from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db

_TICKERS = ["DOWNCO"]
_START = date(2026, 6, 1)


def test_apply_cost_subtracts_a_flat_cost_from_a_gain():
    assert apply_cost(0.10, 10.0) == pytest.approx(0.099)


def test_apply_cost_subtracts_the_same_cost_from_a_loss():
    # Cost is paid on entry and exit regardless of whether the trade won.
    assert apply_cost(-0.05, 20.0) == pytest.approx(-0.052)


def test_apply_cost_zero_bps_is_a_no_op():
    assert apply_cost(0.0345, 0.0) == pytest.approx(0.0345)


class _StubCollector:
    def __init__(self, closes: list[float]) -> None:
        self._closes = closes

    def daily_bars(self, ticker: str) -> list[Bar]:
        return [
            Bar(date=_START + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1_000_000.0)
            for i, c in enumerate(self._closes)
        ]


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()

    def _clean():
        session.execute(delete(PriceBar).where(PriceBar.ticker.in_(_TICKERS)))
        session.execute(delete(SignalRow).where(SignalRow.ticker.in_(_TICKERS)))
        session.execute(delete(RankedOpportunity).where(RankedOpportunity.ticker.in_(_TICKERS)))
        session.commit()

    _clean()
    # DOWNCO falls 100 -> 90 over 5 sessions (-10%).
    backfill_ticker(db=session, ticker="DOWNCO", collector=_StubCollector([100, 98, 96, 94, 92, 90]))
    try:
        yield session
    finally:
        _clean()
        session.close()


def test_cost_is_applied_after_direction_adjustment_not_before(db):
    # A SELL signal on a stock that fell 10%: direction-adjusted return is
    # +10%. Subtracting cost BEFORE that sign flip would let the flip
    # invert the cost too and turn a deduction into a bonus. The net
    # figure must be a strictly smaller gain, not a larger one.
    db.add(SignalRow(
        timestamp=datetime.now(timezone.utc),
        event_date=_START,
        dedup_key="cost-sell-check",
        source="sec_form4",
        ticker="DOWNCO",
        confidence=0.8,
        evidence={"direction": "sell"},
    ))
    db.commit()

    [gross] = evaluate_signals(db, horizons=(5,), cost_bps=0.0)
    [net] = evaluate_signals(db, horizons=(5,), cost_bps=10.0)

    assert gross.horizons[5].avg_return == pytest.approx(0.10)
    assert net.horizons[5].avg_return == pytest.approx(0.10 - 0.001)
    assert net.horizons[5].avg_return < gross.horizons[5].avg_return


def test_multi_vs_single_source_cost_applied_after_sell_negation(db):
    db.add(RankedOpportunity(
        ticker="DOWNCO", score=85.0, recommendation="SELL", net_direction=-1.0,
        signal_count=1, sources=["sec_form4"],
        rank_timestamp=datetime(2026, 6, 1, 12, 0, 0),
    ))
    db.commit()

    gross = multi_vs_single_source(db, horizon_days=5, cost_bps=0.0)
    net = multi_vs_single_source(db, horizon_days=5, cost_bps=10.0)

    gross_single = next(c for c in gross.cohorts if c.label == "single-source")
    net_single = next(c for c in net.cohorts if c.label == "single-source")

    assert gross_single.mean_return == pytest.approx(0.10)
    assert net_single.mean_return == pytest.approx(0.10 - 0.001)
