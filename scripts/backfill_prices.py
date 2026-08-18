"""Backfills daily price history for specific tickers.

Mostly for the benchmark. Every other backfill pulls prices for the
tickers its signals mention, which never includes SPY — so without this
the benchmark comparison has nothing to compare against.

    python scripts/backfill_prices.py SPY
    python scripts/backfill_prices.py SPY QQQ IWM
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.prices import BENCHMARK_TICKER, backfill_ticker
from topos.collectors.prices import PriceCollector
from topos.db.session import SessionLocal, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill price history for tickers.")
    parser.add_argument(
        "tickers",
        nargs="*",
        default=[BENCHMARK_TICKER],
        help=f"Tickers to fetch (default: {BENCHMARK_TICKER}).",
    )
    parser.add_argument("--delay", type=float, default=0.4, help="Seconds between requests.")
    args = parser.parse_args()

    tickers = [t.upper() for t in (args.tickers or [BENCHMARK_TICKER])]

    init_db()
    session = SessionLocal()
    try:
        collector = PriceCollector()
        for ticker in tickers:
            try:
                bars = backfill_ticker(session, ticker, collector=collector)
                print(f"{ticker}: {bars} new bars stored")
            except Exception as error:
                print(f"{ticker}: failed — {error}")
            time.sleep(args.delay)
    finally:
        session.close()


if __name__ == "__main__":
    from _cli import run

    run(main)
