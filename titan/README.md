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
- [ ] Insider trade tracker
- [ ] Signal scoring engine
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
