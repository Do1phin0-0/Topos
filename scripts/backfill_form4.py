"""Backfills historical SEC Form 4 insider trades — the second source.

Validation's central finding was that it could not test the project's
founding assumption: with only congressional data loaded, no ticker ever
had two sources agreeing, so the multi-source cohort had n=0. This adds
insider filings over the same period so that comparison can finally run.

    python scripts/backfill_form4.py --since 2024-01-01
    python scripts/backfill_form4.py --since 2024-01-01 --max-filings 50

By default it fetches Form 4s only for tickers that already have price
history — the only ones whose forward returns are measurable, and
therefore the only ones that can contribute to the comparison. Roughly a
quarter-million Form 4s are filed each year; fetching them all would take
a day and answer nothing extra.

Downloads are cached, so re-runs are free. Run before replay_rankings.py:
rankings have to be rebuilt once new signals exist, or the new source
will be invisible to the report.
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.collectors.edgar_archive import EdgarArchiveCollector, EdgarUnavailable
from topos.db.models import PriceBar
from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db
from topos.pipeline import persist_signals


def quarters_between(since: date, until: date) -> list[tuple[int, int]]:
    """Every (year, quarter) touching the range, oldest first."""
    result = []
    year, quarter = since.year, (since.month - 1) // 3 + 1
    while (year, quarter) <= (until.year, (until.month - 1) // 3 + 1):
        result.append((year, quarter))
        quarter += 1
        if quarter > 4:
            year, quarter = year + 1, 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical Form 4 insider trades.")
    parser.add_argument("--since", default="2024-01-01", help="Earliest quarter to fetch (YYYY-MM-DD).")
    parser.add_argument(
        "--max-filings",
        type=int,
        default=0,
        help="Cap on filings fetched per quarter (0 = all). Use for a trial run.",
    )
    parser.add_argument(
        "--all-signal-tickers",
        action="store_true",
        help=(
            "Widen from tickers with price history to every ticker with any "
            "signal. More filings, but returns are unmeasurable without prices."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.12,
        help="Seconds between requests. SEC's limit is 10/sec; do not go below 0.1.",
    )
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d").date()

    init_db()
    session = SessionLocal()
    try:
        if args.all_signal_tickers:
            rows = session.query(SignalRow.ticker).distinct().all()
            basis = "have any signal"
        else:
            rows = session.query(PriceBar.ticker).distinct().all()
            basis = "have price history"
        tickers = sorted({row[0] for row in rows})
    finally:
        session.close()

    if not tickers:
        print(
            "No tickers to target. Run the congressional backfill first — this\n"
            "fetches insider filings for companies Topos already tracks, so it\n"
            "needs something to intersect with."
        )
        return

    print(f"{len(tickers)} tickers that {basis}.")

    collector = EdgarArchiveCollector(delay=args.delay)
    try:
        ciks = collector.ciks_for(tickers)
    except EdgarUnavailable as error:
        print(f"\n{error}\n")
        raise SystemExit(1)

    print(f"{len(ciks)} resolved to a CIK via SEC's ticker map.")
    unresolved = len(tickers) - len(ciks)
    if unresolved:
        # Foreign issuers, ADRs and delisted names have no CIK in the map
        # and file no Form 4 — expected, but worth seeing the size of.
        print(f"  ({unresolved} did not resolve — foreign issuers, ADRs, delisted names.)")

    all_signals = []
    for year, quarter in quarters_between(since, date.today()):
        try:
            result = collector.form4_signals(
                year, quarter, ciks=ciks, limit=args.max_filings or None
            )
        except EdgarUnavailable as error:
            print(f"  {year}Q{quarter}: unavailable ({error})")
            continue

        print(f"  {result.summary()}")
        all_signals.extend(result.signals)

    print(f"\n{len(all_signals)} Form 4 signals parsed.")
    in_window = [s for s in all_signals if s.event_date >= since]
    print(f"{len(in_window)} in the window (on or after {since}).")

    if not in_window:
        print("Nothing to ingest.")
        return

    session = SessionLocal()
    try:
        inserted = persist_signals(session, in_window)
        print(f"Persisted {inserted} new ({len(in_window) - inserted} already known).")
    finally:
        session.close()

    print("\nNext, so the new source reaches the report:")
    print("  python scripts/replay_rankings.py --since 2024-01-01")
    print("  python scripts/research_report.py --output report.md")


if __name__ == "__main__":
    from _cli import run

    run(main)
