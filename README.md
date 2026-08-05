# Topos

A personal AI-assisted investment research platform. Topos aggregates signals
from multiple public data sources and scores opportunities by combining
several independent signals — it never acts on a single source alone. An AI
ranking engine ranks opportunities; it does not place trades directly. Only
after explicit risk checks pass does the execution layer act, and initially
that's paper trading only.

## Architecture

```
Data Sources
  -> Data Collection Layer      (topos/collectors/)
  -> Signal Extraction Layer    (topos/signals/)
  -> AI Ranking Engine          (topos/ranking/)
  -> Portfolio Decision Engine  (topos/portfolio/)
  -> Risk Management Layer      (topos/risk/)
  -> Broker Execution Layer     (topos/execution/)
  -> Performance Analytics Dashboard (dashboard/)
```

Every signal carries a `timestamp`, `source`, `confidence` score, `ticker`,
and `evidence` payload (`topos/signals/base.py`).

## Signal sources

| Source | Status |
| --- | --- |
| SEC Form 4 (insider buy/sell) | **Live** — `topos/signals/form4.py` |
| Congressional trade disclosures | **Live, House only** — `topos/signals/congress.py`, parsed from House Clerk PTR filings (see caveat below) |
| Earnings reports | **Live** — `topos/signals/earnings.py`, SEC 8-K Item 2.02 detection (timing only, see caveat below) |
| News sentiment | **Live** — `topos/signals/news.py`, Google News RSS + local VADER scoring, no API key |
| Technical indicators | **Live** — `topos/signals/technical.py`, RSI(14) + SMA 20/50 crossover from free Stooq price data |
| Reddit sentiment | Blocked — `topos/signals/reddit.py` is built and ready, but Reddit no longer grants the API access it needs (see below) |
| X/Twitter sentiment | **Live, opt-in** — `topos/signals/twitter.py`, needs a **paid** X API plan (see below) |
| Institutional ownership (13F) | **Live** — `topos/signals/institutional.py`, diffs a fund's 13F-HR against its own prior quarter (see caveat below) |
| Options activity | Not started |
| Analyst revisions | Not started |

**Congressional data caveat:** there is no free official *structured* API for
congressional trade disclosures — the House Clerk and Senate eFD systems
publish documents, not data. Topos used to read House Stock Watcher and
Senate Stock Watcher, open-source projects that parsed those documents into
public JSON, but in **August 2026 both S3 buckets began returning
`AccessDenied` to everyone** and that route closed.

Topos now goes to the source: it downloads the Clerk's yearly disclosure
archive, pulls each Periodic Transaction Report PDF, and parses the
transaction table itself (`topos/collectors/house_clerk.py`). Two
consequences worth knowing:

- **Coverage is partial.** Electronically filed reports carry a text layer
  and parse cleanly; paper filings are scans and are skipped rather than
  guessed at. The backfill prints its parse rate per year so a shortfall
  is visible rather than looking like a quiet quarter.
- **The Senate is dark.** Senate eFD sits behind an interstitial agreement
  form with no bulk archive, so `congress_senate` currently yields nothing.
  Anything resting on multi-source agreement is missing a chamber.

**Earnings caveat:** Topos flags 8-K filings that report Item 2.02 (the item
issuers use to furnish an earnings press release). That's a real-time timing
signal — "a report just dropped" — not a beat/miss signal. Actual
EPS-vs-estimate data needs a paid provider (Alpha Vantage, Finnhub, ...),
which isn't wired up.

**Reddit caveat:** Reddit closed unauthenticated/scraped access in 2023, and
as of its 2026 "Responsible Builder Policy" has gone further — self-serve
creation of new API apps is now blocked entirely, and the legacy Data API
(what `topos/signals/reddit.py` targets) is gated to applicants with "a
valid moderation use case." A stock-sentiment bot doesn't qualify, so this
signal is currently not obtainable through legitimate means, not just
inconvenient to set up. The code is fully built and will work the moment
`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` are set (silently skipped, no
error, until then) — kept in case Reddit's policy changes or a qualifying
use case comes along, but don't expect to unblock it soon.

