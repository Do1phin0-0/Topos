# Validation results — final, 2026-08-07

The question was: **does the scoring model have predictive power?**

**Answer: no.** Not "not yet", not "the sample is too small" — the
experiment ran properly, on two independent sources, 58,327 signals,
21,122 point-in-time rankings, measured against SPY, and the model does
not rank opportunities in a way that earns money.

This document is the record of that, including the two occasions the
report itself got the answer wrong before the measurement was fixed.

## The numbers

Horizon 20 trading days, returns relative to SPY.

| question | answer |
|---|---|
| Do individual sources predict returns? | No. congress −0.21% (n=3,434, 50% win), Form 4 −0.34% (n=43,661, 48% win). Both slightly negative against the market. |
| Do higher score buckets earn more? | Not usefully. Bucket means order at ρ=+0.67 across 10 buckets, but the spread is noise-scale: −0.65% to +1.92% with no clean progression. |
| Is score correlated with forward return? | ρ=+0.020, p=0.031, n=11,348. Statistically detectable and **explains 0.04% of return variation.** |
| Does multi-source agreement beat single-source? | **The opposite.** Multi −0.67% vs single +0.56%, a −1.23% gap at p=0.015 on 3,828 and 7,520 observations. |
| Should the weights change? | No. UNCHANGED, not safe to act. |
| Is any of this tradeable? | No. |

### On the score correlation

ρ=0.020 at n=11,348 is the most instructive number here. It is
statistically significant and economically meaningless, and the gap
between those two facts is where backtests go to die. A large sample
makes tiny effects significant; significance is not size.

Worth stating precisely, because "pure noise" would be an overstatement:
the bucket ordering at ρ=+0.67 is not random, and averaging within
buckets is exactly what reveals a small effect hiding under large
per-name variance. So there may be a real, tiny relationship. It is far
too small to survive transaction costs, and this project models none.

### On multi-source underperformance

This is the one result with an economically meaningful magnitude, and it
contradicts the project's founding assumption. Read it carefully before
generalising:

Form 4 signals are dense — 43,661 filings across ~452 tickers means
nearly every ticker carries insider activity at nearly every snapshot.
So "multi-source" here effectively means *"congress traded it too"*, and
the comparison is really measuring what congressional involvement adds on
top of insider data. The answer is that it subtracts, which is consistent
with congress being −0.21% standalone.

It is **not** a general refutation of corroboration. It is a specific
finding about these two sources.

## What went wrong in the measurement, twice

Both worth keeping, because both produced a confident wrong answer that
looked exactly like a right one.

1. **No benchmark.** Returns were absolute. Over 60 trading days of a
   rising market every bucket earned roughly +3%, which reads as success
   and is approximately what the index returned. Fixed by measuring
   excess return against SPY, with the rule that an unmeasurable
   benchmark leg yields `None` rather than a silent fall back to the
   absolute number — which would relabel beta as alpha.

2. **Guardrails that only checked sample size.** With two sources loaded,
   the report announced "the ranking has directional validity", verdict
   DECREASE, **safe to act: yes** — off ρ=0.020. Every threshold in the
   guardrails was about *n* and none about *magnitude*, so the protection
   got weaker exactly as the data got better. Fixed with an effect-size
   floor and a distinct NEGLIGIBLE verdict.

The first one was found by reading a number that looked too good. The
second was found by disbelieving a recommendation the tool had just made.
Neither was caught by a test, because tests check what you thought to
check.

## What this licenses

- **No weight tuning.** There is no signal to tune toward. Adjusting
  weights against ρ=0.02 fits noise, and the fitted model will score
  better precisely because it has memorised randomness.
- **No trading, paper included.** Nothing here is worth executing.
- **The validation freeze is over.** It did its job: it stopped feature
  work from outrunning evidence, and the evidence arrived.

## Where the remaining doubt actually lives

Ranked by how much they could move the answer:

1. **Two-thirds of tickers had no price history** (452 of 1,342). Whatever
   is systematically missing — foreign listings, ADRs, small caps — is
   missing from every number above.
2. **Congressional signals are dated by transaction, not disclosure.**
   The STOCK Act allows 45 days between them, so these windows measure
   what a member knew, not what a follower could have traded. A
   disclosure-dated run answers the tradeable question and is a small
   change.
3. **Confidence formulas were never calibrated.** Congressional
   confidence is `0.25 + min(midpoint/250k, 1) × 0.4` — a number chosen
   by hand, not fitted to anything. The same is true of every weight in
   `attribution.py`. The score was assembled from plausible-sounding
   judgments and this is the first time any of them met an outcome.
4. **Only two of eight sources have history.** Earnings, 13F, news,
   technical and sentiment remain untested — though note that adding
   sources is what *created* the multi-source result above, and it was
   negative.

## Honest bottom line

Following congressional and insider disclosures, scored this way, did not
beat buying SPY over 2024–2026. That is not a surprising result — it is
roughly what the academic literature on both signals would predict once
costs and publication lag are accounted for — but it is now *your*
result, measured on your data, rather than something taken on faith.

The machinery built to determine that is sound and reusable:
point-in-time replay, benchmark-relative returns, permutation tests,
sample-size and effect-size floors, and a report that refuses to endorse
its own output. That is the durable asset here. The scoring model is not.
