"""Is the multi-vs-single-source cohort comparison measuring what it claims?

research_report.py's section 4 found single-source opportunities averaging
+19.20% and multi-source averaging -0.30%, a p=0.000 gap, on n=249 vs
n=40,070. That lopsidedness is the same fingerprint as the earlier
"multi-source underperforms" finding in docs/VALIDATION_RESULTS.md, which
turned out to be an artifact of a biased small cohort rather than a real
effect of corroboration. This checks whether history is repeating before
anyone treats the new number as real.

    python scripts/diagnose_single_source_cohort.py

Nothing is written to the database.
"""

import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.evaluate import _measure
from topos.backtesting.prices import BENCHMARK_TICKER
from topos.db.models import RankedOpportunity
from topos.db.session import SessionLocal, init_db

HORIZON_DAYS = 20


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        rows = session.query(RankedOpportunity).all()
    finally:
        session.close()

    single = []  # (ticker, rank_date, only_source, recommendation, realized_return)
    for opportunity in rows:
        if opportunity.rank_timestamp is None:
            continue
        sources = opportunity.sources or []
        if len(sources) != 1:
            continue
        realized = _measure(
            session,
            opportunity.ticker,
            opportunity.rank_timestamp.date(),
            HORIZON_DAYS,
            BENCHMARK_TICKER,
        )
        if realized is None:
            continue
        if opportunity.recommendation == "SELL":
            realized = -realized
        single.append(
            (opportunity.ticker, opportunity.rank_timestamp.date(), sources[0],
             opportunity.recommendation, realized)
        )

    print(f"{len(single)} single-source, measurable opportunities.\n")
    if not single:
        print("Nothing to diagnose.")
        return

    by_source = Counter(row[2] for row in single)
    print("Which source is the lone one:")
    for source, count in by_source.most_common():
        print(f"  {source}: {count} ({count / len(single):.0%})")

    by_rec = Counter(row[3] for row in single)
    print("\nRecommendation split:")
    for rec, count in by_rec.most_common():
        print(f"  {rec}: {count}")

    returns = [row[4] for row in single]
    print(f"\nReturn distribution (n={len(returns)}):")
    print(f"  mean:   {statistics.mean(returns):+.2%}")
    print(f"  median: {statistics.median(returns):+.2%}")
    print(f"  stdev:  {statistics.stdev(returns):.2%}" if len(returns) > 1 else "  stdev:  n/a")
    print(f"  min:    {min(returns):+.2%}")
    print(f"  max:    {max(returns):+.2%}")

    ranked = sorted(single, key=lambda row: abs(row[4]), reverse=True)
    print("\nTop 15 by absolute return (ticker, date, lone source, rec, return):")
    for ticker, rank_date, source, rec, realized in ranked[:15]:
        print(f"  {ticker:8s} {rank_date}  {source:20s} {rec:5s} {realized:+.2%}")

    top5_share = sum(abs(r[4]) for r in ranked[:5]) / sum(abs(r) for r in returns)
    print(
        f"\nThe 5 most extreme observations account for {top5_share:.0%} of total "
        "absolute return in this cohort. If that number is large, a handful of "
        "outliers are driving the mean, not a real property of single-source "
        "opportunities in general."
    )


if __name__ == "__main__":
    from _cli import run

    run(main)
