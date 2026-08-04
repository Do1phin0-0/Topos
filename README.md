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
| Congressional trade disclosures | **Live** — `topos/signals/congress.py`, via House/Senate Stock Watcher (see caveat below) |
| Earnings reports | **Live** — `topos/signals/earnings.py`, SEC 8-K Item 2.02 detection (timing only, see caveat below) |
| News sentiment | **Live** — `topos/signals/news.py`, Google News RSS + local VADER scoring, no API key |
| Technical indicators | **Live** — `topos/signals/technical.py`, RSI(14) + SMA 20/50 crossover from free Stooq price data |
| Reddit sentiment | **Live, opt-in** — `topos/signals/reddit.py`, needs a free registered Reddit API app (see below) |
| X/Twitter sentiment | **Live, opt-in** — `topos/signals/twitter.py`, needs a **paid** X API plan (see below) |
| SEC 13F-HR (hedge fund holdings) | Collector wired, extraction is a follow-up (needs prior-quarter diffing to be meaningful) |
| Options activity | Not started |
| Analyst revisions | Not started |

**Congressional data caveat:** there is no free official structured API for
congressional trade disclosures — the House Clerk and Senate eFD systems
only publish PDFs. Topos pulls from [House Stock Watcher](https://housestockwatcher.com)
and [Senate Stock Watcher](https://senatestockwatcher.com), open-source
projects that parse those official PDFs into public JSON. That means Topos's
congressional signal is only as fresh/accurate as those mirrors.

**Earnings caveat:** Topos flags 8-K filings that report Item 2.02 (the item
issuers use to furnish an earnings press release). That's a real-time timing
signal — "a report just dropped" — not a beat/miss signal. Actual
EPS-vs-estimate data needs a paid provider (Alpha Vantage, Finnhub, ...),
which isn't wired up.

**Reddit caveat:** Reddit closed unauthenticated/scraped access in 2023.
Register a free "script" app at
[reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) and set
`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` — Reddit sentiment is silently
skipped (no error) until you do.

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

Note: Render discontinued its free Postgres tier a while back, so
`topos-db` is set to the `starter` plan. Check
[render.com/pricing](https://render.com/pricing) and your dashboard before
deploying — this repo has no way to verify current pricing at write time.

## Disclaimer

This is a personal research tool. Nothing it outputs is investment advice.
It runs against Alpaca's paper trading endpoint only until you deliberately
supply live credentials and pass `--execute`.
