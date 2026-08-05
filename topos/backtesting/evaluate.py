"""Does a signal — or a score — actually predict anything?

Every confidence weight in `topos/signals/` was hand-tuned and has never
been checked against what the ticker did next. This measures that.

Two things worth stating plainly about the method:

*Returns are direction-adjusted.* A sell signal that correctly called a
-5% move is a win, not a loss. Following a signal means going long on
"buy" and short (or out) on "sell", so a sell signal's raw return is
negated to get the return the signal actually earned. Scoring raw price
change instead would grade every bearish call backwards.

*Unmeasurable signals are excluded, not zeroed.* A signal too recent to
have a full forward window yet has no result — counting it as 0% would
drag every average toward zero and make a strategy look flatter and safer
than it is.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from topos.backtesting.prices import forward_return
from topos.db.models import RankedOpportunity
from topos.db.models import Signal as SignalRow

DEFAULT_HORIZONS = (5, 20, 60)
_TRADING_DAYS_PER_YEAR = 252


@dataclass
class HorizonStats:
    """Outcome of one group of signals at one holding period."""

    horizon_days: int
    sample_size: int
    win_rate: float | None
    avg_return: float | None
    median_return: float | None
    sharpe: float | None

    @property
    def is_meaningful(self) -> bool:
        """Whether this group has enough observations to read as anything
        other than noise. Surfaced so the dashboard can label thin
        buckets instead of presenting a 2-sample win rate as a finding."""
        return self.sample_size >= 20


@dataclass
class GroupResult:
    """One bucket (a source, a direction, a score range) across horizons."""

    label: str
    horizons: dict[int, HorizonStats] = field(default_factory=dict)


def _sharpe(returns: list[float], horizon_days: int) -> float | None:
    """Annualized Sharpe for a fixed holding period, assuming a 0%
    risk-free rate and non-overlapping trades.

    Scaling by sqrt(252/horizon) puts a 5-day and a 60-day strategy on the
    same axis; without it, longer holds look better purely because each
    observation covers more time.
    """
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    if stdev == 0:
        return None
    periods_per_year = _TRADING_DAYS_PER_YEAR / horizon_days
    return (statistics.mean(returns) / stdev) * (periods_per_year**0.5)


def _summarize(returns: list[float], horizon_days: int) -> HorizonStats:
    if not returns:
        return HorizonStats(horizon_days, 0, None, None, None, None)
    wins = sum(1 for r in returns if r > 0)
    return HorizonStats(
        horizon_days=horizon_days,
        sample_size=len(returns),
        win_rate=wins / len(returns),
        avg_return=statistics.mean(returns),
        median_return=statistics.median(returns),
        sharpe=_sharpe(returns, horizon_days),
    )


def _direction_multiplier(direction: str | None) -> int | None:
    if direction == "buy":
        return 1
    if direction == "sell":
        return -1
    return None  # no directional claim to grade


def _collect(
    db: Session,
    rows: list[tuple[str, str, object]],
    horizons: tuple[int, ...],
) -> dict[str, dict[int, list[float]]]:
    """Maps (group label, ticker, entry date) rows to realized returns."""
    grouped: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for label, ticker, entry_date in rows:
        for horizon in horizons:
            raw = forward_return(db, ticker, entry_date, horizon)
            if raw is None:
                continue
            grouped[label][horizon].append(raw)
    return grouped


def evaluate_signals(
    db: Session,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    group_by: str = "source",
) -> list[GroupResult]:
    """Forward performance of raw signals, grouped by `source`,
    `direction`, or `confidence` bucket.

    Entry is each signal's `event_date` — when the thing actually
    happened — not when it was scraped.
    """
    signals = db.query(SignalRow).all()

    grouped: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for signal in signals:
        direction = (signal.evidence or {}).get("direction")
        multiplier = _direction_multiplier(direction)
        if multiplier is None:
            continue

        if group_by == "source":
            label = signal.source
        elif group_by == "direction":
            label = direction
        elif group_by == "confidence":
            low = int(signal.confidence * 10) * 10
            label = f"{low}-{low + 10}%"
        else:
            raise ValueError(f"unknown group_by: {group_by!r}")

        for horizon in horizons:
            raw = forward_return(db, signal.ticker, signal.event_date, horizon)
            if raw is None:
                continue
            grouped[label][horizon].append(raw * multiplier)

    return [
        GroupResult(
            label=label,
            horizons={h: _summarize(grouped[label].get(h, []), h) for h in horizons},
        )
        for label in sorted(grouped)
    ]


def evaluate_score_buckets(
    db: Session,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    bucket_width: int = 10,
    recommendation: str | None = "BUY",
) -> list[GroupResult]:
    """The headline question: does a higher combined score actually earn
    a higher return?

    Entry is each opportunity's rank timestamp — the moment the engine
    made the call — so this grades the recommendation as it was actually
    issued. Defaults to BUY recommendations because that's what the
    portfolio engine acts on; pass None to include every ranking.
    """
    query = db.query(RankedOpportunity)
    if recommendation:
        query = query.filter(RankedOpportunity.recommendation == recommendation)

    grouped: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for opportunity in query.all():
        if opportunity.rank_timestamp is None:
            continue
        low = int(opportunity.score // bucket_width) * bucket_width
        label = f"{low}-{low + bucket_width}"
        # A SELL call is graded on the downside it predicted.
        multiplier = -1 if opportunity.recommendation == "SELL" else 1

        for horizon in horizons:
            raw = forward_return(
                db, opportunity.ticker, opportunity.rank_timestamp.date(), horizon
            )
            if raw is None:
                continue
            grouped[label][horizon].append(raw * multiplier)

    return [
        GroupResult(
            label=label,
            horizons={h: _summarize(grouped[label].get(h, []), h) for h in horizons},
        )
        # Sort by the bucket's lower bound, so 100-110 doesn't sort before 20-30.
        for label in sorted(grouped, key=lambda s: int(s.split("-")[0]))
    ]
