# Topos — Market Intelligence AI Agent

A command-driven market research platform powered by Claude AI. Tracks stocks and crypto in real time, builds evidence-based bull/bear theses, remembers every analysis, and lets you grow it with custom commands.

> **Disclaimer:** For research and education only. Not a financial advisor. Never guarantees returns. Always do your own research.

---

## How It Works

```
You type a command
        │
        ▼
┌───────────────────────────────────────┐
│  1. Live Data Fetch (instant)         │
│     yfinance  → price, P/E, volume,   │
│                 insider trades        │
│     CoinGecko → crypto price, cap,    │
│                 supply, ATH delta     │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  2. Memory Injection                  │
│     Loads prior thesis for this       │
│     asset (if any) from memory.json   │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  3. Claude AI (claude-sonnet-4-6)     │
│     Web search → news, sentiment,     │
│     filings, analyst ratings          │
│     + structured data from step 1     │
│     + prior thesis from step 2        │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  4. Response + Auto-Save              │
│     Formatted analysis in terminal    │
│     Thesis saved to memory.json       │
│     for future comparison             │
└───────────────────────────────────────┘
```

The agent runs an **agentic loop** — it can trigger multiple web searches in one response before synthesizing its answer. Structured data (prices, fundamentals, insiders) is fetched first and injected as ground truth, so Claude doesn't have to guess at numbers.

---

## Setup

