"""Statistical tests for whether the scoring model predicts anything.

Three questions, in order of importance:

1. Does a higher score correspond to a higher forward return?
2. Do multi-source signals outperform single-source ones?
3. Given the above, should the hand-tuned weights change?

Significance is established by permutation test rather than a
t-distribution approximation. The samples here are small and financial
returns are famously non-normal; a normal approximation would overstate
significance exactly when the sample is thinnest, which is the failure
mode this whole exercise exists to avoid. A permutation test makes no
distributional assumption: it shuffles the labels many times and asks how
often chance alone produces a result this extreme.
"""

import random
import statistics
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from topos.backtesting.evaluate import _measure
from topos.backtesting.prices import forward_return
from topos.db.models import RankedOpportunity
from topos.db.models import Signal as SignalRow

# Below this, no inference is attempted at all.
MIN_SAMPLE_FOR_INFERENCE = 30
# Below this, findings are reported but flagged as provisional.
MIN_SAMPLE_FOR_CONFIDENCE = 100

# Significance is not the same thing as size, and a large sample makes the
# difference stark: at n≈11,000 a Spearman of 0.02 clears p<0.05 while
# explaining 0.04% of the variation in returns. Reporting that as "the
# ranking has directional validity" is how a backtest manufactures
# confidence — the number is real, the edge is not.
#
# 0.05 is deliberately a low bar rather than a safe one. Quant equity
# desks do trade information coefficients in this range, but only with
# transaction costs, turnover and breadth modelled, none of which Topos
# does. Clearing it means "worth investigating", never "worth trading".
MIN_ACTIONABLE_CORRELATION = 0.05

PERMUTATIONS = 10_000
_SEED = 20260805  # fixed so a report is reproducible


@dataclass
class CorrelationResult:
    n: int
    spearman: float | None
    pearson: float | None
    p_value: float | None
    horizon_days: int

    @property
    def is_negligible(self) -> bool:
        """Statistically detectable, too small to mean anything.

        Kept distinct from "no relationship" because they call for
        different responses: no relationship means look elsewhere, this
        means the effect is real but a rounding error next to the costs
        and variance of actually trading it.
        """
        return (
            self.spearman is not None
            and abs(self.spearman) < MIN_ACTIONABLE_CORRELATION
        )

    @property
    def variance_explained(self) -> float | None:
        """The share of return variation the score accounts for."""
        return None if self.spearman is None else self.spearman**2

    @property
    def verdict(self) -> str:
        if self.n < MIN_SAMPLE_FOR_INFERENCE:
            return "INSUFFICIENT DATA"
        if self.p_value is None or self.spearman is None:
            return "INSUFFICIENT DATA"
        if self.p_value > 0.05:
            return "NO SIGNIFICANT RELATIONSHIP"
        if self.is_negligible:
            return (
                f"NEGLIGIBLE — statistically detectable at n={self.n}, "
                f"but |rho|={abs(self.spearman):.3f} explains "
                f"{self.variance_explained:.2%} of return variation"
            )
        if self.spearman > 0:
            return "POSITIVE — higher scores earned higher returns"
        return "NEGATIVE — higher scores earned LOWER returns"

    @property
    def is_provisional(self) -> bool:
        return self.n < MIN_SAMPLE_FOR_CONFIDENCE


@dataclass
class CohortResult:
    label: str
    n: int
    mean_return: float | None
    win_rate: float | None


@dataclass
class CohortComparison:
    horizon_days: int
    cohorts: list[CohortResult] = field(default_factory=list)
    p_value: float | None = None
    difference: float | None = None

    @property
    def verdict(self) -> str:
        usable = [c for c in self.cohorts if c.n >= MIN_SAMPLE_FOR_INFERENCE]
        if len(usable) < 2 or self.p_value is None:
            return "INSUFFICIENT DATA"
        if self.p_value > 0.05:
            return "NO SIGNIFICANT DIFFERENCE"
        if (self.difference or 0) > 0:
            return "MULTI-SOURCE OUTPERFORMS"
        return "MULTI-SOURCE UNDERPERFORMS"


def _ranks(values: list[float]) -> list[float]:
    """Ranks with ties averaged, as Spearman requires."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(x) != len(y):
        return None
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = (
        sum((a - mx) ** 2 for a in x) ** 0.5 * sum((b - my) ** 2 for b in y) ** 0.5
    )
    return None if den == 0 else num / den


def spearman(x: list[float], y: list[float]) -> float | None:
    """Rank correlation — measures whether the relationship is monotonic
    without assuming it's linear. A score model only has to rank
    opportunities correctly; it doesn't have to be linear in return."""
    if len(x) < 2 or len(x) != len(y):
        return None
    return pearson(_ranks(x), _ranks(y))


