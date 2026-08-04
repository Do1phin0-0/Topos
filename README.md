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
| SEC 13F-HR (hedge fund holdings) | Collector wired, extraction is a follow-up (needs prior-quarter diffing to be meaningful) |
| Earnings reports | Not started |
| News sentiment | Not started — needs a provider (NewsAPI, Finnhub, etc.) |
| Technical indicators | Not started |
| Options activity | Not started |
| Analyst revisions | Not started |
| Social sentiment | Not started |

**Congressional data caveat:** there is no free official structured API for
congressional trade disclosures — the House Clerk and Senate eFD systems
only publish PDFs. Topos pulls from [House Stock Watcher](https://housestockwatcher.com)
and [Senate Stock Watcher](https://senatestockwatcher.com), open-source
projects that parse those official PDFs into public JSON. That means Topos's
congressional signal is only as fresh/accurate as those mirrors.

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

Everything else in the architecture diagram (13F, earnings, news/social
sentiment, options flow, analyst revisions) is documented intent for Phase
2, not implemented yet.

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
