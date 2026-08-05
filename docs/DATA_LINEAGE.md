# Data lineage

Every signal Topos stores, where its date comes from, how it's
deduplicated, and how its confidence is computed. Confidence formulas are
transcribed from the code — if they drift, the code is the truth and this
file is a bug.

**All confidence weights below are hand-tuned and unvalidated.** None has
been shown to predict returns. That is what the backtesting layer exists
to determine, and it has not yet run on enough real history to say.

## Summary

| Source | `event_date` from | Real event? | Deduplicated on |
|---|---|---|---|
| `sec_form4` | earliest `transactionDate` in the filing; falls back to `periodOfReport` | Yes | filing URL |
| `congress_house` (Senate currently dark) | transaction date as filed in the PTR | Yes | chamber + member + ticker + date + direction |
| `sec_8k_earnings` | 8-K filing date (atom `updated`) | Yes | filing URL |
| `institutional_13f` | 13F-HR filing date (atom `updated`) | Yes | filing URL + CUSIP |
| `technical` | date of the most recent price bar used | Yes | ticker + bar date |
| `news_sentiment` | publication date of the freshest article | Yes | ticker + freshest article date |
| `reddit_sentiment` | creation date of the newest post | Yes | ticker + newest post date |
| `twitter_sentiment` | creation date of the newest tweet | Yes | ticker + newest tweet date |

No source uses scrape time. A record that cannot be dated is dropped
rather than stamped with today — a fabricated date silently corrupts
every forward return measured from it.

---

## SEC Form 4 — insider trades

- **Collector**: `topos/collectors/sec_edgar.py` — EDGAR current-filings
  atom feed, then each filing's XML. No API key; SEC requires a
  descriptive `User-Agent`.
- **Event date**: the earliest `transactionDate` across the filing's
  non-derivative transactions. When a filing reports several trades, the
  earliest is when the insider first acted. Falls back to the
  document-level `periodOfReport` (which the Form 4 schema requires);
  a filing with neither is dropped.
- **Dedup**: `sec_form4:{filing_url}` — one filing yields at most one
  signal.
- **Direction**: sign of net shares across non-derivative transactions
  (`A` acquired adds, `D` disposed subtracts). Zero net is `neutral` and
  is not graded by the backtester.
- **Confidence**: `0.2 + role_weight + size_weight`, clamped to [0, 1]
  - `role_weight` = 0.3 if officer or director, else 0.15
  - `size_weight` = `min(total_value / 1_000_000, 1.0) * 0.5`
  - So a $1M+ trade by an officer scores 1.0; a small trade by a
    non-insider floors near 0.35.

## Congressional trades

- **Collector**: `topos/collectors/house_clerk.py` — the House Clerk's own
  disclosure archive. `{year}FD.zip` carries an XML index of every filing,
  from which Periodic Transaction Reports (filing type `P`) are fetched as
  PDFs from `ptr-pdfs/{year}/{doc_id}.pdf` and parsed by
  `topos/collectors/ptr_parser.py`.
  - **Why PDFs.** This used to read House Stock Watcher and Senate Stock
    Watcher JSON — open-source projects that parsed these same filings
    into structured data. In August 2026 both S3 buckets began returning
    `AccessDenied` to everyone, verified against the origin. There is no
    free official *structured* API; the Clerk publishes documents, which
    is precisely the gap those mirrors filled.
  - **Coverage is partial by construction.** Electronically filed reports
    have a text layer and parse cleanly. Paper filings are scanned images
    with no text, and are skipped rather than guessed at. `BackfillResult`
    reports the parse rate per year so a shortfall is visible instead of
    looking like a quiet quarter.
  - **Senate is not covered.** Senate eFD sits behind an interstitial
    agreement form and has no equivalent bulk archive, so `congress_senate`
    currently produces no signals. Anything scored on multi-source
    agreement should be read with that in mind — one chamber is dark.
  - **Funds are excluded.** Rows whose asset type marks a pooled vehicle
    (`MF`, `EF`, `ETF`, …) are dropped: an index-fund purchase carries a
    ticker but is not a view on a company.
