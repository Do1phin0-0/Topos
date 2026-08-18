from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from topos.backtesting.prices import backfill_ticker
from topos.collectors.prices import Bar
from topos.db.models import PriceBar
from topos.db.session import SessionLocal, init_db
from topos.screening.liquidity import assess, filter_signals, filter_tradeable
from topos.signals.base import Signal

_FIXTURE_TICKERS = ["LIQUID", "PENNY", "THIN", "NOBARS"]


class _StubCollector:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    def daily_bars(self, ticker: str) -> list[Bar]:
        return self._bars


def _bars(close: float, volume: float, count: int = 30) -> list[Bar]:
    return [
        Bar(
            date=date(2026, 6, 1) + timedelta(days=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
        )
        for i in range(count)
    ]


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    session.execute(delete(PriceBar).where(PriceBar.ticker.in_(_FIXTURE_TICKERS)))
    session.commit()

    # A normal large-cap: $50 stock trading 1M shares/day = $50M/day.
    backfill_ticker(db=session, ticker="LIQUID", collector=_StubCollector(_bars(50.0, 1_000_000)))
    # Sub-dollar shell, heavy share count but trivial dollar volume.
    backfill_ticker(db=session, ticker="PENNY", collector=_StubCollector(_bars(0.30, 500_000)))
    # Respectable price, almost no volume — can't actually be traded.
    backfill_ticker(db=session, ticker="THIN", collector=_StubCollector(_bars(45.0, 200)))
    try:
        yield session
    finally:
        session.execute(delete(PriceBar).where(PriceBar.ticker.in_(_FIXTURE_TICKERS)))
        session.commit()
        session.close()


def test_liquid_ticker_passes(db):
    verdict = assess(db, "LIQUID")

    assert verdict.tradeable is True
    assert verdict.avg_dollar_volume == pytest.approx(50_000_000.0)


def test_sub_dollar_stock_is_rejected(db):
    verdict = assess(db, "PENNY")

    assert verdict.tradeable is False
    assert "below" in verdict.reason


def test_illiquid_ticker_is_rejected_despite_healthy_price(db):
    # $45 x 200 shares = $9k/day. Real price, untradeable size.
    verdict = assess(db, "THIN")

    assert verdict.tradeable is False
    assert "dollar volume" in verdict.reason


def test_ticker_with_no_price_history_is_rejected_not_assumed_good(db):
    # Unknown liquidity is exactly the case that put untradeable names in
    # Ranked Opportunities — it must fail closed.
    verdict = assess(db, "NOBARS")

    assert verdict.tradeable is False
    assert "price bars" in verdict.reason


def test_filter_tradeable_splits_and_explains(db):
    keep, rejected = filter_tradeable(db, ["LIQUID", "PENNY", "THIN", "NOBARS"])

    assert keep == ["LIQUID"]
    assert {v.ticker for v in rejected} == {"PENNY", "THIN", "NOBARS"}
    assert all(v.reason for v in rejected)


def test_filter_signals_drops_untradeable_tickers(db):
    def _sig(ticker: str) -> Signal:
        return Signal(
            timestamp=datetime.now(timezone.utc),
            event_date=date(2026, 7, 1),
            dedup_key=f"sec_form4:{ticker}",
            source="sec_form4",
            ticker=ticker,
            confidence=0.9,
            evidence={"direction": "buy"},
        )

    kept = filter_signals(db, [_sig("LIQUID"), _sig("PENNY"), _sig("NOBARS")])

    assert [s.ticker for s in kept] == ["LIQUID"]


def test_thresholds_are_tunable(db):
    # THIN fails the default screen but passes a deliberately loose one.
    assert assess(db, "THIN").tradeable is False
    assert assess(db, "THIN", min_dollar_volume=1_000.0).tradeable is True