**Requirements:** Python 3.10+, an [Anthropic API key](https://console.anthropic.com)

```bash
# Clone and enter the project
cd marketagent/market-agent

# Install dependencies
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=your_key_here    # Mac/Linux
$env:ANTHROPIC_API_KEY="your_key_here"   # Windows PowerShell

# Run
python agent.py
```

---

## Commands

### Market Overview

| Command | What it does |
|---------|-------------|
| `/scan` | Top movers (stocks + crypto), volume spikes, sector trends, fear/greed. Pre-fetches SPY/QQQ/VIX/BTC/ETH snapshot. |
| `/news` | 5–7 most market-moving stories right now, each tagged with affected tickers |
| `/opportunities` | Scans for unusual volume, insider buys (Form 4), ETF filings, earnings surprises, whale moves |
| `/calendar` | Upcoming earnings (2 weeks), Fed meetings, CPI/jobs/PPI, IPOs, options expiry, crypto events |
| `/bubble` | Assets with parabolic moves, extreme retail enthusiasm, or stretched valuations |

---

### Single Asset Analysis

| Command | What it does |
|---------|-------------|
| `/stock TICKER` | Deep stock analysis — price, fundamentals, news, bull/bear, confidence score |
| `/coin SYMBOL` | Crypto analysis — price, on-chain metrics, whale activity, sentiment |
| `/analyze ASSET` | **Flagship.** Full "Would I Buy?" report (see below) |
| `/risk ASSET` | Risk factors ranked High / Medium / Low |
| `/sentiment ASSET` | Social sentiment, options flow (put/call), short interest, institutional ownership |
| `/why ASSET` | What's driving price action specifically TODAY |
| `/compare A B` | Side-by-side comparison of two assets |

---

### Watchlist

| Command | What it does |
|---------|-------------|
| `/watch add TICKER` | Add to watchlist |
| `/watch remove TICKER` | Remove from watchlist |
| `/watch` | Show each watchlist asset with latest news and whether your thesis is **Strengthening / Weakening / Unchanged** vs. prior analysis |

---

### Memory & Learning

| Command | What it does |
|---------|-------------|
| `/history ASSET` | Timeline of every prior analysis stored for that asset |
| `/learn` | Identifies patterns in your watchlist and suggests new metrics to track |
| `/gaps` | Finds coverage gaps — sectors/geographies not watched, stale analyses |

---

### Custom Skills

| Command | What it does |
|---------|-------------|
| `/skills` | Lists all built-in commands plus any custom skills you've registered |
| `/buildskill NAME` | Define a new analysis module — the agent asks for purpose, data sources, and output format, then registers it permanently |
| `/metrics` | Memory stats: assets tracked, analyses stored, custom skills registered |

---

## Sample Output

### `/analyze NVDA`

```
WOULD I BUY NVDA?

Current Stance: Moderately Bullish

Supporting Evidence:
✅ Revenue grew 122% YoY driven by data center AI demand (Q3 2025 earnings)
✅ Blackwell GPU shipments accelerating — customers include Microsoft, Google, Meta
✅ Analyst consensus target $160 (18% upside from current $135)

Concerns:
⚠️ Valuation stretched at 48x trailing P/E vs sector average of 28x
⚠️ Export restrictions to China create ~$15B revenue risk annually
⚠️ AMD MI300X gaining ground in enterprise AI deployments

Bull Thesis:
AI infrastructure buildout is in early innings. Every hyperscaler is
racing to deploy GPU clusters, and NVDA's CUDA ecosystem lock-in makes
displacement difficult even at premium prices.

Bear Thesis:
At this valuation, any guidance miss or macro slowdown would cause a
significant de-rating. China export rules could tighten further.

Key Catalysts:
- Next earnings: Feb 26 (consensus EPS $0.84)
- CES January — potential Blackwell roadmap update
- Any new China export rule changes

Conviction Score: 7/10
Strong fundamentals but valuation leaves little room for error.

What Would Change My Mind:
Bearish: Earnings miss + guidance cut / AMD wins major hyperscaler contract
Bullish: Beats and raises + regulatory clarity on China exports

⚠️ This is market research, not investment advice.
```

---

### `/scan`

```
TODAY'S MOVERS

Stocks:
NVDA  +4.2%  — Blackwell demand commentary from CEO
TSLA  -3.1%  — Delivery miss vs. estimates
SOFI  +8.4%  — Fed rate cut accelerates

Crypto:
BTC   +2.1%  — ETF inflows $480M (3-day streak)
PEPE  +18%   — Influencer attention + low float
SOL   +5.3%  — DEX volume record

Potential Catalysts:
Fed speech Thursday — Powell testimony to Senate Banking
CPI Friday — consensus +2.8% YoY

Market Mood: Cautiously Bullish
VIX: 14.2 (low fear)
```

---

### `/watch`

```
NVDA — Thesis: Strengthening
Latest: Blackwell shipments beat expectations, raising 2025 estimates.

BTC — Thesis: Unchanged
Latest: ETF inflows positive but price range-bound near ATH.

SOFI — Thesis: Weakening
Latest: Competition from traditional banks increasing in personal loans.
```

---

### `/compare NVDA AMD`

```
COMPARISON: NVDA vs AMD

                NVDA              AMD
Price trend:    Uptrend (+42% 6M) Flat (+4% 6M)
News:           Very positive     Mixed
Bull case:      AI dominance      MI300X market share
Bear case:      Valuation, China  Execution risk
Risk level:     6/10              5/10
Conviction:     7/10              5/10

Verdict: NVDA has the stronger near-term catalyst pipeline but AMD
offers a lower-risk entry at a more reasonable valuation if you
believe the AI GPU market is large enough for two players.
```

---

### Thesis Evolution (automatic on repeated `/analyze`)

Once you've analyzed an asset before, subsequent runs show how the thesis drifted:

```
THESIS EVOLUTION
Prior stance (2025-01-10): Neutral — waiting for earnings clarity
Current stance: Moderately Bullish
What changed: Q4 beat by 12%, guidance raised, short interest dropped from 8% to 3%
```

---

## Data Sources

| Source | What it provides | Cost |
|--------|-----------------|------|
| **yfinance** | Price, P/E, EPS, revenue, 52W range, analyst targets, short float, beta, sector, insider transactions | Free |
| **CoinGecko** | Crypto price, 24h/7d/30d change, market cap, rank, volume, ATH, supply, categories | Free (public API) |
| **Claude web search** | News, sentiment, analyst commentary, SEC filings, social signals, earnings transcripts | Per API call |

The data fetch happens **before** Claude starts thinking — so the model receives a structured block like this:

```
[LIVE STOCK DATA — NVDA — Jun 29 2026 16:15 UTC]
Price: $135.58 (+2.40% today)
Volume: 42.10M shares (avg: 38.50M) — 1.1x average
Market Cap: $3.32T
P/E: 48.2 | Fwd P/E: 34.1 | EPS: $2.81
Revenue (TTM): $44.10B
52W Range: $86.11 — $153.13 (at 89% of 52W high)
Analyst Target: $160.00 (+18% upside)
Short: 0.9% of float | Beta: 1.72
Sector: Technology — Semiconductors

Recent Insider Activity:
  • Jensen Huang: Sale 120,000 shares $15.70M on 2026-06-15
```

...and then uses web search on top of that for news and qualitative context.

---

## Persistent Memory

Every analysis command (`/analyze`, `/stock`, `/coin`, `/risk`, `/sentiment`) is automatically saved to `memory.json` per asset, keeping the last 10 entries. This enables:

- **Thesis drift detection** — `/analyze` automatically compares against last run
- **`/watch` context** — agent knows what you believed last week
- **`/history ASSET`** — full timeline of how your view evolved
- **Custom skills** — `/buildskill` registrations persist across sessions

---

## Custom Skills (`/buildskill`)

Teach the agent new analysis patterns at runtime:

```
→ /buildskill etfflow

Agent: Let's define this skill.
  Purpose: Track ETF inflow/outflow trends for an asset
  Data sources: ETF.com, Bloomberg ETF data, news search
  Output format: Net flows 7-day, top ETFs holding the asset, trend

SKILL REGISTERED: /etfflow
You can now use /etfflow TICKER in this session (and future sessions).
```

Registered skills appear in `/skills` and persist in `memory.json`.

---

## Project Structure

```
marketagent/market-agent/
├── agent.py          — Main loop, agentic web-search, memory + data injection
├── commands.py       — System prompt (7,700+ chars) and command registry
├── data.py           — yfinance + CoinGecko fetchers and formatters
├── memory.py         — Persistent analysis history and custom skill storage
├── watchlist.py      — Local JSON watchlist management
├── display.py        — Terminal formatting (rich library)
├── requirements.txt  — anthropic, rich, yfinance, requests
└── .gitignore        — Excludes watchlist.json, memory.json, __pycache__

Runtime files (auto-created, gitignored):
  watchlist.json      — your watched assets and add dates
  memory.json         — stored analyses and registered skills
```

---

## Extending the Agent

### Add a new built-in command
1. Add it to `COMMAND_REGISTRY` in `commands.py`
2. Describe its behavior in `build_system_prompt()` in `commands.py`
3. If it needs local handling (no AI needed), add a case in `handle_local_commands()` in `agent.py`
4. If it should auto-fetch market data, add it to the `hint_map` in `data.py`

### Add a new data source
1. Add a fetch function in `data.py` (follow the pattern of `fetch_stock` or `fetch_crypto`)
2. Add a formatter function (returns a plain-text block)
3. Call it from `build_data_context()` for the relevant commands

### Register a custom command at runtime
```
/buildskill insiderflow
```
No code changes needed — the agent defines the skill and it persists in `memory.json`.

---

## Ideas for Future Extensions

- **`/alert NVDA > 150`** — background monitor with desktop/email notification
- **`/digest`** — scheduled daily scan + watch summary written to `digest.md`
- **Web UI** — Flask + HTMX dashboard with streaming responses
- **More data sources** — SEC EDGAR (Form 4, 8-K), Alpha Vantage, Unusual Whales
- **Portfolio mode** — track actual positions with cost basis and P&L context
