# Titan

A local, production-oriented application: congressional trade tracker, insider
trade tracker, a signal scoring engine, Alpaca paper trading, and a Streamlit
dashboard — served through a FastAPI backend backed by PostgreSQL.

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
- [ ] Alpaca paper trading integration
- [ ] Streamlit dashboard

## Architecture

```
Postgres <- SQLAlchemy <- FastAPI (app/api/) <- Streamlit dashboard
                              ^
                   app/collectors/ + app/signals/ + app/scoring/ + app/execution/
```

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

Titan's Docker Compose stack maps its dashboard to host port **8502** (not
8501) and its Postgres to host port **5433** (not 5432), so it can run
alongside Topos's own `docker-compose.yml` without port collisions.
