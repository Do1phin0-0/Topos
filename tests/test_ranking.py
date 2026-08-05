from datetime import date, datetime, timezone

from topos.db.models import RankedOpportunity
from topos.portfolio.decision import PortfolioDecisionEngine, TargetPosition
from topos.ranking.ranker import RankingEngine
from topos.risk.checks import RiskManager
from topos.signals.base import Signal


def _signal(ticker: str, source: str, confidence: float, direction: str | None = None) -> Signal:
    evidence = {"direction": direction} if direction else {}
    return Signal(
        timestamp=datetime.now(timezone.utc),
        event_date=date(2026, 7, 1),
        dedup_key=f"{source}:{ticker}:{direction}",
        source=source,
        ticker=ticker,
        confidence=confidence,
        evidence=evidence,
    )


def test_rank_favors_multi_source_agreement():
    # Directions are supplied because the additive attribution model
    # rewards sources *agreeing on a direction*, not merely both having
    # mentioned the ticker. Every real extractor sets a direction; the
    # earlier version of this test omitted it, which no live signal does.
    signals = [
        _signal("AAA", "sec_form4", 0.6, direction="buy"),
        _signal("BBB", "sec_form4", 0.6, direction="buy"),
        _signal("BBB", "news_sentiment", 0.6, direction="buy"),
    ]

    ranked = RankingEngine().rank(signals)

    assert ranked[0].ticker == "BBB"
    assert ranked[0].signal_count == 2
    assert ranked[1].ticker == "AAA"


def test_source_count_alone_does_not_raise_the_score():
    # Two sources that merely mention a ticker, with no directional view,
    # are not corroboration — the bonus is for agreement, not headcount.
    one = RankingEngine().rank([_signal("AAA", "sec_form4", 0.6)])[0]
    two = RankingEngine().rank(
        [_signal("BBB", "sec_form4", 0.6), _signal("BBB", "news_sentiment", 0.6)]
    )[0]

    assert two.score == one.score


def test_single_source_never_gets_buy_or_sell_recommendation():
    # One strong signal alone shouldn't produce BUY/SELL, however high the
    # score — the project's own principle is not to blindly follow a
    # single source. It caps out at HOLD until a second source agrees.
    signals = [_signal("AAA", "sec_form4", 0.9, direction="buy")]

    ranked = RankingEngine().rank(signals)

    assert ranked[0].score >= 60  # score alone would have cleared BUY
    assert ranked[0].recommendation == "HOLD"


def test_two_agreeing_sources_produce_buy_recommendation():
    signals = [
        _signal("AAA", "sec_form4", 0.7, direction="buy"),
        _signal("AAA", "congress_house", 0.6, direction="buy"),
    ]

    ranked = RankingEngine().rank(signals)

    assert ranked[0].recommendation == "BUY"
    assert ranked[0].net_direction == 1.0


def test_disagreeing_signals_score_lower_and_stay_hold():
    agreeing = [
        _signal("AAA", "sec_form4", 0.7, direction="buy"),
        _signal("AAA", "congress_house", 0.7, direction="buy"),
    ]
    disagreeing = [
        _signal("BBB", "sec_form4", 0.7, direction="buy"),
        _signal("BBB", "congress_house", 0.7, direction="sell"),
    ]

    ranked_agree = RankingEngine().rank(agreeing)
    ranked_disagree = RankingEngine().rank(disagreeing)

    assert ranked_agree[0].recommendation == "BUY"
    assert ranked_disagree[0].recommendation == "HOLD"
    assert ranked_disagree[0].score < ranked_agree[0].score
    assert ranked_disagree[0].net_direction == 0.0


def test_portfolio_only_selects_buy_even_if_sell_scores_higher():
    ranked = [
        RankedOpportunity(
            ticker="SELLME",
            score=95.0,
            recommendation="SELL",
            net_direction=-1.0,
            signal_count=3,
            sources=["sec_form4", "congress_house", "news_sentiment"],
        ),
        RankedOpportunity(
            ticker="BUYME",
            score=70.0,
            recommendation="BUY",
            net_direction=1.0,
            signal_count=2,
            sources=["sec_form4", "congress_house"],
        ),
    ]

    targets = PortfolioDecisionEngine(top_n=5, min_score=50.0).decide(ranked)

    assert [t.ticker for t in targets] == ["BUYME"]


def test_portfolio_and_risk_pipeline():
    ranked = [
        RankedOpportunity(
            ticker="AAA",
            score=90.0,
            recommendation="BUY",
            net_direction=1.0,
            signal_count=2,
            sources=["sec_form4", "congress_house"],
        ),
        RankedOpportunity(
            ticker="BBB",
            score=40.0,
            recommendation="HOLD",
            net_direction=0.0,
            signal_count=1,
            sources=["sec_form4"],
        ),
    ]

    targets = PortfolioDecisionEngine(top_n=5, min_score=50.0).decide(ranked)
    assert [t.ticker for t in targets] == ["AAA"]

    decision = RiskManager(max_position_weight=0.5).check(targets)
    assert [t.ticker for t in decision.approved] == ["AAA"]
    assert decision.approved[0].weight == 0.5
    assert decision.rejected == []


def test_risk_manager_rejects_beyond_max_positions():
    targets = [
        TargetPosition(ticker="AAA", weight=0.5, score=90.0),
        TargetPosition(ticker="BBB", weight=0.5, score=80.0),
    ]

    decision = RiskManager(max_position_weight=1.0, max_positions=1).check(targets)
    assert [t.ticker for t in decision.approved] == ["AAA"]
    assert decision.rejected == [(targets[1], "exceeds max open positions")]
