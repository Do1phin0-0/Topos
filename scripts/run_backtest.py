"""Answers the question the whole ranking engine rests on: does a higher
score actually earn a higher return?

    python scripts/run_backtest.py
    python scripts/run_backtest.py --group-by source --horizons 5,20
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.evaluate import (
    DEFAULT_HORIZONS,
    GroupResult,
    evaluate_score_buckets,
    evaluate_signals,
)
from topos.db.session import SessionLocal, init_db


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _fmt_ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _print_table(title: str, results: list[GroupResult], horizons: tuple[int, ...]) -> None:
    print(f"\n{title}")
    print("=" * len(title))
    if not results:
        print("  No measurable history yet.")
        return

    header = f"{'bucket':<14}{'horizon':>9}{'n':>7}{'win rate':>11}{'avg':>11}{'median':>11}{'sharpe':>9}"
    print(header)
    print("-" * len(header))
    for result in results:
        for horizon in horizons:
            stats = result.horizons[horizon]
            # A thin bucket is marked rather than silently presented as a
            # finding — a 2-sample win rate is noise, not evidence.
            flag = "" if stats.is_meaningful else "  (thin)"
            print(
                f"{result.label:<14}{horizon:>7}d{stats.sample_size:>7}"
                f"{'—' if stats.win_rate is None else f'{stats.win_rate:.0%}':>11}"
                f"{_fmt_pct(stats.avg_return):>11}"
                f"{_fmt_pct(stats.median_return):>11}"
                f"{_fmt_ratio(stats.sharpe):>9}{flag}"
            )
    print(
        "\n  Returns are direction-adjusted: a correct SELL call counts as a gain."
        "\n  Signals too recent to have a full forward window are excluded, not counted as 0%."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Topos signal performance.")
    parser.add_argument(
        "--horizons",
        default=",".join(str(h) for h in DEFAULT_HORIZONS),
        help="Comma-separated holding periods in trading days (default: 5,20,60).",
    )
    parser.add_argument(
        "--group-by",
        choices=["score", "source", "direction", "confidence"],
        default="score",
        help="How to bucket results (default: score).",
    )
    args = parser.parse_args()
    horizons = tuple(int(h) for h in args.horizons.split(","))

    init_db()
    session = SessionLocal()
    try:
        if args.group_by == "score":
            _print_table(
                "Score bucket vs. forward return (BUY recommendations)",
                evaluate_score_buckets(session, horizons=horizons),
                horizons,
            )
        else:
            _print_table(
                f"Signal performance by {args.group_by}",
                evaluate_signals(session, horizons=horizons, group_by=args.group_by),
                horizons,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
