# Where Topos stands — session checkpoint

> **VALIDATION COMPLETE — 2026-08-07. See `docs/VALIDATION_RESULTS.md`.**
> The scoring model has no tradeable predictive power. Score/return
> Spearman +0.020 (explains 0.04% of variation) on 11,348 observations
> across two independent sources, measured against SPY. Multi-source
> agreement *underperformed* single-source by 1.23% (p=0.015) —
> the founding assumption, contradicted. Both sources are individually
> negative vs the market. No weight tuning, no trading. The freeze on
> new work is lifted; the open question is now what to build next, not
> whether this model works.

## What Topos is

A personal investment-intelligence platform: it collects signals from
public sources (congressional trade disclosures, SEC Form 4 insider
trades, 8-K earnings timing, 13F institutional moves, news/technical
sentiment), aggregates them per ticker into a 0–100 score with a
BUY/SELL/HOLD recommendation, and — long term, after validation and an
explicit opt-in — is meant to trade via Alpaca, paper first. The owner's
stated end goal: an auto-trading bot, reached gradually and never
silently.

## The objective, now answered

**Did the scoring model have predictive power?** Six parts: congressional
backfill · per-source validation · score-bucket performance ·
score-return correlation · multi-source agreement · a weights
recommendation. All six ran. All six are in
`docs/VALIDATION_RESULTS.md`. The answer is no.

## What is built and pushed (branch `claude/topos-repo-purpose-xsj7u0`)

242 tests passing.

- **Congressional collector** (`topos/collectors/house_clerk.py` +
  `ptr_parser.py`) — the House and Senate Stock Watcher mirrors died
  (S3 AccessDenied, Aug 2026), so this downloads the House Clerk's yearly
  archive and parses each PTR PDF. ~11,400 transactions from 2024-2026,
  zero unreadable filings. Senate is dark: no bulk archive exists.
- **Form 4 collector** (`topos/collectors/edgar_archive.py`) — EDGAR
  quarterly full-index, filtered by CIK before anything downloads because
  ~250k Form 4s are filed per year. 44,435 signals parsed.
- **Price collector is a fallback chain** (`topos/collectors/prices.py`):
  Stooq, then Yahoo, both key-free; a host that will not connect three
  times running is benched for the rest of the run.
- **Benchmark-relative returns** — `--benchmark SPY` by default. An
  unmeasurable benchmark leg yields None rather than falling back to the
  absolute return, which would relabel market drift as skill.
- **Ranking replay** (`scripts/replay_rankings.py`) — point-in-time
  snapshots every 28 days across signal history. Snapshots never see
  their own future; re-runs replace their own rows.
- **Research report** (`scripts/research_report.py`) — six sections,
  permutation tests, sample-size floors (n>=30 to infer, n>=100 to be
  non-provisional) *and* an effect-size floor (|rho|>=0.05 to be
  actionable), plus a monotonicity check on the bucket table.
- **SQLite end to end** — no Postgres, Docker or network needed for
  research.

## The owner's machine

- **Local database:** `$env:DATABASE_URL = "sqlite:///topos.db"`, must be
  re-set in every new PowerShell window or scripts point at Render again.
- **VPN ON → GitHub works; VPN OFF → price fetches work.** Outbound 5432
  is blocked without the VPN (irrelevant now that research is local), and
  stooq.com DNS broke *under* it. Rule: pull with VPN on, fetch with it
  off.
- `topos.db` holds **58,327 signals, 21,122 rankings, 452 tickers with
  price history** plus SPY. Roughly 92 MB.
- Downloads are cached in `.cache/house_clerk/` and `.cache/edgar/` —
  re-parsing is free, nothing re-downloads.
- **PowerShell 5 mis-renders the UTF-8 report.** Use
  `Get-Content report.md -Encoding UTF8`, or just open it in an editor.

## Re-running the analysis

```powershell
$env:DATABASE_URL = "sqlite:///topos.db"
py scripts/replay_rankings.py --since 2024-01-01   # only after new signals
py scripts/research_report.py --output report.md
py scripts/research_report.py --horizon 60 --output report-60d.md
py scripts/research_report.py --absolute --output report-abs.md
```

## Open items

1. **Render database password is leaked** (pasted in chat) and rotation is
   unconfirmed. Render offers no password reset for Postgres, so the
   practical fix is to delete that database — everything in it is
   superseded by the local file. Its only consumer is a dashboard showing
   stale numbers.
2. PR #3 is open and unmerged; this branch has moved far past it.
3. Dashboard redesign — was deferred pending validation. Validation is
   done, but there is now nothing worth putting on a dashboard.
4. Untested sources: earnings, 13F, news, technical, sentiment. Note that
   adding a second source is what produced the multi-source finding, and
   it was negative.
