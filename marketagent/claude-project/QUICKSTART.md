# Claude.ai Project Setup — Market Intelligence Agent

This sets up a persistent Market Intelligence Agent inside Claude.ai Projects.
No installation, no API key management, no terminal — just open Claude and start typing commands.

---

## Setup (2 minutes)

### Step 1 — Create a new Project
1. Go to [claude.ai](https://claude.ai)
2. Click **Projects** in the left sidebar
3. Click **+ New Project**
4. Name it: `Market Intelligence Agent`

### Step 2 — Add custom instructions
1. Inside your new project, click **Project instructions** (or the gear icon)
2. Open `INSTRUCTIONS.md` from this folder
3. Copy everything **below** the first line (`> Paste everything below...`)
4. Paste it into the instructions field
5. Save

### Step 3 — Start your first conversation
Click **New conversation** inside the project and try:

```
My watchlist: NVDA, BTC, SOFI

/scan
```

---

## How to Use It

### Starting a session
Tell it your watchlist at the beginning of each conversation:
```
My watchlist is NVDA, BTC, SOFI, AAPL
```

Or build it up:
```
/watch add NVDA
/watch add BTC
```

### Core workflow
```
/scan                    ← what's moving today?
/analyze NVDA            ← should I be interested?
/compare NVDA AMD        ← which looks better?
/opportunities           ← what did I miss?
/watch                   ← how's my watchlist doing?
/why BTC                 ← why is Bitcoin up today?
/calendar                ← what's coming up?
```

### Getting deeper
```
/stock SOFI              ← full fundamentals breakdown
/coin PEPE               ← crypto deep-dive
/risk NVDA               ← what could go wrong?
/sentiment TSLA          ← what's the crowd thinking?
/bubble                  ← what looks dangerously overheated?
```

---

## Differences vs. CLI Version

| Feature | CLI (`agent.py`) | Claude.ai Project |
|---------|-----------------|-------------------|
| Real-time prices | ✅ yfinance (exact price) | ✅ Web search (may be approximate) |
| Insider trades | ✅ Exact Form 4 data | ✅ Web search results |
| Persistent memory | ✅ `memory.json` (thesis history) | ✅ Project memory (Pro/Team plans) |
| Watchlist | ✅ `watchlist.json` | Tell Claude at session start |
| Setup | Install Python + deps | None |
| Access | Terminal only | Web, mobile, desktop |
| Sharing | Clone repo | Invite to project |

---

## Tips

**Thesis tracking** — If you've analyzed an asset before, tell Claude:
```
Last time I looked at NVDA (Jan 10) I was Moderately Bullish because of AI demand.
What's changed since then? /analyze NVDA
```

**Saving your watchlist** — At the end of a session, ask:
```
Summarize my current watchlist and thesis for each asset so I can paste it next time.
```

**Team use** — On Claude.ai Team or Pro plans, you can invite colleagues to the same project so everyone shares the same agent instructions and knowledge files.

**Upload knowledge** — You can upload files to the project (earnings reports, 10-Ks, whitepapers) and the agent will reference them when you ask about those assets.

---

## Troubleshooting

**Agent not following commands?**
Make sure the instructions are saved in Project Settings, not in a chat message.

**Responses too short?**
Ask: "Please give a full analysis using the Standard Analysis Template"

**Want more data sources?**
Upload relevant PDFs (earnings reports, analyst research) to the project knowledge base.
