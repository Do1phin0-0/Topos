from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from topos.backtesting.evaluate import (
    _sharpe,
    evaluate_score_buckets,
    evaluate_signals,
)
from topos.backtesting.prices import backfill_ticker
from topos.collectors.prices import Bar
from topos.db.models import PriceBar, RankedOpportunity
from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db

_TICKERS = ["UPCO", "DOWNCO"]
_START = date(2026, 6, 1)


class _StubCollector:
    def __init__(self, closes: list[float]) -> None:
        self._closes = closes

    def daily_bars(self, ticker: str) -> list[Bar]:
        return [
            Bar(
                date=_START + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=1_000_000.0,
            )
            for i, c in enumerate(self._closes)
        ]


def _signal(ticker: str, source: str, direction: str, confidence: float, key: str) -> SignalRow:
    return SignalRow(
        timestamp=datetime.now(timezone.utc),
        event_date=_START,
        dedup_key=key,
        source=source,
        ticker=ticker,
        confidence=confidence,
        evidence={"direction": direction},
    )


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
    # UPCO climbs 100 -> 110 over 5 sessions (+10%).
    backfill_ticker(db=session, ticker="UPCO", collector=_StubCollector([100, 102, 104, 106, 108, 110]))
    # DOWNCO falls 100 -> 90 over 5 sessions (-10%).
    backfill_ticker(db=session, ticker="DOWNCO", collector=_StubCollector([100, 98, 96, 94, 92, 90]))
    try:
        yield session
    finally:
        _clean()
        session.close()


def test_correct_sell_call_counts_as_a_win_not_a_loss(db):
    # The signal said "sell" and the stock fell 10%. Following it earned
    # +10%; grading it on raw price change would score it as a loser.
    db.add(_signal("DOWNCO", "sec_form4", "sell", 0.8, "k-sell-right"))
    db.commit()

    [result] = evaluate_signals(db, horizons=(5,))
    stats = result.horizons[5]

    assert stats.sample_size == 1
    assert stats.avg_return == pytest.approx(0.10)
    assert stats.win_rate == 1.0


def test_wrong_buy_call_counts_as_a_loss(db):
    db.add(_signal("DOWNCO", "sec_form4", "buy", 0.8, "k-buy-wrong"))
    db.commit()

    [result] = evaluate_signals(db, horizons=(5,))

    assert result.horizons[5].avg_return == pytest.approx(-0.10)
    assert result.horizons[5].win_rate == 0.0


def test_signals_are_grouped_by_source(db):
    db.add(_signal("UPCO", "sec_form4", "buy", 0.8, "bt-k1"))
    db.add(_signal("DOWNCO", "congress_house", "buy", 0.8, "bt-k2"))
    db.commit()

    results = {r.label: r for r in evaluate_signals(db, horizons=(5,))}

    assert results["sec_form4"].horizons[5].avg_return == pytest.approx(0.10)
    assert results["congress_house"].horizons[5].avg_return == pytest.approx(-0.10)


def test_neutral_signals_are_not_graded(db):
    # No directional claim means nothing to be right or wrong about.
    db.add(_signal("UPCO", "sec_form4", "neutral", 0.8, "k-neutral"))
    db.commit()

    assert evaluate_signals(db, horizons=(5,)) == []


def test_unmeasurable_signals_are_excluded_not_counted_as_flat(db):
    # Only 6 bars exist, so a 60-day horizon can't be measured. Counting
    # it as 0% would drag the average toward zero and understate risk.
    db.add(_signal("UPCO", "sec_form4", "buy", 0.8, "k-short"))
    db.commit()

    [result] = evaluate_signals(db, horizons=(5, 60))

    assert result.horizons[5].sample_size == 1
    assert result.horizons[60].sample_size == 0
    assert result.horizons[60].avg_return is None


def test_confidence_bucketing(db):
    db.add(_signal("UPCO", "sec_form4", "buy", 0.85, "k-high"))
    db.add(_signal("DOWNCO", "sec_form4", "buy", 0.25, "k-low"))
    db.commit()

    labels = {r.label for r in evaluate_signals(db, horizons=(5,), group_by="confidence")}

    assert labels == {"80-90%", "20-30%"}


def test_score_buckets_grade_the_recommendation_as_issued(db):
    db.add(
        RankedOpportunity(
            ticker="UPCO", score=85.0, recommendation="BUY", net_direction=1.0,
            signal_count=2, sources=["sec_form4"],
            rank_timestamp=datetime(2026, 6, 1, 12, 0, 0),
        )
    )
    db.add(
        RankedOpportunity(
            ticker="DOWNCO", score=65.0, recommendation="BUY", net_direction=1.0,
            signal_count=2, sources=["sec_form4"],
            rank_timestamp=datetime(2026, 6, 1, 12, 0, 0),
        )
    )
    db.commit()

    results = {r.label: r for r in evaluate_score_buckets(db, horizons=(5,))}

    assert results["80-90"].horizons[5].avg_return == pytest.approx(0.10)
    assert results["60-70"].horizons[5].avg_return == pytest.approx(-0.10)


def test_score_buckets_sort_numerically_not_lexically(db):
    for score in (95.0, 25.0, 5.0):
        db.add(
            RankedOpportunity(
                ticker="UPCO", score=score, recommendation="BUY", net_direction=1.0,
                signal_count=1, sources=["sec_form4"],
                rank_timestamp=datetime(2026, 6, 1, 12, 0, 0),
            )
        )
    db.commit()

    labels = [r.label for r in evaluate_score_buckets(db, horizons=(5,))]

    # Lexical sorting would put "0-10" after "20-30".
    assert labels == ["0-10", "20-30", "90-100"]


def test_sell_recommendation_is_graded_on_its_downside(db):
    db.add(
        RankedOpportunity(
            ticker="DOWNCO", score=85.0, recommendation="SELL", net_direction=-1.0,
            signal_count=2, sources=["sec_form4"],
            rank_timestamp=datetime(2026, 6, 1, 12, 0, 0),
        )
    )
    db.commit()

    [result] = evaluate_score_buckets(db, horizons=(5,), recommendation="SELL")

    assert result.horizons[5].avg_return == pytest.approx(0.10)


def test_sharpe_is_annualized_by_holding_period():
    returns = [0.01, 0.02, -0.01, 0.03, 0.00]
    mean = sum(returns) / len(returns)
    import statistics

    ratio = mean / statistics.stdev(returns)

    # A 5-day hold compounds ~50x a year; a 60-day hold ~4x. The same
    # per-trade edge should not score identically at both.
    assert _sharpe(returns, 5) == pytest.approx(ratio * (252 / 5) ** 0.5)
    assert _sharpe(returns, 60) == pytest.approx(ratio * (252 / 60) ** 0.5)
    assert _sharpe(returns, 5) > _sharpe(returns, 60)


def test_sharpe_is_none_when_undefined():
    assert _sharpe([0.05], 5) is None  # single observation
    assert _sharpe([0.05, 0.05], 5) is None  # zero variance


def test_thin_buckets_are_flagged_as_not_meaningful(db):
    db.add(_signal("UPCO", "sec_form4", "buy", 0.8, "k-thin"))
    db.commit()

    [result] = evaluate_signals(db, horizons=(5,))

    assert result.horizons[5].sample_size == 1
    assert result.horizons[5].is_meaningful is False
