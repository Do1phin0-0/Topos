# Where Topos stands — session checkpoint

> **VALIDATION COMPLETE AND CONFIRMED — 2026-08-07, RE-TESTED 2026-08-18.**
> See `docs/VALIDATION_RESULTS.md`. The scoring model does not predict
> returns. Both known holes were then closed — price coverage repaired
> from 452 to 1,254 tickers, and congressional signals re-dated by
> disclosure — and the verdict got *cleaner*: score-return correlation
> fell to rho=+0.012 at p=0.086 (no longer significant at all), and the
> multi-source underperformance finding vanished (p=0.015 -> p=0.057),
> having been an artifact of the biased sample. Congress standalone is
> -0.04% transaction-dated, +0.13% disclosure-dated; Form 4 is -0.34%.
> All indistinguishable from zero against SPY.
>
> Five price-action sources (gap, relative volume, 20/60-day momentum,
> 5-day reversal) and a flat 10bps transaction-cost model were added and
> tested on 2026-08-18. They didn't rescue anything: all five cluster
> near zero net of cost, the score correlation got even flatter
> (rho=-0.000, p=0.940, n=40,319), and a large "multi-source
> underperforms" result turned out to be a second, structurally distinct
> artifact — see "Price-action signals — 2026-08-18" in
> `docs/VALIDATION_RESULTS.md`.
>
> Nothing left to rescue. The open question is what Topos becomes, not
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

## What is built and pushed (branch `claude/topos-repo-purpose-xsj7u0`, merged to `main`)

281 tests passing.

- **Price-action signals** (`topos/signals/price_action.py`) — gap,
  relative volume, 20/60-day momentum, 5-day reversal, computed purely
  from stored bars, no network call. Backfilled via
  `scripts/backfill_price_signals.py`. Tested 2026-08-18: no edge, see
  `docs/VALIDATION_RESULTS.md`.
- **Flat transaction-cost model** (`apply_cost()` in
  `topos/backtesting/prices.py`, `--cost-bps`/`--gross` on
  `research_report.py`) — 10bps round-trip by default, applied strictly
  after direction adjustment.

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
- `topos.db` holds **~58,000 signals, ~21,000 rankings, 1,254 tickers
  with price history** (963k+ bars) plus SPY. Several hundred MB.
  Congressional signals are currently **disclosure-dated**; switching
  basis rebuilds them from cache in seconds.
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

1. PR #3 merged to `main` on 2026-08-18. A separate, unrelated PR #4
   (`claude/market-signals-platform-uz6v0b`) is open, built on the old
   pre-merge `main`, and proposes enabling live paper trading
   (`--execute` on the Render cron). It was built without reference to
   any of the validation work above and should not be merged as-is —
   see the PR itself before touching it.
2. Dashboard redesign — was deferred pending validation. Validation is
   done, but there is now nothing worth putting on a dashboard.
3. `multi_vs_single_source` (`topos/backtesting/research.py`) has a
   structural design flaw, not just a sampling problem: single-source
   opportunities can only ever be recommendation HOLD (per
   `attribution.py`'s 2-source-minimum rule for BUY/SELL), so they get no
   directional sign-adjustment while multi-source opportunities do. The
   comparison has never actually tested "does agreement help" — see
   "Price-action signals — 2026-08-18" in `docs/VALIDATION_RESULTS.md`.
   Needs a redesign (grade single-source on its own signal's direction,
   or compare exactly-2-source vs 3+-source cohorts instead) before this
   section of the report should be trusted.
4. Untested sources: earnings, 13F, news, sentiment. Note that adding
   sources is what produced two separate false "multi-source" findings
   now — treat any future one with the same suspicion.