def permutation_p_value(
    x: list[float],
    y: list[float],
    observed: float,
    iterations: int = PERMUTATIONS,
    seed: int = _SEED,
) -> float | None:
    """Two-sided probability of a rank correlation at least this extreme
    arising by chance, by repeatedly reshuffling one side."""
    if len(x) < 2 or observed is None:
        return None
    rng = random.Random(seed)
    shuffled = list(y)
    extreme = 0
    for _ in range(iterations):
        rng.shuffle(shuffled)
        rho = spearman(x, shuffled)
        if rho is not None and abs(rho) >= abs(observed):
            extreme += 1
    # +1 in numerator and denominator: with finite permutations a p-value
    # of exactly 0 is not a claim the data can support.
    return (extreme + 1) / (iterations + 1)


def permutation_difference_p_value(
    group_a: list[float],
    group_b: list[float],
    iterations: int = PERMUTATIONS,
    seed: int = _SEED,
) -> float | None:
    """Probability that the gap between two groups' means is chance."""
    if len(group_a) < 2 or len(group_b) < 2:
        return None
    observed = statistics.mean(group_a) - statistics.mean(group_b)
    pooled = group_a + group_b
    split = len(group_a)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(iterations):
        rng.shuffle(pooled)
        diff = statistics.mean(pooled[:split]) - statistics.mean(pooled[split:])
        if abs(diff) >= abs(observed):
            extreme += 1
    return (extreme + 1) / (iterations + 1)


def score_return_correlation(
    db: Session,
    horizon_days: int = 20,
    recommendation: str | None = None,
    benchmark: str | None = None,
) -> CorrelationResult:
    """Task 4: is score related to what happened next?

    Uses every ranking with a measurable forward window, not just BUYs by
    default — restricting to BUYs would only measure the top of the range
    and can't show whether the score discriminates across it.
    """
    query = db.query(RankedOpportunity)
    if recommendation:
        query = query.filter(RankedOpportunity.recommendation == recommendation)

    scores: list[float] = []
    returns: list[float] = []
    for opportunity in query.all():
        if opportunity.rank_timestamp is None:
            continue
        realized = _measure(
            db, opportunity.ticker, opportunity.rank_timestamp.date(), horizon_days, benchmark
        )
        if realized is None:
            continue
        # A SELL is graded on the downside it predicted, so its realized
        # return is negated to put every call on a "did it work" axis.
        if opportunity.recommendation == "SELL":
            realized = -realized
        scores.append(opportunity.score)
        returns.append(realized)

    rho = spearman(scores, returns)
    return CorrelationResult(
        n=len(scores),
        spearman=rho,
        pearson=pearson(scores, returns),
        p_value=permutation_p_value(scores, returns, rho) if rho is not None else None,
        horizon_days=horizon_days,
    )


def multi_vs_single_source(
    db: Session, horizon_days: int = 20, benchmark: str | None = None
) -> CohortComparison:
    """Task 5: does corroboration across sources actually help?

    This is the empirical test of the project's founding assumption —
    that agreement between independent sources is worth more than one
    loud source. It has never been checked.
    """
    single: list[float] = []
    multi: list[float] = []

    for opportunity in db.query(RankedOpportunity).all():
        if opportunity.rank_timestamp is None:
            continue
        realized = _measure(
            db, opportunity.ticker, opportunity.rank_timestamp.date(), horizon_days, benchmark
        )
        if realized is None:
            continue
        if opportunity.recommendation == "SELL":
            realized = -realized
        source_count = len(opportunity.sources or [])
        (multi if source_count >= 2 else single).append(realized)

    def _cohort(label: str, values: list[float]) -> CohortResult:
        if not values:
            return CohortResult(label, 0, None, None)
        return CohortResult(
            label=label,
            n=len(values),
            mean_return=statistics.mean(values),
            win_rate=sum(1 for v in values if v > 0) / len(values),
        )

    comparison = CohortComparison(
        horizon_days=horizon_days,
        cohorts=[_cohort("single-source", single), _cohort("multi-source", multi)],
    )
    if single and multi:
        comparison.difference = statistics.mean(multi) - statistics.mean(single)
        comparison.p_value = permutation_difference_p_value(multi, single)
    return comparison


@dataclass
class WeightRecommendation:
    verdict: str  # INCREASE | DECREASE | UNCHANGED | INVESTIGATE
    reasons: list[str] = field(default_factory=list)
    per_source: dict[str, str] = field(default_factory=dict)
    safe_to_act: bool = False


