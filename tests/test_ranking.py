from datetime import datetime, timezone

from topos.ranking.ranker import RankingEngine
from topos.signals.base import Signal


def test_rank_favors_multi_source_agreement():
    signals = [
        Signal(timestamp=datetime.now(timezone.utc), source="sec_form4", ticker="AAA", confidence=0.6),
        Signal(timestamp=datetime.now(timezone.utc), source="sec_form4", ticker="BBB", confidence=0.6),
        Signal(timestamp=datetime.now(timezone.utc), source="news", ticker="BBB", confidence=0.6),
    ]

    ranked = RankingEngine().rank(signals)

    assert ranked[0].ticker == "BBB"
    assert ranked[0].signal_count == 2
    assert ranked[1].ticker == "AAA"


def test_portfolio_and_risk_pipeline():
    from topos.db.models import RankedOpportunity
    from topos.portfolio.decision import PortfolioDecisionEngine
    from topos.risk.checks import RiskManager

    ranked = [
        RankedOpportunity(ticker="AAA", score=0.9, signal_count=2, sources=["sec_form4"]),
        RankedOpportunity(ticker="BBB", score=0.4, signal_count=1, sources=["sec_form4"]),
    ]

    targets = PortfolioDecisionEngine(top_n=5, min_score=0.5).decide(ranked)
    assert [t.ticker for t in targets] == ["AAA"]

    decision = RiskManager(max_position_weight=0.5).check(targets)
    assert [t.ticker for t in decision.approved] == ["AAA"]
    assert decision.approved[0].weight == 0.5
    assert decision.rejected == []


def test_risk_manager_rejects_beyond_max_positions():
    from topos.portfolio.decision import TargetPosition
    from topos.risk.checks import RiskManager

    targets = [
        TargetPosition(ticker="AAA", weight=0.5, score=0.9),
        TargetPosition(ticker="BBB", weight=0.5, score=0.8),
    ]

    decision = RiskManager(max_position_weight=1.0, max_positions=1).check(targets)
    assert [t.ticker for t in decision.approved] == ["AAA"]
    assert decision.rejected == [(targets[1], "exceeds max open positions")]