- **Event date**: `transaction_date` (the trade), falling back to
  `disclosure_date`. Note these differ by up to 45 days under the STOCK
  Act, so the *disclosure* is when the market could first react while the
  *transaction* is when the member acted. Topos currently dates by
  transaction, which is the more conservative choice for measuring
  informational value but means some forward windows begin before the
  information was public.
- **Dedup**: `congress_{chamber}:{member}:{ticker}:{date}:{direction}` —
  these records carry no stable upstream id.
- **Direction**: `purchase` → buy, `sale` → sell. Exchanges and other
  types produce no signal.
- **Confidence**: `0.25 + min(amount_midpoint / 250_000, 1.0) * 0.4`
  - Amounts are disclosed as ranges (e.g. "$100,001 - $250,000"); the
    midpoint is used.

## SEC 8-K — earnings timing

- **Event date**: the 8-K filing date. This is a *timing* signal — an
  earnings release just dropped — not a beat/miss signal. Actual
  EPS-versus-estimate data needs a paid provider.
- **Dedup**: `sec_8k_earnings:{filing_url}`.
- **Direction**: none is inferred. **These signals carry no direction and
  are therefore excluded from backtest grading entirely** — there is no
  directional claim to be right or wrong about. They still contribute to
  a ticker's raw score base.
- **Confidence**: fixed `0.4`. Not size- or content-aware.

## SEC 13F-HR — institutional ownership

- **Event date**: the 13F filing date, not the quarter it covers. 13F
  holdings are disclosed with a substantial lag; the filing date is when
  the market could first act on them.
- **Dedup**: `institutional_13f:{filing_url}:{cusip}` — one filer's
  disclosed change in one holding.
- **Direction**: always `buy`. Only *increases* are emitted; position
  reductions and exits are not currently detected.
- **Confidence**: `0.3 + min(pct_change, 1.0) * 0.5`, emitted only when
  `pct_change >= 0.10` (a 10% share increase or a brand-new position).
- **Caveat**: CUSIPs are resolved to tickers via OpenFIGI. Coverage is
  incomplete; unresolved holdings are dropped rather than guessed at.
  Capped at 5 filers per run — each costs a filing-history lookup plus
  two holdings tables.

## Technical indicators

- **Event date**: the date of the most recent price bar the indicators
  were computed from — the last session the market actually traded.
- **Dedup**: `technical:{ticker}:{bar_date}` — one reading per ticker per
  session, so recomputing the same bar doesn't stack duplicates.
- **Direction**: RSI(14) below 30 is oversold → buy; above 70 overbought
  → sell (mean-reversion reading). Between those, the SMA 20/50 crossover
  decides.
- **Confidence**: `0.2 + min(strength, 1.0) * 0.5` where `strength` is
  the RSI distance past the threshold, or the relative SMA gap in the
  neutral band.

## News sentiment

- **Collector**: Google News RSS search. Unofficial — Google could change
  or rate-limit it without notice.
- **Event date**: the publication date of the freshest article in the
  batch. A rolling aggregate is dated by its newest input, not by when it
  was computed: if the newest article is five days old, the sentiment
  event happened five days ago.
- **Dedup**: `news_sentiment:{ticker}:{freshest_article_date}` — keyed to
  content, so re-scanning unchanged coverage dedupes rather than
  recording the same stale sentiment daily.
- **Direction**: sign of the mean VADER compound score across headlines;
  `|mean| < 0.05` produces no signal.
- **Confidence**: `0.2 + |mean_compound| * 0.6 + min(count / 20, 0.2)`
- **Caveat**: VADER is a general-purpose lexicon, not finance-tuned. It
  has no concept of "beat expectations" versus "missed"; headline
  sentiment is a weak proxy for the market's reading.

## Reddit sentiment — currently unavailable

- **Status**: built and functional, but Reddit's Responsible Builder
  Policy restricts the Data API to moderation use cases. A
  stock-sentiment bot does not qualify, so this source cannot be
  legitimately enabled. Skipped silently without credentials.
