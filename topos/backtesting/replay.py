"""Replays the ranking engine over stored signal history.

The score-based validation sections read `RankedOpportunity` rows, and
in live operation those only accumulate as the pipeline runs — a fresh
database has none, and waiting for them means waiting a month per
20-day forward window. But the inputs to a ranking are just signals,
and years of those are already stored. So: walk backward through time,
and at each snapshot date rank exactly the signals that existed and
were fresh then, stamped with that date.

This is honest point-in-time work only because two properties hold:

* `event_date` is the real event date on every signal (the bug hunt
  that established this is documented in docs/DATA_LINEAGE.md), so
  "signals that existed by date D" is a query, not a guess.
* `build_breakdown(as_of=D)` measures staleness against D, so a filing
  three weeks old *at the snapshot* is penalised as three weeks old,
  not as however old it is today.

One caveat carries over from the lineage doc rather than being created
here: congressional signals are dated by transaction, which can precede
public disclosure by up to 45 days. Forward windows measured from those
dates measure informational value, not returns a live trader could have
captured. The report's per-source section carries the same caveat.

Idempotency: replayed rankings for a snapshot date get one fixed
timestamp, and each run deletes exactly that timestamp's rows before
writing. Re-running a window replaces it; it never doubles it. Live
pipeline rankings (stamped at wall-clock times) are untouched.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from topos.db.models import RankedOpportunity
from topos.db.models import Signal as SignalRow
from topos.ranking.attribution import STALENESS_HORIZON_DAYS
from topos.ranking.ranker import RankingEngine
from topos.signals.base import Signal

# Every ~4 trading weeks. Denser snapshots re-rank mostly the same
# signals into overlapping windows, which inflates n without adding
# independent observations — the statistics would look stronger while
# actually double-counting the same disclosures.
DEFAULT_STEP_DAYS = 28

_SNAPSHOT_TIME = time(20, 0)


@dataclass
class ReplayResult:
    snapshots: int = 0
    rankings_written: int = 0
    rankings_replaced: int = 0
    per_snapshot: list[tuple[date, int]] = field(default_factory=list)


def snapshot_dates(since: date, until: date, step_days: int) -> list[date]:
    """Snapshot dates from `since` forward, none later than `until`."""
    dates = []
    current = since
    while current <= until:
        dates.append(current)
        current += timedelta(days=step_days)
    return dates


def _to_signal(row: SignalRow) -> Signal:
    return Signal(
        timestamp=row.timestamp,
        event_date=row.event_date,
        dedup_key=row.dedup_key,
        source=row.source,
        ticker=row.ticker,
        confidence=row.confidence,
        evidence=row.evidence or {},
    )


def replay_rankings(
    db: Session,
    *,
    since: date,
    until: date | None = None,
    step_days: int = DEFAULT_STEP_DAYS,
) -> ReplayResult:
    """Writes point-in-time rankings for each snapshot date in the range.

    `until` defaults to the last date whose 60-trading-day forward window
    could plausibly have closed — there is no value in ranking yesterday,
    where every forward return is still None.
    """
    if until is None:
        until = date.today()

    engine = RankingEngine()
    result = ReplayResult()

    for snapshot in snapshot_dates(since, until, step_days):
        fresh_after = snapshot - timedelta(days=STALENESS_HORIZON_DAYS)
        rows = (
            db.query(SignalRow)
            .filter(SignalRow.event_date <= snapshot)
            .filter(SignalRow.event_date > fresh_after)
            .all()
        )
        if not rows:
            continue

        stamp = datetime.combine(snapshot, _SNAPSHOT_TIME)
        deleted = db.execute(
            delete(RankedOpportunity).where(RankedOpportunity.rank_timestamp == stamp)
        ).rowcount
        result.rankings_replaced += deleted or 0

        rankings = engine.rank([_to_signal(row) for row in rows], as_of=snapshot)
        for ranking in rankings:
            # The engine stamps tz-aware; the column stores naive. Make
            # the stored value byte-identical to the delete filter above,
            # or idempotency quietly breaks on the timezone marker.
            ranking.rank_timestamp = stamp
            db.add(ranking)

        db.commit()
        result.snapshots += 1
        result.rankings_written += len(rankings)
        result.per_snapshot.append((snapshot, len(rankings)))

    return result
