# Market Intelligence AI Agent

A command-driven market intelligence platform powered by Claude with real-time web search and persistent memory.

> **Disclaimer:** This tool is for research and education only. It is not a financial advisor and does not provide investment recommendations. Always do your own research.

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key
```bash
# Mac/Linux
export ANTHROPIC_API_KEY=your_key_here

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY="your_key_here"
```

Get your key at: https://console.anthropic.com

### 3. Run the agent
```bash
python agent.py
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/skills` | All analysis modules (built-in + custom) |
| `/scan` | Rapid market-wide summary — movers, volume, catalysts |
| `/news` | Top 5-7 market-moving stories with affected tickers |
| `/stock TICKER` | Deep stock analysis (e.g. `/stock AAPL`) |
| `/coin SYMBOL` | Crypto analysis with on-chain + sentiment (e.g. `/coin BTC`) |
| `/analyze ASSET` | Full "Would I Buy?" report with conviction score |
| `/compare A B` | Side-by-side analysis of two assets |
| `/watch` | Watchlist with thesis change vs. prior analysis |
| `/watch add TICKER` | Add to watchlist |
| `/watch remove TICKER` | Remove from watchlist |
| `/opportunities` | Unusual volume, insider buys, ETF filings, whale moves |
| `/calendar` | Earnings, Fed events, CPI, IPOs, options expiry |
| `/risk ASSET` | Risk factors ranked by severity |
| `/sentiment ASSET` | Social sentiment, options flow, short interest, institutions |
| `/why ASSET` | Why is this moving TODAY? Concrete catalyst breakdown |
| `/bubble` | Speculative bubble scanner |
| `/history ASSET` | Prior analyses stored in memory for an asset |
| `/learn` | Detect patterns and suggest new metrics |
| `/gaps` | Research coverage gaps in your watchlist |
| `/buildskill NAME` | Define and register a new custom analysis module |
| `/metrics` | Memory stats and system health |

---

## Key Features

### Persistent Memory
Every `/analyze`, `/stock`, `/coin`, `/risk`, and `/sentiment` run is saved to `memory.json`. On subsequent runs against the same asset, the agent automatically loads the prior thesis and tells you what changed:

```
THESIS EVOLUTION
Prior stance (2025-01-10): Moderately Bullish
Current stance: Strongly Bullish
What changed: Earnings beat + ETF approval
```

### "Would I Buy?" Reports (`/analyze`)
The flagship command builds a full research thesis with evidence-backed bull and bear cases, a conviction score, and explicit conditions that would change the view — not a buy/sell recommendation.

### Watchlist with Thesis Tracking (`/watch`)
The agent compares current news against what it previously believed about each watched asset and flags whether each thesis is strengthening, weakening, or unchanged.

### Custom Skills (`/buildskill`)
Register new analysis modules on the fly:
```
/buildskill insider
```
The agent defines the skill, registers it in memory, and it persists across sessions.

### Multi-turn Web Search
The agentic loop properly handles Anthropic's `web_search_20250305` tool — searches run in real time before the agent synthesizes its response.

---

## Project Structure

```
market-agent/
├── agent.py          # Main loop, agentic web-search, memory integration
├── commands.py       # System prompt and command registry
├── memory.py         # Persistent analysis history and custom skill storage
├── watchlist.py      # Local JSON watchlist management
├── display.py        # Terminal formatting (rich)
├── requirements.txt  # Dependencies
├── .gitignore        # Excludes watchlist.json, memory.json, __pycache__
└── README.md
```

Runtime files (auto-created, gitignored):
- `watchlist.json` — your watched assets
- `memory.json` — stored analyses and custom skills

---

## Extending the Agent

### Add a built-in command
1. Add it to `COMMAND_REGISTRY` in `commands.py`
2. Add behavior instructions to `build_system_prompt()` in `commands.py`
3. If it needs local handling (no AI), add a case in `handle_local_commands()` in `agent.py`

### Register a custom command at runtime
```
/buildskill insiderflow
```
The agent will ask what data to pull and what format to use, then register it in memory permanently.

---

## Example Session

```
→ /scan
→ /analyze NVDA
→ /analyze BTC
→ /opportunities
→ /watch add NVDA
→ /watch add BTC
→ /watch
→ /compare NVDA AMD
→ /why PEPE
→ /buildskill etfflow
→ /skills
→ /history NVDA
```
