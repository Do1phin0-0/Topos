"""Generates the signal-validation research report.

Answers, in order: do individual sources predict returns, do higher score
buckets earn more, is score correlated with forward return, does
multi-source agreement beat single-source, and should the weights change.

    python scripts/research_report.py
    python scripts/research_report.py --horizon 5 --output report.md

Every section reports its sample size first. A finding on 8 observations
is not a finding, and the report says so rather than printing a
confident-looking number.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.backtesting.evaluate import evaluate_score_buckets, evaluate_signals
from topos.backtesting.research import (
    MIN_SAMPLE_FOR_CONFIDENCE,
    MIN_SAMPLE_FOR_INFERENCE,
    multi_vs_single_source,
    score_return_correlation,
    weight_recommendation,
)
from topos.db.models import PriceBar, RankedOpportunity
from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _num(value: float | None, places: int = 3) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _table(rows: list[list[str]], headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_report(session, horizon: int) -> str:
    out: list[str] = []
    w = out.append

    signal_count = session.query(SignalRow).count()
    ranked_count = session.query(RankedOpportunity).count()
    price_tickers = session.query(PriceBar.ticker).distinct().count()

    w("# Signal validation research report")
    w("")
    w(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · "
      f"holding period {horizon} trading days")
    w("")
    w("## 0. Data inventory")
    w("")
    w(_table(
        [
            ["signals stored", str(signal_count)],
            ["ranked opportunities", str(ranked_count)],
            ["tickers with price history", str(price_tickers)],
        ],
        ["item", "count"],
    ))
    w("")

    if signal_count == 0 or ranked_count == 0 or price_tickers == 0:
        w("> **No data to analyse.** Run the pipeline and the congressional")
        w("> backfill first; forward returns cannot be measured without both")
        w("> ranked opportunities and price history covering their windows.")
        w("")
        return "\n".join(out)

    # --- Task 2 ---
    w("## 1. Performance by signal source")
    w("")
    source_stats = evaluate_signals(session, horizons=(horizon,), group_by="source")
    if not source_stats:
        w("No source has a measurable forward window yet.")
    else:
        rows = []
        for result in source_stats:
            stats = result.horizons[horizon]
            rows.append([
                result.label,
                str(stats.sample_size),
                "—" if stats.win_rate is None else f"{stats.win_rate:.0%}",
                _pct(stats.avg_return),
                _num(stats.sharpe, 2),
                "yes" if stats.is_meaningful else "**thin**",
            ])
        w(_table(rows, ["source", "n", "win rate", "avg return", "sharpe", "usable?"]))
    w("")
    w("Returns are direction-adjusted: a correct SELL counts as a gain. "
      "Sources with no directional claim (8-K earnings) are excluded — there "
      "is nothing to be right or wrong about.")
    w("")

    # --- Task 3 ---
    w("## 2. Performance by score bucket")
    w("")
    buckets = evaluate_score_buckets(session, horizons=(horizon,), recommendation=None)
    if not buckets:
        w("No scored opportunity has a closed forward window yet.")
    else:
        rows = []
        for bucket in buckets:
            stats = bucket.horizons[horizon]
            rows.append([
                bucket.label,
                str(stats.sample_size),
                "—" if stats.win_rate is None else f"{stats.win_rate:.0%}",
                _pct(stats.avg_return),
                _num(stats.sharpe, 2),
                "yes" if stats.is_meaningful else "**thin**",
            ])
        w(_table(rows, ["score", "n", "win rate", "avg return", "sharpe", "usable?"]))
        w("")
        w("A working score shows a rising avg return down this table. "
          "A flat or non-monotonic column means the score is not "
          "discriminating, whatever its individual values look like.")
    w("")

    # --- Task 4 ---
    w("## 3. Correlation between score and forward return")
    w("")
    correlation = score_return_correlation(session, horizon_days=horizon)
    w(_table(
        [
            ["observations", str(correlation.n)],
            ["Spearman (rank)", _num(correlation.spearman)],
            ["Pearson (linear)", _num(correlation.pearson)],
            ["p-value (permutation)", _num(correlation.p_value)],
            ["verdict", f"**{correlation.verdict}**"],
        ],
        ["metric", "value"],
    ))
    w("")
    w("Spearman is the headline: a score model only has to *rank* "
      "opportunities correctly, not be linear in return. The p-value comes "
      "from a permutation test — no normality assumed, which matters "
      "because returns are not normal and this sample is small.")
    w("")

    # --- Task 5 ---
    w("## 4. Multi-source agreement vs single-source")
    w("")
    cohorts = multi_vs_single_source(session, horizon_days=horizon)
    rows = [
        [c.label, str(c.n), "—" if c.win_rate is None else f"{c.win_rate:.0%}", _pct(c.mean_return)]
        for c in cohorts.cohorts
    ]
    w(_table(rows, ["cohort", "n", "win rate", "avg return"]))
    w("")
    w(_table(
        [
            ["difference (multi - single)", _pct(cohorts.difference)],
            ["p-value (permutation)", _num(cohorts.p_value)],
            ["verdict", f"**{cohorts.verdict}**"],
        ],
        ["metric", "value"],
    ))
    w("")
    w("This is the empirical test of the project's founding assumption — "
      "that corroboration across independent sources beats one loud source. "
      "It has never been checked against outcomes before.")
    w("")

    # --- Task 6 ---
    w("## 5. Recommendation on weights")
    w("")
    recommendation = weight_recommendation(correlation, cohorts, source_stats)
    w(f"### Verdict: **{recommendation.verdict}**")
    w("")
    w(f"Safe to act on: **{'yes' if recommendation.safe_to_act else 'no'}**")
    w("")
    for reason in recommendation.reasons:
        w(f"- {reason}")
    w("")
    if recommendation.per_source:
        w("Per-source assessment:")
        w("")
        w(_table(
            [[source, note] for source, note in sorted(recommendation.per_source.items())],
            ["source", "assessment"],
        ))
        w("")

    w("---")
    w("")
    w(f"Thresholds: inference is not attempted below n={MIN_SAMPLE_FOR_INFERENCE}; "
      f"findings below n={MIN_SAMPLE_FOR_CONFIDENCE} are flagged provisional. "
      "These exist because tuning weights against noise produces a model that "
      "looks better precisely because it has been fitted to randomness.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the validation research report.")
    parser.add_argument("--horizon", type=int, default=20, help="Holding period in trading days.")
    parser.add_argument("--output", help="Write to a file instead of stdout.")
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        report = build_report(session, args.horizon)
    finally:
        session.close()

    if args.output:
        Path(args.output).write_text(report)
        print(f"Wrote {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
