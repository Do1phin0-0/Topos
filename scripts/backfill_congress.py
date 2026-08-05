"""Backfills historical congressional trades to accelerate validation.

Live accumulation is slow: the score-bucket table needs enough closed
forward windows to say anything, and the pipeline only sees new
disclosures as they appear. The House Clerk publishes a yearly archive of
every Periodic Transaction Report, so years of history can be ingested at
once — which is what makes validating the scoring model possible now
rather than next quarter.

    python scripts/backfill_congress.py --since 2024-01-01
    python scripts/backfill_congress.py --since 2024-01-01 --max-filings 50
    python scripts/backfill_congress.py --since 2024-01-01 --skip-prices

The first run downloads a few thousand PDFs; they are cached, so later
runs re-parse from disk for free. Start with --max-filings to see the
parse rate on a sample before committing to a full year, and --skip-prices
to see the ticker count you would be signing up for.
"""

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.prices import backfill_ticker
from topos.collectors.house_clerk import HouseClerkCollector, HouseClerkUnavailable
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
        "--max-filings",
        type=int,
        default=0,
        help="Cap on PTR filings to fetch per year (0 = all). Use for a trial run.",
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
        help="Seconds between requests, to stay a polite client.",
    )
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d").date()
    years = list(range(since.year, date.today().year + 1))

    init_db()

    collector = HouseClerkCollector(delay=args.delay)
    records = []
    print(f"Fetching House Clerk disclosure archives for {years}...")
    for year in years:
        try:
            result = collector.transactions(
                year, limit=args.max_filings or None
            )
        except HouseClerkUnavailable as error:
            # A year the Clerk has not published yet is expected, not fatal.
            print(f"  {year}: unavailable ({error})")
            continue

        print(f"  {result.summary()}")
        if result.parse_rate is not None and result.parse_rate < 0.5:
            print(
                f"  [warn] {year}: under half of fetched filings yielded transactions. "
                "That is either a lot of scanned paper filings or a parser problem — "
                "inspect a few before trusting the numbers."
            )
        records.extend(result.transactions)

    print(f"\n  {len(records)} transactions parsed across {len(years)} year(s).")

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

        prices = PriceCollector()
        total_bars = 0
        for index, ticker in enumerate(targets, start=1):
            try:
                total_bars += backfill_ticker(session, ticker, collector=prices)
            except Exception as exc:
                print(f"  [warn] {ticker}: {exc}")
            if index % 25 == 0:
                print(f"  ...{index}/{len(targets)} tickers, {total_bars} bars stored")
            time.sleep(args.delay)

        print(f"\nDone. {total_bars} price bars stored across {len(targets)} tickers.")
        print("Now run: python scripts/research_report.py --output report.md")
    finally:
        session.close()


if __name__ == "__main__":
    from _cli import run

    run(main)