- **Event date**: newest post's `created_utc`.
- **Dedup**: `reddit_sentiment:{ticker}:{newest_post_date}`.
- **Confidence**: `0.15 + |mean_compound| * 0.5 + min(engagement / 5000, 0.25)`

## X/Twitter sentiment — requires a paid plan

- **Status**: built; X's free tier has no search access. Skipped silently
  without a bearer token.
- **Event date**: newest tweet's `created_at`. The collector explicitly
  requests `tweet.fields=created_at`, which X omits by default.
- **Dedup**: `twitter_sentiment:{ticker}:{newest_tweet_date}`.
- **Confidence**: `0.15 + |mean_compound| * 0.5 + min(count / 50, 0.25)`

---

## From confidence to score

Per-source confidences are combined additively
(`topos/ranking/attribution.py`):

```
score = sum(source contributions) + bonuses - penalties
```

- **Contributions** — each source's share of the confidence-weighted
  base, on a 0-100 scale.
- **Multi-source agreement** — `+5` per additional source agreeing on
  direction, capped at `+20`. Requires *directional* agreement; two
  sources merely mentioning a ticker is not corroboration.
- **Conflicting signals** — up to `-25`, scaled by how evenly split the
  buy and sell weight is.
- **Staleness** — up to `-15`, scaled by the age of the newest signal
  against a 90-day horizon. Computed against an `as_of` date so a
  backtest can reconstruct a historical score rather than penalizing old
  signals for being old today.
- **Clamped to 0-100**, recorded as an explicit adjustment so the parts
  always reconcile to the total.

A BUY or SELL additionally requires at least two distinct sources and
`|net_direction| >= 0.2`; a single source, however strong, caps at HOLD.

---

## Historical backfill availability

Live accumulation is slow — validating the score needs months of
scheduled runs. This is what could be backfilled to accelerate it.

| Source | Archive | Coverage | Effort |
|---|---|---|---|
| **Congressional (House)** | [Clerk `{year}FD.zip` + PTR PDFs](https://disclosures-clerk.house.gov/) | 2008–present | Medium |
| **Technical** | Stooq daily history | years | **Trivial** |
| Form 4 | [EDGAR full-index](https://www.sec.gov/Archives/edgar/full-index/) | 1993Q1–present | Medium |
| 8-K earnings | EDGAR full-index | 1993Q1–present | Medium |
| 13F | EDGAR full-index | 1993Q1–present | High |
| News | [GDELT](https://www.gdeltproject.org/) (free, 1979+) | decades | High |
| Reddit | Pushshift dead since May 2023 | — | Not advisable |
| X/Twitter | paid tiers only | — | Not viable |

### The two quick wins

**Congressional trades still have the deepest downloadable history.**
The Clerk publishes a complete archive per year, so `scripts/backfill_congress.py`
can ingest several years in one run — no other source offers that without
significant work. It is no longer free, though: the first run downloads a
few thousand PDFs. Downloads are cached on disk, so the cost is paid once
and re-parsing (which the parser will need as its output is inspected) is
instant afterwards.

**Price history is already complete.** `PriceCollector.daily_bars()`
returns Stooq's full available history, and `backfill_ticker()` stores
all of it. No additional work needed.

### The medium ones

EDGAR publishes quarterly index files listing every filing by form type
back to 1993Q1, free, no key. Backfilling Form 4 means walking those
indexes for the target period and fetching each filing's XML — the same
parser already handles the document, so the work is enumeration and rate
limiting (SEC asks for ~10 requests/second and a descriptive
`User-Agent`). 13F is harder because each signal requires pairing a
filing with the *same filer's* prior-quarter filing.

### The ones not worth pursuing

News backfill would require GDELT, a different source with different
coverage and article selection than the Google News RSS feed used live.
Backfilled sentiment would not be measuring the same signal the live
system produces, so validating one would not validate the other.

Reddit's public archive (Pushshift) was withdrawn in May 2023.
Community-maintained mirrors exist, but Reddit's own API is already
closed to this use case, so a backfilled Reddit signal could not be run
live even if validated.

X/Twitter historical search has never had a free tier.