**X/Twitter caveat:** X's free API tier does not include search access at
all as of this writing — this needs a paid Basic-tier (or higher) bearer
token from [developer.x.com](https://developer.x.com), set as
`TWITTER_BEARER_TOKEN`. There's no scraping fallback: getting around X's
anti-bot measures isn't something this project does. Skipped silently until
a token is set.

**How enrichment sources pick tickers:** news, Reddit, Twitter, and
technical indicators all need a ticker to look at — there's no free
firehose of "sentiment for the whole market." Each pipeline run, they only
look at tickers that Form 4 / congressional / earnings activity already
surfaced that run (capped at 20), rather than scanning blindly.

**Institutional ownership (13F) caveat:** 13F filings report holdings by
CUSIP, not ticker, and there's no free official CUSIP→ticker mapping
(CUSIP data itself is commercially licensed). Topos resolves CUSIPs via
[OpenFIGI](https://www.openfigi.com)'s free mapping API — works
unauthenticated at a low rate limit, or set `OPENFIGI_API_KEY` (free
signup) for a higher one. Coverage isn't complete; holdings that don't
resolve are dropped, not guessed at. Diffing a fund's holdings against its
own prior quarter also means fetching two 13F filings plus a filing-history
lookup per institution, so this is capped at 5 institutional filers per
pipeline run.

## Phase 1 MVP — done

- Form 4 filings pulled live from SEC EDGAR (no API key required).
- Congressional trade disclosures pulled live (see caveat above).
- All raw signals, ranked opportunities, and trade attempts stored in
  PostgreSQL (`topos/db/models.py`).
- Signal scoring: confidence heuristics per source (insider role + trade
  size for Form 4; trade size for congressional trades), aggregated per
  ticker with a multi-source-agreement bonus (`topos/ranking/ranker.py`).
- Opportunities, raw signals, and trade history displayed in Streamlit
  (`dashboard/app.py`).
- Paper trades executed via Alpaca — defaults to **dry run**, only submits
  real paper orders with `--execute` and valid Alpaca credentials.
- Returns tracked by reading Alpaca's own paper-account equity/P&L and
  position endpoints (`topos/execution/alpaca_client.py`) rather than
  reimplementing portfolio accounting — shown in the dashboard's
  Performance section once `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` are set.

Portfolio sizing and risk checks are intentionally simple for this phase:
equal-weight top-N tickers above a score floor, capped at a max position
weight and max open positions (`topos/portfolio/`, `topos/risk/`).

## Phase 2 — done

Earnings monitoring, news sentiment, Reddit sentiment, X/Twitter sentiment,
and technical indicators — see the signal sources table above for status
and caveats on each. Each source fails independently; one being down
(network blip, missing credentials, upstream outage) doesn't take down the
rest of the pipeline.

13F diffing and options/analyst-revision signals are still not implemented.

## Phase 3 — AI ranking layer — done

The ranking engine (`topos/ranking/ranker.py`) now produces a 0-100
**combined score** and a **BUY / SELL / HOLD recommendation** per ticker,
instead of a bare 0-1 attention score:

- **Direction matters, not just volume.** A ticker with several strongly
  bearish signals no longer scores the same as one with equally strong
  bullish signals — the score is scaled down when signals disagree on
  direction (buy vs. sell), based on each signal's own `evidence.direction`.
- **No single-source recommendations.** Matching the project's own stated
  principle ("should not blindly follow any single source"), a ticker
  needs signals from at least 2 distinct sources agreeing on direction to
  get a BUY or SELL recommendation. One strong signal alone caps out at
  HOLD, however high its score.
- **The portfolio engine only acts on BUY.** This closes a real bug from
  Phase 1/2: the old ranking only measured "how much attention is this
  ticker getting," so a ticker could rank #1 purely on strong *sell*
  signals and the portfolio engine would still buy it (nothing checked
  direction). It now filters on `recommendation == "BUY"` explicitly.
  Institutional-ownership increases (Signal E) count toward this the same
  as any other source.

**Schema note:** `ranked_opportunities` gained two required columns
(`recommendation`, `net_direction`) and `score` changed scale from 0-1 to
0-100. `SQLAlchemy`'s `create_all()` won't retrofit an existing table, so
if you already have a deployed/local database from before this change,
drop the `ranked_opportunities` table before redeploying — it's cached
rankings, not source-of-truth data, so this is safe. `signals` and `trades`
are untouched.

## Backtesting — point-in-time data and signal validation

The platform's scoring weights were all hand-tuned and had never been
checked against what the tickers actually did next. This layer measures
that. Two foundational data problems had to be fixed first:

**Signals are dated by event, not by scrape.** Every source except
congressional trades used to stamp `datetime.now()` — the moment the
scraper ran. An insider trade from July 15 scraped on August 5 was
recorded as August 5, so a "20-day forward return" measured a window in
which the market had already reacted weeks earlier. Every signal now
carries an explicit `event_date` (the insider's trade date, the SEC
filing date, the last price bar, the sentiment snapshot day) separate
from the observation `timestamp`. A record that can't be dated is dropped
rather than backdated to today.

**Signals are deduplicated.** The pipeline runs on a schedule over
overlapping windows, and previously re-inserted the same Form 4 as a
fresh signal every run — inflating a ticker's signal count in ranking and
making stored history useless. Signals now carry a natural `dedup_key`
with a database unique constraint.

### Liquidity screen (`topos/screening/liquidity.py`)

Untradeable names were reaching Ranked Opportunities. A ticker must now
clear a dollar-volume floor, a minimum price, and a minimum amount of
price history before it can be ranked or traded. Screening uses dollar
volume (close x volume), not share count — 10M shares of a $0.30 stock is
not the liquidity that 100k shares of a $200 stock is. A ticker with no
stored price history fails the screen rather than getting the benefit of
the doubt. Raw signals for screened-out tickers are still stored; they
just aren't ranked or traded.

### Running it

```bash
python scripts/run_backtest.py                      # score bucket vs. return
python scripts/run_backtest.py --group-by source    # which sources work
python scripts/run_backtest.py --group-by confidence --horizons 5,20
```

The same score-bucket table is in the dashboard's **Signal Validation**
section.

### Accelerating validation with backfill

Waiting for live accumulation is slow. Congressional trades are the
cheapest history to backfill by a wide margin — the House/Senate Stock
Watcher endpoints return their entire archive (2020 onward) on every
request, so the pipeline was already downloading years of disclosures and
discarding all but the most recent rows.

```bash
python scripts/backfill_congress.py --since 2024-01-01 --skip-prices  # see the scale first
python scripts/backfill_congress.py --since 2024-01-01                # then fetch prices
```

Price backfill is the slow half (one Stooq request per ticker, rate
limited), so run with `--skip-prices` first to see how many tickers
you'd be committing to. `docs/DATA_LINEAGE.md` covers what's backfillable
for the other seven sources and what isn't worth pursuing.

### Reading the results honestly

- **Returns are direction-adjusted.** A SELL signal that correctly called
  a drop is a win. Grading on raw price change would score every bearish
  call backwards.
- **Unmeasurable signals are excluded, not zeroed.** A signal too recent
  to have a full forward window has no result; counting it as 0% would
  drag averages toward zero and make the strategy look flatter and safer
  than it is.
- **Thin buckets are flagged.** Anything under 20 observations is marked
  `(thin)` in the CLI and the dashboard. A 2-sample win rate is noise.
  **The scoring weights should not be tuned off thin buckets** — this
  table only becomes evidence once the pipeline has accumulated real
  history, which takes weeks of scheduled runs.
- Sharpe is annualized by holding period (`sqrt(252/horizon)`), assumes a
  0% risk-free rate, and assumes non-overlapping trades.

**Status: the harness is built and verified, but it has not yet produced
a verdict on Topos's scoring.** That requires accumulated live history.
Nothing here yet says the score predicts returns.

### Required migration for existing deployments

Phase 2 added `event_date` and `dedup_key` to `signals` as NOT NULL
columns. `create_all()` only creates missing *tables* — it will not add
columns to one that already exists, so an already-deployed database
silently keeps the old schema and **the next pipeline run fails with
"column event_date does not exist"**. Run once against the deployed
database before redeploying:

```bash
python scripts/migrate_phase2.py            # report what needs doing
python scripts/migrate_phase2.py --apply    # drop and recreate `signals`
```

Existing rows are discarded rather than migrated forward: they were
stamped with scrape time instead of event time and duplicated on every
scheduled run, so their real event dates were never recorded and can't be
reconstructed. `price_bars` and `ranked_opportunities` are unaffected.

## Setup

```bash
cp .env.example .env   # fill in SEC_EDGAR_USER_AGENT (your name + email); Alpaca keys can wait
docker compose up --build
```

Or locally:

```bash
pip install -r requirements.txt
python scripts/init_db.py
python scripts/run_pipeline.py     # dry run — collects, ranks, prints intended trades
streamlit run dashboard/app.py
```

SEC EDGAR requires a descriptive `User-Agent` header identifying who's
making requests (name + contact email) — see
https://www.sec.gov/os/accessing-edgar-data. Set `SEC_EDGAR_USER_AGENT`
accordingly.

### Research without a database server

Backtesting and the validation report need no Postgres, no Docker and no
network. Point `DATABASE_URL` at a file and everything runs locally:

```powershell
$env:DATABASE_URL = "sqlite:///topos.db"    # PowerShell
```
```bash
export DATABASE_URL="sqlite:///topos.db"    # bash
```

This matters more than it sounds. The deployed dashboard runs on Postgres,
but research against a *remote* Postgres puts a VPN and a firewall between
you and a question about a scoring model — and outbound 5432 is exactly
the port corporate and home networks like to block. A local file removes
that entire class of failure from work that never needed a server.

`tests/test_sqlite_portability.py` keeps this working: the schema, the
attribution NULL detection and the whole report are exercised against
SQLite, so a Postgres-only construct fails in CI rather than the first
time someone tries to run research offline.

## Deploying to Render

`render.yaml` defines a Blueprint with three resources:

- `topos-db` — the Postgres instance.
- `topos-dashboard` — a web service running the Streamlit dashboard
  (Dockerfile-based, binds to Render's `$PORT`).
- `topos-pipeline` — a cron job running `python scripts/run_pipeline.py`
  hourly (UTC — adjust the schedule for your needs; it defaults to dry run,
  so it won't place real trades until you also set `--execute` and Alpaca
  keys in the dashboard).

To deploy: push this repo to GitHub, then in the Render dashboard choose
"New > Blueprint" and point it at the repo. Fill in `SEC_EDGAR_USER_AGENT`
and (optionally) `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` as secrets when
prompted — they're marked `sync: false` in the blueprint so Render won't
try to auto-populate them.

Note: Render discontinued its free Postgres tier, and later also retired
the old named tiers (including `starter`) for new databases — `topos-db`
is set to `basic-256mb`, Render's current cheapest paid plan. Check
[render.com/pricing](https://render.com/pricing) and your dashboard before
deploying — this repo has no way to verify current pricing/plan names
live, and Render has changed this naming scheme before.

## Disclaimer

This is a personal research tool. Nothing it outputs is investment advice.
It runs against Alpaca's paper trading endpoint only until you deliberately
supply live credentials and pass `--execute`.

## Validation research report

Once there's enough history, this answers whether the scoring model has
predictive power:

```bash
python scripts/research_report.py                      # 20-day horizon
python scripts/research_report.py --horizon 5 --output report.md
```

Six sections: per-source performance, per-score-bucket performance, the
rank correlation between score and forward return, multi-source versus
single-source cohorts, and a recommendation on whether the weights should
move.

Significance comes from **permutation tests**, not a t-approximation.
Returns are not normal and these samples are small, and a normal
approximation overstates significance exactly when the sample is
thinnest — which is the failure mode the whole exercise exists to avoid.

The recommendation defaults to **UNCHANGED** and the bar for anything
else is deliberately high: no inference at all below n=30, findings
flagged provisional below n=100, and a negative correlation returns
INVESTIGATE (suspecting a look-ahead error or inverted convention) rather
than a mandate to retune. Tuning weights against a sample too small to
separate skill from noise produces a model that looks better precisely
because it has been fitted to randomness.
