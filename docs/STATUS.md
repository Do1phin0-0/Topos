# Where Topos stands — session checkpoint (2026-08-05)

Read this first when resuming. It is the whole picture: what this
project is, what question we are answering right now, exactly where we
stopped, and the precise next commands.

## What Topos is

A personal investment-intelligence platform: it collects signals from
public sources (congressional trade disclosures, SEC Form 4 insider
trades, 8-K earnings timing, 13F institutional moves, news/technical
sentiment), aggregates them per ticker into a 0–100 score with a
BUY/SELL/HOLD recommendation, and — long term, after validation and an
explicit opt-in — is meant to trade via Alpaca, paper first. The owner's
stated end goal: an auto-trading bot, reached gradually and never
silently.

## The current objective (nothing else until this is done)

**Determine whether the scoring model has predictive power.** Six parts:
congressional backfill · per-source signal validation · score-bucket
performance · score↔forward-return correlation · multi-source agreement
vs single source · a recommendation on weights. Constraint from the
owner: **no new signals, no UI work, until validation is complete.**

## What is built and pushed (branch `claude/topos-repo-purpose-xsj7u0`)

Everything needed for validation exists and is tested (198 passing):

- **Congressional collector rebuilt from the ground truth.** The House
  and Senate Stock Watcher mirrors died (S3 AccessDenied for everyone,
  Aug 2026). Topos now downloads the House Clerk's yearly archive and
  parses each Periodic Transaction Report PDF itself
  (`topos/collectors/house_clerk.py` + `ptr_parser.py`). Verified on
  real filings: ~11,400 transactions parsed from 2024–2026, zero
  unreadable filings, and every dropped row confirmed to be bonds /
  property / funds (correct exclusions). Senate is dark — no bulk
  archive exists. Multi-source conclusions must carry that caveat.
- **Price collector is a fallback chain** (`topos/collectors/prices.py`):
  Stooq, then Yahoo chart API, both key-free; a host that won't connect
  three times in a row is benched for the run. Built because Stooq
  started 404ing on real symbols mid-backfill.
- **Ranking replay** (`scripts/replay_rankings.py`): writes point-in-time
  rankings every 28 days across signal history, so score validation has
  a sample now instead of accruing one live over months. Snapshots never
  see their own future; staleness is measured against the snapshot date;
  re-runs replace their own rows.
- **Research report** (`scripts/research_report.py`): all six validation
  sections, sample-size guardrails (no inference below n=30, provisional
  below n=100), permutation tests, and a legacy-vs-current formula split.
- **SQLite support end to end**, so none of this needs Postgres, Docker,
  or any network beyond the data fetches themselves.

## The owner's machine — hard-won environment facts

- **Local database:** `$env:DATABASE_URL = "sqlite:///topos.db"` in the
  project folder. Must be re-set in every new PowerShell window,
  otherwise scripts silently point at Render again.
- **VPN ON → GitHub works** (git pull needs it) but stooq.com DNS broke
  under it. **VPN OFF → outbound 5432 is blocked** by the home network
  (only matters for Render, which validation no longer uses).
  Practical rule: *pull with VPN on, fetch prices with VPN off.*
- The local `topos.db` already holds **10,196 signals**. It has **zero
  price bars and zero rankings** — that is the unfinished part.
- House Clerk PDFs are cached in `.cache/house_clerk/` — re-parses are
  free, nothing re-downloads.

## Where we stopped

The owner ran `git pull` (VPN state unknown at that moment) and it
failed; session ended there. The three data-producing commands below
have not run yet on the latest code.

## Exact resume sequence

```powershell
# 1. VPN ON for the pull:
git pull origin claude/topos-repo-purpose-xsj7u0

# 2. Same window, every time:
$env:DATABASE_URL = "sqlite:///topos.db"

# 3. VPN OFF for the fetches (15–25 min; watch "M bars stored" climb —
#    if it is still 0 after ~50 tickers, stop and report the warnings):
py scripts/backfill_congress.py --since 2024-01-01 --max-tickers 0

# 4. Fast:
py scripts/replay_rankings.py --since 2024-01-01
py scripts/research_report.py --output report.md
```

Then read `report.md` — that is the deliverable this whole phase exists
to produce.

## If prices still store zero bars

Both free sources are then blocked from that network. Next move (already
agreed in principle): wire the Alpaca market-data API as a third source —
the owner has an Alpaca account; keys go in `.env` as `ALPACA_API_KEY` /
`ALPACA_SECRET_KEY`.

## Open items beyond validation (parked, in order of urgency)

1. **Render database password is leaked** (pasted in chat) and rotation
   is unconfirmed. The DB also appears reachable from any IP. Rotate in
   the Render dashboard; update `DATABASE_URL` env var on the dashboard
   service afterward.
2. PR #3 is open and unmerged; this branch has moved far past it.
3. Bloomberg as a source: parked — conflicts with the owner's own
   "no new signals until validation" rule, and needs a Terminal license.
4. Dashboard redesign: explicitly deferred until validation completes.
5. Senate coverage (eFD scraper) if congressional signal proves out.
