# Validation results — final, 2026-08-07

> **Both known holes were closed on 2026-08-07 and every number below was
> re-measured. The verdict did not change; it got cleaner.** Price
> coverage went from 452 tickers to 1,254 (963,329 new bars), and
> congressional signals were re-dated by disclosure as well as by
> transaction. See "After closing both holes" at the end — the headline
> is that the two effects this document treated as real both weakened,
> and one of them disappeared entirely.

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

1. **Two-thirds of tickers had no price history** (452 of 1,435), and
   the 2026-08-07 diagnostic says the gap is worse than a coverage
   problem — it is a *biased* coverage problem.

   91% of the missing are ordinary US symbols, not foreign listings, and
   36% of a retried sample came back with full history, so much of the
   gap is a source outage rather than a fact about the market.

   What did not come back is the concerning part: ANSS, BERY, AMED,
   AZPN, ATSG, BLL — 2024-2026 acquisitions and delistings. **Acquired
   companies are bought at a premium.** If congress or insiders were
   buying them beforehand, those are precisely the trades that worked,
   and they are the ones systematically absent. The missing names skew
   toward winners, so their absence pushes every measured return in this
   document *downward*. The null result is not safe to treat as final
   until coverage is repaired.
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


## After closing both holes

Two things could have overturned the null verdict. Both were addressed,
and the result is a stronger null than before.

**Coverage repair.** 891 of the 983 missing tickers came back with data —
963,329 price bars. Price history went from 452 tickers to **1,254**, and
measurable observations from 11,348 to **19,392**. The earlier gap was
indeed a source outage, not a fact about the market.

**Disclosure dating.** Congressional signals re-anchored to when the
filing became public rather than when the member traded, answering the
tradeable question instead of the informational one.

### What changed

| measure | original (452 tickers) | coverage repaired | + disclosure-dated |
|---|---|---|---|
| observations | 11,348 | 19,392 | 19,046 |
| score↔return | ρ=+0.020, p=0.031 | ρ=+0.012, **p=0.086** | ρ=+0.011, **p=0.122** |
| verdict | NEGLIGIBLE | **NO SIGNIFICANT RELATIONSHIP** | **NO SIGNIFICANT RELATIONSHIP** |
| multi vs single | −1.23%, **p=0.015** | −0.71%, **p=0.057** | −0.66%, **p=0.081** |
| verdict | UNDERPERFORMS | **NO SIGNIFICANT DIFFERENCE** | **NO SIGNIFICANT DIFFERENCE** |
| congress standalone | −0.21% | −0.04% | **+0.13%** |
| Form 4 standalone | −0.34% | −0.34% | −0.34% |

### Three things worth stating plainly

1. **The multi-source finding was an artifact.** This document called it
   "the one result with an economically meaningful magnitude". With a
   proper sample it fell from −1.23% (p=0.015) to −0.71% (p=0.057) and
   stopped being significant. It was a property of the biased 452-ticker
   sample, not of the signals. Treat the earlier claim as withdrawn.

2. **The score correlation also failed to survive.** ρ=0.020 at p=0.031
   became ρ=0.012 at p=0.086 — no longer statistically detectable at all,
   let alone actionable. The effect-size floor turned out to be belt and
   braces: with a better sample, the significance test rejects it on its
   own.

3. **The survivorship prediction was directionally right and small.**
   Congress improved from −0.21% to −0.04% once the missing names were
   recovered, consistent with the missing names skewing toward winners.
   It did not turn a losing signal into a winning one.

Disclosure-dating nudged congress to **+0.13%** with a 50% win rate and a
Sharpe of 0.05 — indistinguishable from zero, and mildly interesting only
because the *opposite* was expected. If any tiny effect exists it looks
more like post-disclosure attention than private information. It is not
large enough to be worth another sentence.

### The verdict, now properly earned

