"""The statistics have to be right, or the report is confident-sounding noise.

Correlation, permutation significance, and the weight recommendation are
each checked against data whose answer is known in advance — including
the cases that matter most: pure noise must NOT come back significant,
and a thin sample must never yield a recommendation to retune.
"""

import random
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete

from topos.backtesting.evaluate import evaluate_signals
from topos.backtesting.prices import backfill_ticker
from topos.backtesting.research import (
    MIN_SAMPLE_FOR_INFERENCE,
    CohortComparison,
    CohortResult,
    CorrelationResult,
    multi_vs_single_source,
    pearson,
    permutation_difference_p_value,
    permutation_p_value,
    score_return_correlation,
    spearman,
    weight_recommendation,
)
from topos.collectors.prices import Bar
from topos.db.models import PriceBar, RankedOpportunity
from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db

_START = date(2026, 1, 5)


# --- pure statistics -------------------------------------------------


def test_spearman_detects_perfect_monotonic_relationships():
    x = [1, 2, 3, 4, 5]

    assert spearman(x, [10, 20, 30, 40, 50]) == pytest.approx(1.0)
    assert spearman(x, [50, 40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_sees_monotonic_relationships_pearson_understates():
    # Exponential: perfectly ordered, badly non-linear. A score model only
    # needs to rank correctly, which is why Spearman is the headline.
    x = [1, 2, 3, 4, 5, 6]
    y = [2**i for i in x]

    assert spearman(x, y) == pytest.approx(1.0)
    assert pearson(x, y) < 0.95


def test_spearman_handles_ties():
    assert spearman([1, 2, 2, 3], [1, 2, 2, 3]) == pytest.approx(1.0)


def test_correlation_helpers_reject_degenerate_input():
    assert spearman([], []) is None
    assert spearman([1.0], [2.0]) is None
    assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None  # zero variance


def test_permutation_test_finds_a_real_relationship():
    x = list(range(40))
    y = [float(v) for v in x]

    p = permutation_p_value(x, y, spearman(x, y), iterations=2000)

    assert p < 0.01


def test_permutation_test_does_not_cry_wolf_on_noise():
    # The failure mode that matters most: random data must not come back
    # significant, or every report would manufacture a finding.
    rng = random.Random(11)
    x = [rng.gauss(0, 1) for _ in range(60)]
    y = [rng.gauss(0, 1) for _ in range(60)]

    p = permutation_p_value(x, y, spearman(x, y), iterations=2000)

    assert p > 0.05


def test_permutation_p_value_is_never_exactly_zero():
    # With finite permutations, p=0 is not a claim the data supports.
    x = list(range(30))
    y = [float(v) for v in x]

    assert permutation_p_value(x, y, spearman(x, y), iterations=100) > 0


def test_permutation_difference_separates_shifted_groups():
    rng = random.Random(5)
    high = [rng.gauss(0.05, 0.01) for _ in range(40)]
    low = [rng.gauss(0.00, 0.01) for _ in range(40)]

    assert permutation_difference_p_value(high, low, iterations=2000) < 0.01
    # Two samples from the same distribution must not separate.
    same_a = [rng.gauss(0, 0.01) for _ in range(40)]
    same_b = [rng.gauss(0, 0.01) for _ in range(40)]
    assert permutation_difference_p_value(same_a, same_b, iterations=2000) > 0.05


# --- recommendation guardrails ---------------------------------------


def _correlation(n: int, rho: float | None, p: float | None) -> CorrelationResult:
    return CorrelationResult(n=n, spearman=rho, pearson=rho, p_value=p, horizon_days=20)


def _cohorts(verdict_diff: float | None, p: float | None, n: int = 50) -> CohortComparison:
    return CohortComparison(
        horizon_days=20,
        cohorts=[
            CohortResult("single-source", n, 0.01, 0.5),
            CohortResult("multi-source", n, 0.02, 0.6),
        ],
        p_value=p,
        difference=verdict_diff,
    )


def test_thin_sample_never_recommends_retuning():
    result = weight_recommendation(
        _correlation(n=MIN_SAMPLE_FOR_INFERENCE - 1, rho=0.9, p=0.001),
        _cohorts(0.02, 0.001),
        [],
    )

    # Even with a spectacular-looking correlation, too few observations
    # means no change is defensible.
    assert result.verdict == "UNCHANGED"
    assert result.safe_to_act is False
    assert "need" in " ".join(result.reasons).lower() or "only" in " ".join(result.reasons).lower()


def test_insignificant_correlation_recommends_unchanged():
    result = weight_recommendation(
        _correlation(n=200, rho=0.05, p=0.62), _cohorts(0.001, 0.8), []
    )

    assert result.verdict == "UNCHANGED"
    assert "no significant relationship" in " ".join(result.reasons).lower()


def test_negative_correlation_triggers_investigation_not_retuning():
    result = weight_recommendation(
        _correlation(n=200, rho=-0.4, p=0.001), _cohorts(0.0, 0.9), []
    )

    assert result.verdict == "INVESTIGATE"
    assert "look-ahead" in " ".join(result.reasons).lower()


def test_positive_correlation_with_multi_source_edge_recommends_increase():
    result = weight_recommendation(
        _correlation(n=200, rho=0.35, p=0.001), _cohorts(0.02, 0.01), []
    )

    assert result.verdict == "INCREASE"
    assert result.safe_to_act is True


def test_multi_source_underperformance_recommends_decrease():
    result = weight_recommendation(
        _correlation(n=200, rho=0.35, p=0.001), _cohorts(-0.02, 0.01), []
    )

    assert result.verdict == "DECREASE"


def test_provisional_sample_is_flagged_and_not_safe_to_act():
    result = weight_recommendation(
        _correlation(n=40, rho=0.35, p=0.01), _cohorts(0.02, 0.2), []
    )

    assert result.safe_to_act is False
    assert any("PROVISIONAL" in r for r in result.reasons)


# --- end to end against real Postgres --------------------------------


class _Stub:
    def __init__(self, closes):
        self._closes = closes

    def daily_bars(self, ticker):
        return [
            Bar(date=_START + timedelta(days=i), open=c, high=c, low=c, close=c, volume=2e6)
            for i, c in enumerate(self._closes)
        ]


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    # 80 so a 50/50 cohort split clears the n>=30 inference threshold.
    tickers = [f"RS{i:02d}" for i in range(80)]

    def _clean():
        session.execute(delete(PriceBar).where(PriceBar.ticker.in_(tickers)))
        session.execute(delete(SignalRow).where(SignalRow.ticker.in_(tickers)))
        session.execute(delete(RankedOpportunity).where(RankedOpportunity.ticker.in_(tickers)))
        session.commit()

    _clean()
    try:
        yield session, tickers
    finally:
        _clean()
        session.close()


def test_correlation_recovers_a_planted_relationship(db):
    session, tickers = db
    rng = random.Random(3)

    # Plant a monotonic relationship: higher score -> stronger drift.
    for index, ticker in enumerate(tickers):
        score = 20.0 + index  # 20 .. 99
        drift = (score - 60) / 60 * 0.004
        price, closes = 100.0, []
        for _ in range(40):
            price *= 1 + drift + rng.gauss(0, 0.002)
            closes.append(round(price, 2))
        backfill_ticker(db=session, ticker=ticker, collector=_Stub(closes))
        session.add(
            RankedOpportunity(
                ticker=ticker, score=score, recommendation="BUY", net_direction=1.0,
                signal_count=2, sources=["sec_form4", "congress_house"],
                rank_timestamp=datetime(2026, 1, 5, 12, 0, 0),
            )
        )
    session.commit()

    result = score_return_correlation(session, horizon_days=20)

    assert result.n == 80
    assert result.spearman > 0.5
    assert result.p_value < 0.05
    assert result.verdict.startswith("POSITIVE")


def test_correlation_reports_no_relationship_when_none_exists(db):
    session, tickers = db
    rng = random.Random(9)

    # Scores assigned at random, returns independent of them.
    for index, ticker in enumerate(tickers):
        price, closes = 100.0, []
        for _ in range(40):
            price *= 1 + rng.gauss(0, 0.004)
            closes.append(round(price, 2))
        backfill_ticker(db=session, ticker=ticker, collector=_Stub(closes))
        session.add(
            RankedOpportunity(
                ticker=ticker, score=rng.uniform(20, 95), recommendation="BUY",
                net_direction=1.0, signal_count=2, sources=["sec_form4"],
                rank_timestamp=datetime(2026, 1, 5, 12, 0, 0),
            )
        )
    session.commit()

    result = score_return_correlation(session, horizon_days=20)

    assert result.n == 80
    # The honest answer on noise is "no relationship", not a small
    # positive number dressed up as a finding.
    assert result.verdict in ("NO SIGNIFICANT RELATIONSHIP", "INSUFFICIENT DATA")


def test_multi_vs_single_source_separates_cohorts(db):
    session, tickers = db
    rng = random.Random(17)

    for index, ticker in enumerate(tickers):
        multi = index % 2 == 0
        drift = 0.004 if multi else -0.001
        price, closes = 100.0, []
        for _ in range(40):
            price *= 1 + drift + rng.gauss(0, 0.002)
            closes.append(round(price, 2))
        backfill_ticker(db=session, ticker=ticker, collector=_Stub(closes))
        session.add(
            RankedOpportunity(
                ticker=ticker, score=70.0, recommendation="BUY", net_direction=1.0,
                signal_count=2 if multi else 1,
                sources=["sec_form4", "congress_house"] if multi else ["sec_form4"],
                rank_timestamp=datetime(2026, 1, 5, 12, 0, 0),
            )
        )
    session.commit()

    comparison = multi_vs_single_source(session, horizon_days=20)

    by_label = {c.label: c for c in comparison.cohorts}
    assert by_label["multi-source"].n == 40
    assert by_label["single-source"].n == 40
    assert comparison.difference > 0
    assert comparison.verdict == "MULTI-SOURCE OUTPERFORMS"
