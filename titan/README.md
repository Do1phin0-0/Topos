# Titan

A local, production-oriented application: congressional trade tracker, insider
trade tracker, a signal scoring engine, Alpaca paper trading, and a Streamlit
dashboard — served through a FastAPI backend backed by PostgreSQL.

All five features from the original spec are built and verified end-to-end
(see Status below). Verification note: this was built in a sandboxed
environment whose outbound proxy blocks sec.gov, the Stock Watcher data
mirrors, and Alpaca — so signal parsing/scoring logic is verified against
realistic fixtures and mocks, and the full stack (FastAPI + Postgres +
Streamlit, all as real running processes, not just test clients) is verified
end-to-end with seeded data. The actual live HTTP calls to those three
external services are untested from this environment and are worth a real
run on your end before trusting fully.

Titan is a separate application from `../topos` (the sibling project in this
repo). Where Topos is a single Streamlit app reading straight from Postgres,
Titan is structured with a proper API layer: FastAPI serves data and exposes
pipeline-trigger endpoints, and the Streamlit dashboard is a client of that
API rather than talking to the database directly.

## Status

Being built in small iterative steps. Current state:

- [x] Project skeleton — FastAPI app, SQLAlchemy models (`congressional_trades`,
      `insider_trades`, `signal_scores`, `trades`), Postgres, Docker, health
      check (`GET /health`, checks DB connectivity).
- [x] Congressional trade tracker — `POST /congress/ingest` pulls from
      House/Senate Stock Watcher (same free source Topos uses, no official
      structured API exists) and upserts into `congressional_trades`
      (deduped so repeat ingestion runs don't pile up rows);
      `GET /congress/trades` lists them, filterable by `ticker`.
- [x] Insider trade tracker — `POST /insider/ingest` pulls SEC Form 4
      filings from EDGAR (no API key required), nets out buy/sell
      direction from non-derivative transactions, and upserts into
      `insider_trades` (deduped on filing URL); `GET /insider/trades`
      lists them, filterable by `ticker`.
- [x] Signal scoring engine — `POST /scoring/run` combines
      `congressional_trades` + `insider_trades` (last 90 days by default)
      into a 0-100 score and BUY/SELL/HOLD recommendation per ticker,
      persisted to `signal_scores`; `GET /scoring/scores` lists them,
      filterable by `recommendation`. Same two principles as Topos's
      ranking engine: direction-aware scoring (agreement raises the
      score, disagreement pulls it down) and no single-source
      recommendations — a ticker needs *both* trackers to have activity,
      not just one, before it can be BUY/SELL.
- [x] Alpaca paper trading integration — `POST /execution/run` takes the
      BUY recommendations from the most recent scoring run, equal-weights
      the top N by score, and submits paper orders via Alpaca. Defaults
      to a dry run (`execute=false`); needs `execute=true` plus
      `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` to submit real paper orders.
      Every attempt is logged to `trades` regardless of outcome.
      `GET /execution/trades` lists history; `GET /execution/account` and
      `/execution/positions` proxy Alpaca's own account endpoints (400 if
      credentials aren't set).
- [x] Streamlit dashboard (`titan/dashboard/app.py`) — a pure API client
      (zero imports from `titan.app`; talks to the FastAPI backend over
      HTTP via `TITAN_API_BASE_URL` only, same as any other consumer of
      the API could). Buttons to trigger ingestion/scoring/execution,
      tables for scores (filterable by recommendation), congressional
      trades, insider trades, trade history, and live Alpaca account/
      positions once credentials are configured.

## Architecture

```
Postgres <- SQLAlchemy <- FastAPI (app/api/) <- Streamlit dashboard (HTTP only)
                              ^
                   app/collectors/ + app/signals/ + app/scoring/ + app/execution/
```

## Typical flow

```bash
curl -X POST localhost:8000/congress/ingest
curl -X POST localhost:8000/insider/ingest
curl -X POST localhost:8000/scoring/run
curl -X POST "localhost:8000/execution/run?top_n=5&account_equity=100000"
```

Or just click the corresponding buttons in the dashboard — they call the
same endpoints. None of the ingestion/scoring/execution steps run on a
schedule by themselves; nothing in Titan currently triggers this
automatically (no cron), so it's a manual (or externally scheduled)
pipeline for now.

## Setup

```bash
cd titan
cp .env.example .env   # fill in SEC_EDGAR_USER_AGENT; Alpaca keys can wait
docker compose up --build
```

Or locally (from the repo root, so both `topos` and `titan` packages resolve):

```bash
pip install -r titan/requirements.txt
DATABASE_URL=postgresql://titan:titan@localhost:5432/titan python titan/scripts/init_db.py
DATABASE_URL=postgresql://titan:titan@localhost:5432/titan uvicorn titan.app.main:app --reload
```

`GET /health` should return `{"status": "ok", "database": true}`.

In a second terminal, run the dashboard against that API:

```bash
TITAN_API_BASE_URL=http://localhost:8000 streamlit run titan/dashboard/app.py
```

Titan's Docker Compose stack maps its dashboard to host port **8502** (not
8501) and its Postgres to host port **5433** (not 5432), so it can run
alongside Topos's own `docker-compose.yml` without port collisions.