def weight_recommendation(
    correlation: CorrelationResult,
    cohorts: CohortComparison,
    source_stats: list,
) -> WeightRecommendation:
    """Task 6: should the hand-tuned weights move?

    The default answer is UNCHANGED, and the bar for anything else is
    deliberately high. Tuning weights against a sample too small to
    distinguish skill from noise is how a backtest becomes a machine for
    manufacturing false confidence — the resulting model looks better
    precisely because it has been fitted to randomness.
    """
    recommendation = WeightRecommendation(verdict="UNCHANGED")

    if correlation.n < MIN_SAMPLE_FOR_INFERENCE:
        recommendation.reasons.append(
            f"Only {correlation.n} scored opportunities have a measurable "
            f"{correlation.horizon_days}-day forward window "
            f"(need {MIN_SAMPLE_FOR_INFERENCE} to attempt inference). "
            "No weight change is defensible on this sample."
        )
        return recommendation

    if correlation.p_value is not None and correlation.p_value > 0.05:
        recommendation.reasons.append(
            f"Score and forward return show no significant relationship "
            f"(Spearman {correlation.spearman:+.3f}, p={correlation.p_value:.3f}). "
            "The model has not demonstrated predictive power, so there is no "
            "evidence-based direction in which to move the weights."
        )
        return recommendation

    if correlation.is_negligible:
        recommendation.reasons.append(
            f"Score and forward return are correlated at Spearman "
            f"{correlation.spearman:+.3f} (p={correlation.p_value:.3f}, "
            f"n={correlation.n}) — statistically detectable, but explaining "
            f"{correlation.variance_explained:.2%} of return variation. A "
            f"sample this large makes tiny effects significant; significance "
            f"is not size. Below |rho|={MIN_ACTIONABLE_CORRELATION}, and with no "
            "transaction-cost or turnover model in this project, there is "
            "nothing here worth retuning weights against."
        )
        return recommendation

    if correlation.spearman is not None and correlation.spearman < 0:
        recommendation.verdict = "INVESTIGATE"
        recommendation.reasons.append(
            f"Score correlates NEGATIVELY with forward return "
            f"(Spearman {correlation.spearman:+.3f}, p={correlation.p_value:.3f}). "
            "Higher-scoring opportunities did worse. Before touching weights, "
            "check for an inverted direction convention or a look-ahead error "
            "in how entry dates are chosen."
        )
        return recommendation

    recommendation.reasons.append(
        f"Score correlates positively with forward return "
        f"(Spearman {correlation.spearman:+.3f}, p={correlation.p_value:.3f}, "
        f"n={correlation.n}). The ranking has directional validity."
    )
    recommendation.safe_to_act = not correlation.is_provisional

    if cohorts.verdict == "MULTI-SOURCE OUTPERFORMS":
        recommendation.reasons.append(
            f"Multi-source opportunities beat single-source by "
            f"{(cohorts.difference or 0) * 100:+.2f}% (p={cohorts.p_value:.3f}), "
            "supporting an increase to the agreement bonus."
        )
        recommendation.verdict = "INCREASE"
    elif cohorts.verdict == "MULTI-SOURCE UNDERPERFORMS":
        recommendation.reasons.append(
            f"Multi-source opportunities UNDERPERFORMED single-source by "
            f"{(cohorts.difference or 0) * 100:+.2f}% (p={cohorts.p_value:.3f}). "
            "The agreement bonus is not earning its place and should be reduced."
        )
        recommendation.verdict = "DECREASE"
    else:
        recommendation.reasons.append(
            "Multi-source vs single-source shows no significant difference, so "
            "the agreement bonus is neither confirmed nor refuted."
        )

    for result in source_stats:
        stats = next(iter(result.horizons.values()), None)
        if stats is None or not stats.is_meaningful:
            recommendation.per_source[result.label] = (
                f"insufficient data (n={stats.sample_size if stats else 0})"
            )
        elif stats.avg_return is not None and stats.avg_return > 0:
            recommendation.per_source[result.label] = (
                f"positive (avg {stats.avg_return * 100:+.2f}%, n={stats.sample_size})"
            )
        else:
            recommendation.per_source[result.label] = (
                f"negative (avg {(stats.avg_return or 0) * 100:+.2f}%, "
                f"n={stats.sample_size}) — candidate for reduction"
            )

    if correlation.is_provisional:
        recommendation.reasons.append(
            f"PROVISIONAL: n={correlation.n} is below {MIN_SAMPLE_FOR_CONFIDENCE}. "
            "Treat the direction as a hypothesis, not a mandate to retune."
        )

    return recommendation


def source_sample_sizes(db: Session, horizon_days: int = 20) -> dict[str, int]:
    """How many measurable observations each source actually has — the
    first thing to check before reading any per-source performance."""
    counts: dict[str, int] = {}
    for signal in db.query(SignalRow).all():
        if (signal.evidence or {}).get("direction") not in ("buy", "sell"):
            continue
        if forward_return(db, signal.ticker, signal.event_date, horizon_days) is None:
            continue
        counts[signal.source] = counts.get(signal.source, 0) + 1
    return counts
