from datetime import datetime

from titan.app.db.models import CongressionalTrade, InsiderTrade
from titan.app.scoring.engine import SignalScoringEngine


def _congress_trade(transaction_type: str, amount: float) -> CongressionalTrade:
    return CongressionalTrade(
        chamber="house",
        member="Test Rep",
        ticker="AAA",
        transaction_type=transaction_type,
        transaction_date=datetime(2026, 7, 1),
        amount_midpoint_usd=amount,
    )


def _insider_trade(direction: str, value: float, is_officer: bool = True) -> InsiderTrade:
    return InsiderTrade(
        ticker="AAA",
        owner_name="Test Owner",
        is_officer=is_officer,
        is_director=False,
        transaction_code="P" if direction == "buy" else "S",
        direction=direction,
        shares=1000.0,
        total_value_usd=value,
    )


def test_single_source_never_gets_buy_or_sell():
    engine = SignalScoringEngine()

    score = engine._score_ticker("AAA", [_congress_trade("purchase", 500_000)], [])

    assert score.recommendation == "HOLD"
    assert score.congress_signal_count == 1
    assert score.insider_signal_count == 0


def test_both_trackers_agreeing_buy_produces_buy():
    engine = SignalScoringEngine()

    score = engine._score_ticker(
        "AAA",
        [_congress_trade("purchase", 500_000)],
        [_insider_trade("buy", 800_000)],
    )

    assert score.recommendation == "BUY"
    assert score.net_direction == 1.0


def test_disagreeing_trackers_score_lower_and_stay_hold():
    engine = SignalScoringEngine()

    agree = engine._score_ticker(
        "AAA", [_congress_trade("purchase", 500_000)], [_insider_trade("buy", 800_000)]
    )
    disagree = engine._score_ticker(
        "AAA", [_congress_trade("purchase", 500_000)], [_insider_trade("sell", 800_000)]
    )

    assert disagree.recommendation == "HOLD"
    assert disagree.score < agree.score
    # Weights aren't symmetric (congress vs. insider sizing differs), so
    # this isn't exactly 0 — just confirm it's mild enough to stay under
    # the SELL threshold rather than asserting an exact value.
    assert -0.2 < disagree.net_direction < 0


def test_empty_ticker_scores_zero_and_holds():
    engine = SignalScoringEngine()

    score = engine._score_ticker("AAA", [], [])

    assert score.score == 0.0
    assert score.recommendation == "HOLD"