Every plausible rescue has been tried: more data, better coverage, three
horizons, a benchmark, and both date conventions. The scoring model does
not predict returns. That is now a measurement rather than a suspicion.

## Price-action signals — 2026-08-18

A different hypothesis than disclosure lag: does the market's own recent
behaviour (gap, relative volume, 20/60-day momentum, 5-day reversal)
predict what it does next? Five new sources, computed purely from stored
price bars, backfilled and run through the identical pipeline plus a flat
10bps round-trip cost model. 212,719 signals generated.

| question | answer |
|---|---|
| Do the five price-action sources predict returns, net of cost? | No. All cluster near zero: `price_gap` −0.08%, `price_rel_volume` −0.18%, `price_momentum_20d` −0.20%, `price_momentum_60d` −0.28%, `price_reversal_5d` +0.02%. Win rates 48-50% across the board. |
| Does adding them to the score improve the correlation? | It got *more* null. rho=−0.000, p=0.940, n=40,319 — no longer even the marginal p=0.122 signal seen with two sources. |
| Does multi-source agreement beat single-source, now with 7 sources? | **Reported as -19.50% (p=0.000), then retracted — see below.** |

### Momentum came back negative, not positive

Worth stating plainly: momentum is one of the most replicated effects in
equity markets, and it came back slightly negative here (`price_momentum_20d`
−0.20%, `price_momentum_60d` −0.28%), not positive. At this magnitude — a
fraction of a percent against a benchmark, on a sample this size — it reads
as noise rather than a real reversal of a textbook effect, but it is not
the confirming positive-control result the module docstring hoped for
either. Neither claim should be overstated from these numbers.

### The multi-vs-single-source finding, retracted a second time — and for a different reason

`docs/VALIDATION_RESULTS.md`'s original release already retracted one
version of this finding as a biased-sample artifact from missing price
coverage. This run produced the same shape of result again — a large,
"significant" gap on a tiny, lopsided cohort (single n=249, multi
n=40,070) — and investigating it (`scripts/diagnose_single_source_cohort.py`)
found two things:

1. **Outlier domination.** The 5 most extreme of 249 observations account
   for 84% of the cohort's total absolute return. Four of those five are
   the *same ticker* (BMNR) measured on four adjacent snapshot dates
   during one freak rally — one company's move counted four times, not
   four independent data points.
2. **A structural flaw, not (only) a sampling accident.** Every one of
   the 249 single-source rows carries recommendation `HOLD`. That is not
   a coincidence of this sample — it is guaranteed by `attribution.py`'s
   own rule that a ticker needs 2+ sources agreeing before it can ever
   receive a BUY or SELL call. A single source caps out at HOLD *by
   construction*, and HOLD rows get no directional sign-adjustment; they
   are graded on raw benchmark-relative drift. Multi-source rows are a
   mix that includes real, sign-adjusted BUY/SELL calls. The comparison
   was therefore never actually testing "does agreement between sources
   help" — it was comparing unadjusted drift on weakly-signaled names
   against direction-graded performance on confidently-signaled names.
   This has been true since the *original* 2-source validation; it just
   took a larger, more diverse signal set to expose it clearly.

**This metric (`multi_vs_single_source`) should be read as unreliable as
currently designed, not merely unlucky this one run.** It has now
produced a large, statistically "significant" but ultimately artifactual
result twice, for two different underlying reasons. A meaningful version
of this test would need to either grade single-source opportunities on
their lone signal's own directional evidence (rather than defaulting to
unadjusted HOLD treatment), or compare cohorts that can both actually
reach BUY/SELL — e.g. exactly-2-source versus 3-or-more-source agreement.
Neither has been built. Until one is, this section of the report should
be read, not acted on.

### Updated bottom line

Price-action does not rescue the model. Five more sources, a cost model,
and 212,719 additional signals later, the honest reading is unchanged
from the original verdict: the scoring model does not predict returns,
and nothing measured since — including this run — has found an exception
that survives scrutiny.
