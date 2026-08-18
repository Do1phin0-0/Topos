"""Builds the historical ranking sample the score validation reads.

A fresh database has signals but no rankings — those normally accumulate
one pipeline run at a time. This replays the ranking engine over stored
signal history, producing point-in-time snapshots the backtester can
measure forward returns against immediately.

    python scripts/replay_rankings.py --since 2024-01-01
    python scripts/replay_rankings.py --since 2024-01-01 --every 14

Run it after the signal backfill and before the research report.
Re-running is safe: each snapshot replaces its own previous rows.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.replay import DEFAULT_STEP_DAYS, replay_rankings
from topos.db.session import SessionLocal, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay rankings over signal history.")
    parser.add_argument(
        "--since",
        default="2024-01-01",
        help="First snapshot date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--every",
        type=int,
        default=DEFAULT_STEP_DAYS,
        help=(
            f"Days between snapshots (default {DEFAULT_STEP_DAYS}). Denser "
            "snapshots re-rank the same signals into overlapping windows — "
            "more rows, not more independent evidence."
        ),
    )
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d").date()

    init_db()
    session = SessionLocal()
    try:
        print(f"Replaying rankings every {args.every} days from {since}...")
        result = replay_rankings(session, since=since, step_days=args.every)
    finally:
        session.close()

    for snapshot, count in result.per_snapshot:
        print(f"  {snapshot}: {count} tickers ranked")

    replaced = f" (replaced {result.rankings_replaced} from a previous run)" if result.rankings_replaced else ""
    print(
        f"\n{result.rankings_written} rankings across {result.snapshots} "
        f"snapshots{replaced}."
    )
    print("Now run: python scripts/research_report.py --output report.md")


if __name__ == "__main__":
    from _cli import run

    run(main)
