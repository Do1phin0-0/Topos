"""Backfills historical congressional trades to accelerate validation.

Live accumulation is slow: the score-bucket table needs enough closed
forward windows to say anything, and the pipeline only sees new
disclosures. But the House/Senate Stock Watcher endpoints return their
entire archive on every request — the pipeline was already downloading
years of history and discarding all but the most recent rows.

This ingests that history and backfills the price bars needed to measure
forward returns against it. Congressional trades are the cheapest source
to backfill by a wide margin; see docs/DATA_LINEAGE.md for the others.

    python scripts/backfill_congress.py --since 2024-01-01
    python scripts/backfill_congress.py --since 2024-01-01 --max-tickers 100
    python scripts/backfill_congress.py --since 2024-01-01 --skip-prices

Price backfill is the slow part — one Stooq request per ticker, rate
limited. Run with --skip-prices first to see the ticker count you'd be
committing to.
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.prices import backfill_ticker
from topos.collectors.congress import CongressTradeCollector
from topos.collectors.prices import PriceCollector
from topos.db.session import SessionLocal, init_db
from topos.pipeline import persist_signals
from topos.signals.congress import extract_congress_signal


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill congressional trade history.")
    parser.add_argument(
        "--since",
        default="2024-01-01",
        help="Only ingest transactions on or after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=250,
        help="Cap on tickers to fetch price history for (0 = no cap).",
    )
    parser.add_argument(
        "--skip-prices",
        action="store_true",
        help="Ingest signals only; report the tickers that would need prices.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Seconds between price requests, to stay a polite client.",
    )
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d").date()

    init_db()
    print(f"Fetching the full congressional archive (filtering to >= {since})...")
    records = CongressTradeCollector().all_transactions()
    print(f"  {len(records)} total disclosures available upstream.")

    signals = []
    for record in records:
        signal = extract_congress_signal(record)
        # Undateable and non-directional records are dropped by the
        # extractor itself; only the date window is applied here.
        if signal and signal.event_date >= since:
            signals.append(signal)

    print(f"  {len(signals)} usable signals in the window.")
    if not signals:
        print("Nothing to ingest.")
        return

    session = SessionLocal()
    try:
        inserted = persist_signals(session, signals)
        print(f"  Persisted {inserted} new ({len(signals) - inserted} already known).")

        tickers = sorted({s.ticker for s in signals})
        print(f"\n{len(tickers)} distinct tickers referenced.")

        if args.skip_prices:
            print("Skipping price backfill (--skip-prices).")
            print("Forward returns can't be measured until these have price history.")
            return

        targets = tickers if args.max_tickers == 0 else tickers[: args.max_tickers]
        if len(targets) < len(tickers):
            print(f"Backfilling prices for the first {len(targets)} (--max-tickers).")
        else:
            print(f"Backfilling prices for all {len(targets)}.")

        collector = PriceCollector()
        total_bars = 0
        for index, ticker in enumerate(targets, start=1):
            try:
                bars = backfill_ticker(session, ticker, collector=collector)
                total_bars += bars
            except Exception as exc:
                print(f"  [warn] {ticker}: {exc}")
            if index % 25 == 0:
                print(f"  ...{index}/{len(targets)} tickers, {total_bars} bars stored")
            time.sleep(args.delay)

        print(f"\nDone. {total_bars} price bars stored across {len(targets)} tickers.")
        print("Now run: python scripts/run_backtest.py")
    finally:
        session.close()


if __name__ == "__main__":
    main()
