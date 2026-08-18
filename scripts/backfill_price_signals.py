"""Backfills price-action signals from stored daily bars — the third source.

Unlike the congressional and Form 4 backfills, this makes no network call:
every input already lives in `price_bars`. It replays each ticker's stored
history through the point-in-time feature walk in
`topos/signals/price_action.py` and persists whatever fires.

    python scripts/backfill_price_signals.py
    python scripts/backfill_price_signals.py --tickers AAPL,MSFT

By default it runs every ticker with at least `--min-bars` stored bars —
80 by default, enough to fill the 60-day momentum window plus a day of
warm-up. Re-running is free and idempotent: `dedup_key` is deterministic
from ticker, source and event date, so a re-run against unchanged history
inserts nothing new.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.prices import get_bars
from topos.collectors.prices import Bar
from topos.db.models import PriceBar
from topos.db.session import SessionLocal, init_db
from topos.pipeline import persist_signals
from topos.signals.price_action import generate_price_action_signals


def _to_bar(row: PriceBar) -> Bar:
    return Bar(
        date=row.date,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill price-action signals from stored price history."
    )
    parser.add_argument(
        "--tickers",
        help="Comma-separated tickers to target (default: every ticker with enough stored history).",
    )
    parser.add_argument(
        "--min-bars",
        type=int,
        default=80,
        help=(
            "Skip tickers with fewer stored bars than this (default 80 — "
            "covers the 60-day momentum window plus warm-up)."
        ),
    )
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        if args.tickers:
            tickers = sorted(
                {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
            )
        else:
            rows = session.query(PriceBar.ticker).distinct().all()
            tickers = sorted({row[0] for row in rows})

        if not tickers:
            print(
                "No tickers with stored price history. Run a price backfill "
                "first — this source needs bars already sitting in price_bars."
            )
            return

        print(f"{len(tickers)} candidate tickers.")

        all_signals = []
        skipped = 0
        for ticker in tickers:
            bars = [_to_bar(row) for row in get_bars(session, ticker)]
            if len(bars) < args.min_bars:
                skipped += 1
                continue
            all_signals.extend(generate_price_action_signals(ticker, bars))

        print(f"{skipped} tickers skipped (fewer than {args.min_bars} stored bars).")
        print(f"{len(all_signals)} price-action signals generated.")

        if not all_signals:
            print("Nothing to ingest.")
            return

        by_source = Counter(signal.source for signal in all_signals)
        for source, count in sorted(by_source.items()):
            print(f"  {source}: {count}")

        inserted = persist_signals(session, all_signals)
        print(f"\nPersisted {inserted} new ({len(all_signals) - inserted} already known).")
    finally:
        session.close()

    print("\nNext, so the new source reaches the report:")
    print("  python scripts/replay_rankings.py --since 2024-01-01")
    print("  python scripts/research_report.py --output report.md")


if __name__ == "__main__":
    from _cli import run

    run(main)
