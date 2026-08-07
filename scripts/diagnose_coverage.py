"""Why do most tickers have no price history?

The validation ran on 452 of 1,342 tickers. Two-thirds of the signal set
never entered the analysis, and the missing names are not a random
sample — they skew small, foreign and delisted, which is precisely where
the literature says insider signals are strongest. So the result may have
been measured on the part of the market where the effect is weakest.

Before fixing that, find out what is actually missing. Some of it is
unfixable (a company that no longer trades has no prices to fetch) and
some is a source that could not answer. Those need different responses,
and a count cannot tell them apart.

    python scripts/diagnose_coverage.py
    python scripts/diagnose_coverage.py --sample 40 --retry

Nothing is written to the database. --retry re-attempts the missing
tickers against the live price chain to see what still fails and how.
"""

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.collectors.prices import PriceCollector
from topos.db.models import PriceBar
from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db

# Suffixes and shapes that identify a ticker no US price source will
# have, so they can be separated from ones that simply failed.
_FIVE_LETTER_ADR = re.compile(r"^[A-Z]{4}[YF]$")  # e.g. ADDYY, AJINF
_CLASS_SUFFIX = re.compile(r"^[A-Z]{1,4}[.\-][A-Z]{1,2}$")  # BRK.B, RDS-A


def classify(ticker: str) -> str:
    """A first guess at why a ticker has no data, from its shape alone."""
    if _FIVE_LETTER_ADR.match(ticker):
        return "likely ADR / foreign ordinary (Y or F suffix)"
    if _CLASS_SUFFIX.match(ticker):
        return "share-class suffix (dot or dash)"
    if len(ticker) > 5:
        return "longer than a US listing (>5 characters)"
    if not ticker.isalpha():
        return "contains non-letters"
    return "ordinary-looking US ticker"


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose missing price coverage.")
    parser.add_argument(
        "--sample", type=int, default=25, help="How many missing tickers to retry."
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Actually re-fetch the sample and report what each source says.",
    )
    parser.add_argument("--delay", type=float, default=0.4)
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        signal_tickers = {t for (t,) in session.query(SignalRow.ticker).distinct()}
        priced = {t for (t,) in session.query(PriceBar.ticker).distinct()}
    finally:
        session.close()

    missing = sorted(signal_tickers - priced)
    covered = len(signal_tickers) - len(missing)

    print(f"{len(signal_tickers)} tickers carry signals.")
    print(f"{covered} have price history ({covered / len(signal_tickers):.0%}).")
    print(f"{len(missing)} do not.\n")

    if not missing:
        print("Full coverage. Nothing to diagnose.")
        return

    shapes = Counter(classify(t) for t in missing)
    width = max(len(s) for s in shapes)
    print("Missing tickers by shape:")
    for shape, count in shapes.most_common():
        share = count / len(missing)
        print(f"  {shape.ljust(width)}  {count:5d}  ({share:.0%})")

    print(
        "\nShape is a hint, not a verdict: an ordinary-looking ticker with no "
        "data is either delisted, or a source that should have answered didn't."
    )

    if not args.retry:
        print(f"\nRun with --retry to re-fetch {args.sample} of them and find out.")
        return

    # Retry the ordinary-looking ones first — they are the ones whose
    # absence would actually be a bug rather than a fact about the market.
    ordinary = [t for t in missing if classify(t) == "ordinary-looking US ticker"]
    targets = (ordinary or missing)[: args.sample]

    print(f"\nRe-fetching {len(targets)} ordinary-looking tickers...\n")
    collector = PriceCollector()
    outcomes = Counter()
    for ticker in targets:
        try:
            bars = collector.daily_bars(ticker)
        except Exception as error:
            outcome = f"error: {type(error).__name__}"
            print(f"  {ticker:8s} {outcome}")
        else:
            outcome = f"{len(bars)} bars" if bars else "no data from any source"
            print(f"  {ticker:8s} {outcome}")
        outcomes[outcome.split(":")[0]] += 1
        time.sleep(args.delay)

    print("\nOutcomes:")
    for outcome, count in outcomes.most_common():
        print(f"  {outcome}: {count}")

    recovered = sum(c for o, c in outcomes.items() if o.endswith("bars"))
    if recovered:
        print(
            f"\n{recovered} of {len(targets)} came back with data this time. "
            "That is recoverable coverage — the earlier run lost them to a "
            "source outage, not to the tickers being untradeable. Re-running "
            "the price backfill would widen the validation sample."
        )
    else:
        print(
            "\nNone came back with data. These tickers are genuinely absent "
            "from both free sources — delisted, foreign, or too small to be "
            "carried. Coverage cannot be widened without a paid data source, "
            "and the validation sample is what it is."
        )


if __name__ == "__main__":
    from _cli import run

    run(main)
