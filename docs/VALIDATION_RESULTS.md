# Validation results — first run, 2026-08-06

The question was: **does the scoring model have predictive power?**

**Answer: not demonstrated.** Score and 20-day forward return show
Spearman −0.009 (p = 0.51) across 4,640 observations. That is not a
small-sample shrug — the sample is 46× the inference threshold and the
result is indistinguishable from zero. On this evidence the score does
not rank opportunities.

**But read the next section before drawing conclusions from that**, because
the thing tested was not the model the system is designed to run.

## What was actually under test

Only congressional disclosures were in the database. With a single
source present, the additive formula collapses algebraically:

| term | value with one source |
|---|---|
| base points | `avg_confidence × 100` — the source's confidence, nothing else |
| multi-source agreement bonus | **never applies** (requires ≥2 agreeing sources) |
| conflict penalty | only when the same chamber both bought and sold the ticker |
| staleness penalty | up to −15, scaling with signal age at the snapshot |

And congressional confidence is `0.25 + min(midpoint/250_000, 1.0) × 0.4`,
where `midpoint` is the disclosed dollar range. The typical disclosure is
the $1,001–$15,000 band → midpoint $8,000 → confidence ≈ **0.263**.

So the score under test reduced to roughly:

```
score ≈ 26 + (trade size, capped) − (staleness) − (conflict)
```

That is why 98% of 13,556 rankings scored under 30, and why buckets above
40 hold 25 rows between them. **The experiment measured "do larger, fresher
congressional trades outperform?" — not "does multi-source corroboration
outperform?"**

The founding assumption of the entire project — that agreement across
independent sources beats one loud source — has **n = 0 observations**.
Section 4 of the report reads INSUFFICIENT DATA, and that is the single
most important line in it.

## Findings that do stand

1. **Congressional trades alone show no edge at 20 trading days.**
   n = 3,433, win rate 50%, average direction-adjusted return −0.27%,
   Sharpe −0.09. A coin flip.
2. **Score buckets trend the wrong way in the populated range**
   (0–10: +1.34%, 10–20: +0.92%, 20–30: +0.59%, 30–40: −0.44%). Higher
   scores earned *less*. The correlation test does not confirm this as
   significant, so it is a thing to investigate, not a thing to act on —
   but it is the opposite of the intended direction and should not be
   waved away.
3. **The guardrails worked.** The report refused to recommend a weight
   change, flagged `safe_to_act: no`, and marked every thin bucket. It
   would have been easy to build something that fitted noise and
   announced a triumph.

## Caveats that could materially move these numbers

- **Only 451 of 1,342 tickers had price history.** Roughly two-thirds of
  the signal set was dropped for want of prices, after Stooq failed and
  the Yahoo fallback covered part of the gap. Whatever is systematically
  missing (foreign listings, OTC, small caps) is missing from the result.
- **Congressional signals are dated by transaction, not disclosure.**
  The STOCK Act allows up to 45 days between them. Forward windows from
  the transaction date measure informational value — what the member
  knew — not returns a follower could have captured. A disclosure-dated
  run would answer the tradeable question and is a one-flag change.
- **One horizon.** 20 trading days is a choice, not a discovery.
  5-day and 60-day runs cost one command each.

## What this does and does not license

- **Does not license** tuning the weights. There is no signal to tune
  toward; changing them now is fitting noise, which produces a model that
  scores better precisely because it has memorised randomness.
- **Does not license** any move toward live trading. Paper included —
  there is nothing here worth executing.
- **Does license** lifting the "no new signals until validation" freeze.
  The freeze existed to stop feature work from outrunning evidence. It
  has done its job, and the evidence now says the *specific* missing
  thing is a second source with history.

## Recommended next step

**Backfill SEC Form 4 from the EDGAR full-index archive.** It is the only
other source with deep, downloadable history (1993Q1–present, see
`docs/DATA_LINEAGE.md`), and it is the shortest path to actually testing
the multi-source thesis rather than a degenerate one-source shadow of it.
Until a second source has history, section 4 of this report will keep
reading INSUFFICIENT DATA no matter how many times it runs.

Cheap things worth doing first, since each is one command:

```powershell
py scripts/research_report.py --horizon 5  --output report-5d.md
py scripts/research_report.py --horizon 60 --output report-60d.md
```
