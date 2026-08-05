"""score = contributions + bonuses - penalties, and it must actually add up.

An explanation that doesn't reconcile to the number it explains is worse
than no explanation, so the summing identity is asserted directly rather
than assumed.
"""

from datetime import date, datetime, timezone

import pytest

from topos.ranking.attribution import build_breakdown
from topos.ranking.ranker import RankingEngine
from topos.signals.base import Signal


def _signal(
    ticker: str,
    source: str,
    confidence: float,
    direction: str,
    event_date: date = date(2026, 7, 1),
) -> Signal:
    return Signal(
        timestamp=datetime.now(timezone.utc),
        event_date=event_date,
        dedup_key=f"{source}:{ticker}:{direction}:{event_date}",
        source=source,
        ticker=ticker,
        confidence=confidence,
        evidence={"direction": direction},
    )


def test_breakdown_sums_to_the_score():
    breakdown = build_breakdown(
        "AAA",
        [
            _signal("AAA", "sec_form4", 0.8, "buy"),
            _signal("AAA", "congress_house", 0.6, "buy"),
            _signal("AAA", "news_sentiment", 0.4, "sell"),
        ],
    )

    assert breakdown.verify()


@pytest.mark.parametrize(
    "signals",
    [
        [("sec_form4", 0.9, "buy")],
        [("sec_form4", 0.9, "buy"), ("congress_house", 0.9, "buy")],
        [("sec_form4", 0.9, "buy"), ("congress_house", 0.9, "sell")],
        [("sec_form4", 0.1, "sell"), ("news_sentiment", 0.2, "sell")],
        [
            ("sec_form4", 1.0, "buy"),
            ("congress_house", 1.0, "buy"),
            ("news_sentiment", 1.0, "buy"),
            ("technical", 1.0, "buy"),
            ("institutional_13f", 1.0, "buy"),
        ],
    ],
)
def test_breakdown_sums_across_many_shapes(signals):
    # Including the 5-source unanimous case, which clamps at 100 — the
    # clamp is recorded as an explicit adjustment so the identity holds.
    breakdown = build_breakdown("AAA", [_signal("AAA", s, c, d) for s, c, d in signals])

    assert breakdown.verify(), breakdown.to_dict()
    assert 0.0 <= breakdown.score <= 100.0


def test_each_source_gets_its_own_attributed_points():
    breakdown = build_breakdown(
        "AAA",
        [
            _signal("AAA", "sec_form4", 0.8, "buy"),
            _signal("AAA", "congress_house", 0.4, "buy"),
        ],
    )

    points = {c.source: c.points for c in breakdown.contributions}

    # The stronger source should carry more of the base.
    assert points["sec_form4"] > points["congress_house"]
    assert set(points) == {"sec_form4", "congress_house"}


def test_agreement_produces_a_bonus():
    breakdown = build_breakdown(
        "AAA",
        [
            _signal("AAA", "sec_form4", 0.7, "buy"),
            _signal("AAA", "congress_house", 0.7, "buy"),
        ],
    )

    labels = {a.label: a.points for a in breakdown.adjustments}

    assert labels["Multi-source agreement"] > 0
    assert "Conflicting signals" not in labels


def test_disagreement_produces_a_penalty_and_names_the_dissenter():
    breakdown = build_breakdown(
        "AAA",
        [
            _signal("AAA", "sec_form4", 0.7, "buy"),
            _signal("AAA", "news_sentiment", 0.5, "sell"),
        ],
    )

    conflict = next(a for a in breakdown.adjustments if a.label == "Conflicting signals")

    assert conflict.points < 0
    assert "news_sentiment" in conflict.detail


def test_agreement_bonus_is_capped():
    many = [
        _signal("AAA", f"source_{i}", 0.8, "buy") for i in range(10)
    ]

    breakdown = build_breakdown("AAA", many)
    bonus = next(a for a in breakdown.adjustments if a.label == "Multi-source agreement")

    assert bonus.points == 20.0


def test_stale_signals_are_penalized_relative_to_fresh_ones():
    fresh = build_breakdown(
        "AAA",
        [
            _signal("AAA", "sec_form4", 0.8, "buy", event_date=date(2026, 7, 1)),
            _signal("AAA", "congress_house", 0.8, "buy", event_date=date(2026, 7, 1)),
        ],
        as_of=date(2026, 7, 2),
    )
    stale = build_breakdown(
        "AAA",
        [
            _signal("AAA", "sec_form4", 0.8, "buy", event_date=date(2026, 1, 1)),
            _signal("AAA", "congress_house", 0.8, "buy", event_date=date(2026, 1, 1)),
        ],
        as_of=date(2026, 7, 2),
    )

    assert stale.score < fresh.score
    assert any(a.label == "Staleness" for a in stale.adjustments)
    assert fresh.verify() and stale.verify()


def test_staleness_is_relative_to_as_of_not_wall_clock():
    # A backtest reconstructing a past score must not penalize a signal
    # for being old *today*.
    signals = [
        _signal("AAA", "sec_form4", 0.8, "buy", event_date=date(2026, 1, 1)),
        _signal("AAA", "congress_house", 0.8, "buy", event_date=date(2026, 1, 1)),
    ]

    at_the_time = build_breakdown("AAA", signals, as_of=date(2026, 1, 2))

    assert not any(a.label == "Staleness" and a.points < -1 for a in at_the_time.adjustments)


def test_no_staleness_penalty_when_as_of_is_omitted():
    breakdown = build_breakdown(
        "AAA", [_signal("AAA", "sec_form4", 0.8, "buy", event_date=date(2020, 1, 1))]
    )

    assert not any(a.label == "Staleness" for a in breakdown.adjustments)


def test_ranking_engine_persists_the_breakdown():
    ranked = RankingEngine().rank(
        [
            _signal("AAA", "sec_form4", 0.7, "buy"),
            _signal("AAA", "congress_house", 0.6, "buy"),
        ]
    )

    attribution = ranked[0].attribution

    assert attribution["ticker"] == "AAA"
    assert {c["source"] for c in attribution["contributions"]} == {
        "sec_form4",
        "congress_house",
    }
    total = attribution["base_points"] + sum(a["points"] for a in attribution["adjustments"])
    assert total == pytest.approx(ranked[0].score, abs=1e-6)


def test_invariants_survive_the_rewrite():
    """The two rules the additive rewrite had to preserve."""
    engine = RankingEngine()

    # 1. One source alone never yields BUY/SELL, however strong.
    [single] = engine.rank([_signal("AAA", "sec_form4", 0.95, "buy")])
    assert single.score >= 60
    assert single.recommendation == "HOLD"

    # 2. Disagreement scores lower than agreement.
    [agree] = engine.rank(
        [
            _signal("BBB", "sec_form4", 0.7, "buy"),
            _signal("BBB", "congress_house", 0.7, "buy"),
        ]
    )
    [disagree] = engine.rank(
        [
            _signal("CCC", "sec_form4", 0.7, "buy"),
            _signal("CCC", "congress_house", 0.7, "sell"),
        ]
    )
    assert agree.recommendation == "BUY"
    assert disagree.recommendation == "HOLD"
    assert disagree.score < agree.score
