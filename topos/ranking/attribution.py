"""Additive score attribution: score = contributions + bonuses - penalties.

The previous formula multiplied an average confidence by a diversity
bonus and a conviction factor. That produced a defensible number but an
unexplainable one — there was no way to say how many points a Form 4
contributed versus a news article, because in a product every factor
scales every other one.

This restates the same judgments additively so every point is traceable
to a named cause. The two hard-won invariants are preserved deliberately:

1. Direction still matters. Sources that disagree incur an explicit
   conflict penalty rather than quietly averaging out.
2. A single source still cannot produce a BUY or SELL. That rule lives
   in the ranking engine, but the attribution makes the reason visible.

`ScoreBreakdown.verify()` asserts the parts sum to the total. If a future
change breaks that identity, the explanation would be a plausible-looking
fiction, which is worse than no explanation at all — so it's a test, not
a comment.
"""

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from topos.signals.base import Signal

# Points added per additional agreeing source, and the ceiling on that
# bonus — agreement is evidence, but the fifth confirming source is worth
# less than the second.
AGREEMENT_BONUS_PER_SOURCE = 5.0
MAX_AGREEMENT_BONUS = 20.0

# Full weight when sources are unanimous, this much subtracted when
# they're perfectly split.
MAX_CONFLICT_PENALTY = 25.0

# A filing from three months ago is not the trade signal a filing from
# yesterday is.
STALENESS_HORIZON_DAYS = 90
MAX_STALENESS_PENALTY = 15.0


@dataclass
class SourceContribution:
    source: str
    signal_count: int
    avg_confidence: float
    direction: str
    points: float
    aligned: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreAdjustment:
    """A bonus (positive points) or penalty (negative points)."""

    label: str
    points: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreBreakdown:
    ticker: str
    score: float
    net_direction: float
    contributions: list[SourceContribution] = field(default_factory=list)
    adjustments: list[ScoreAdjustment] = field(default_factory=list)

    @property
    def base_points(self) -> float:
        return sum(c.points for c in self.contributions)

    def verify(self, tolerance: float = 1e-6) -> bool:
        """Whether the stated parts actually add up to the stated score."""
        total = self.base_points + sum(a.points for a in self.adjustments)
        return abs(total - self.score) <= tolerance

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "score": self.score,
            "net_direction": self.net_direction,
            "base_points": round(self.base_points, 2),
            "contributions": [c.to_dict() for c in self.contributions],
            "adjustments": [a.to_dict() for a in self.adjustments],
        }


def _dominant_direction(signals: list[Signal]) -> str:
    """The direction a source is pulling, weighted by confidence."""
    buy = sum(s.confidence for s in signals if s.evidence.get("direction") == "buy")
    sell = sum(s.confidence for s in signals if s.evidence.get("direction") == "sell")
    if buy > sell:
        return "buy"
    if sell > buy:
        return "sell"
    return "neutral"


def build_breakdown(
    ticker: str, signals: list[Signal], as_of: date | None = None
) -> ScoreBreakdown:
    """Scores a ticker and shows its work.

    `as_of` is the date the score is being computed for — it drives the
    staleness penalty. It's a parameter rather than an implicit "now" so a
    backtest can reconstruct the score a ticker would have had on a past
    date instead of penalizing every historical signal for being old today.
    """
    by_source: dict[str, list[Signal]] = {}
    for signal in signals:
        by_source.setdefault(signal.source, []).append(signal)

    buy_weight = sum(s.confidence for s in signals if s.evidence.get("direction") == "buy")
    sell_weight = sum(s.confidence for s in signals if s.evidence.get("direction") == "sell")
    total_weight = buy_weight + sell_weight
    net_direction = (buy_weight - sell_weight) / total_weight if total_weight else 0.0

    overall_direction = "buy" if net_direction > 0 else "sell" if net_direction < 0 else "neutral"

    # Base points: the confidence-weighted average across sources, on a
    # 0-100 scale. Each source's contribution is its share of that
    # average, so the contributions sum exactly to the base.
    source_confidences = {
        source: sum(s.confidence for s in group) / len(group)
        for source, group in by_source.items()
    }
    base_points = (
        sum(source_confidences.values()) / len(source_confidences) * 100
        if source_confidences
        else 0.0
    )
    confidence_total = sum(source_confidences.values())

    contributions: list[SourceContribution] = []
    for source, group in sorted(by_source.items()):
        avg_conf = source_confidences[source]
        share = (avg_conf / confidence_total) if confidence_total else 0.0
        direction = _dominant_direction(group)
        contributions.append(
            SourceContribution(
                source=source,
                signal_count=len(group),
                avg_confidence=round(avg_conf, 3),
                direction=direction,
                points=round(base_points * share, 2),
                aligned=(direction == overall_direction),
            )
        )

    # Rounding each contribution independently can drift a cent or two
    # from the base; fold that back into the largest contribution so the
    # parts still sum exactly.
    drift = round(base_points - sum(c.points for c in contributions), 2)
    if drift and contributions:
        largest = max(contributions, key=lambda c: abs(c.points))
        largest.points = round(largest.points + drift, 2)

    base_points = sum(c.points for c in contributions)

    adjustments: list[ScoreAdjustment] = []

    agreeing = [c for c in contributions if c.aligned and c.direction != "neutral"]
    if len(agreeing) >= 2:
        bonus = min(
            AGREEMENT_BONUS_PER_SOURCE * (len(agreeing) - 1), MAX_AGREEMENT_BONUS
        )
        adjustments.append(
            ScoreAdjustment(
                label="Multi-source agreement",
                points=round(bonus, 2),
                detail=f"{len(agreeing)} sources agree on {overall_direction}",
            )
        )

    if total_weight and abs(net_direction) < 1.0:
        penalty = MAX_CONFLICT_PENALTY * (1 - abs(net_direction))
        opposed = [c.source for c in contributions if not c.aligned and c.direction != "neutral"]
        adjustments.append(
            ScoreAdjustment(
                label="Conflicting signals",
                points=-round(penalty, 2),
                detail=(
                    f"{', '.join(opposed)} disagree with the majority"
                    if opposed
                    else "sources are not unanimous"
                ),
            )
        )

    if as_of is not None and signals:
        newest = max(s.event_date for s in signals)
        age_days = (as_of - newest).days
        if age_days > 0:
            penalty = min(age_days / STALENESS_HORIZON_DAYS, 1.0) * MAX_STALENESS_PENALTY
            if round(penalty, 2) > 0:
                adjustments.append(
                    ScoreAdjustment(
                        label="Staleness",
                        points=-round(penalty, 2),
                        detail=f"newest signal is {age_days} day(s) old",
                    )
                )

    raw_score = base_points + sum(a.points for a in adjustments)
    score = round(min(max(raw_score, 0.0), 100.0), 2)

    # If clamping moved the number, say so explicitly rather than letting
    # the breakdown silently fail to add up.
    clamp_delta = round(score - round(raw_score, 2), 2)
    if clamp_delta:
        adjustments.append(
            ScoreAdjustment(
                label="Clamped to 0-100",
                points=clamp_delta,
                detail=f"raw total was {raw_score:.2f}",
            )
        )

    return ScoreBreakdown(
        ticker=ticker,
        score=score,
        net_direction=round(net_direction, 3),
        contributions=contributions,
        adjustments=adjustments,
    )
