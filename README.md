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
| SEC 13F-HR (hedge fund holdings) | Collector wired, extraction is a follow-up (needs prior-quarter diffing to be meaningful) |
| Congressional trade disclosures | Not started — no free official API (would need QuiverQuant or a scraper) |
| Earnings reports | Not started |
| News sentiment | Not started — needs a provider (NewsAPI, Finnhub, etc.) |
| Technical indicators | Not started |
| Options activity | Not started |
| Analyst revisions | Not started |
| Social sentiment | Not started |

## Current MVP scope

This is a thin vertical slice, not the full system described above:

- Form 4 filings are pulled live from SEC EDGAR (no API key required) and
  scored into `Signal` records with a confidence heuristic based on insider
  role and transaction size.
- The ranking engine aggregates signals per ticker (source diversity boosts
  score).
- The portfolio decision engine and risk layer run on that ranked output
  (simple top-N equal-weight + position/exposure limits).
- The Alpaca execution layer defaults to **dry run** — it prints what it
  would trade but submits nothing unless you pass `--execute`, and even then
  it only talks to Alpaca's **paper trading** endpoint.
- The dashboard is a read-only Streamlit view over the Postgres tables.

Everything else in the architecture diagram (congressional trades, options
flow, sentiment, etc.) is documented intent, not implemented yet — see the
table above.

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

## Disclaimer

This is a personal research tool. Nothing it outputs is investment advice.
It runs against Alpaca's paper trading endpoint only until you deliberately
supply live credentials and pass `--execute`.
