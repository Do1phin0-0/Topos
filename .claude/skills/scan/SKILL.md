---
name: scan
description: Daily market scan — today's top movers, the catalysts behind them, and overall market mood. Use when the user runs /scan or asks "what's moving markets today," for a morning briefing, or for a quick read on market sentiment.
---

# Market Scan

Produce a concise, evidence-based briefing on the current trading session. This
agent's primary objective is never to recommend investments — report what is
happening and why, and let the reader draw their own conclusions.

## Steps

1. **Establish context.** Note the current date and whether markets are open,
   pre-market, or closed. Identify the relevant session (US, and any other
   market the user has been discussing).

2. **Find today's top movers.** Use web search against live financial sources
   (e.g. Yahoo Finance, MarketWatch, CNBC, Bloomberg, Finviz) to pull:
   - 3-5 largest gainers and 3-5 largest decliners in major indices
     (S&P 500 / Nasdaq / Dow, or the relevant watchlist/sector if the user has
     specified one)
   - Notable large-cap or high-volume names moving on unusual volume

3. **Identify catalysts.** For each mover, find the specific reason it's
   moving: earnings/guidance, M&A, analyst upgrade/downgrade, regulatory
   action, macro data release, product news, litigation, etc. Don't guess —
   if no clear catalyst is reported, say so rather than fabricating one.

4. **Read the macro tape.** Check for major scheduled catalysts today (Fed
   speakers/decisions, CPI/PCE/jobs data, major earnings) and broad market
   indicators (VIX level, breadth/advance-decline, sector rotation) to
   characterize overall mood (risk-on / risk-off / mixed / choppy).

5. **Report back** in this structure:
   - **Market mood** — one or two sentences on the overall tone and why
   - **Top movers** — bullet list: `TICKER  ±%  — catalyst (source/date)`
   - **What's driving the day** — key scheduled macro/earnings catalysts
   - A closing line noting this is informational market context, not a
     recommendation to buy, sell, or hold anything.

## Notes

- Always cite where a data point or catalyst came from (source name), and
  flag the timestamp/staleness of the data if markets are closed or the
  search results are dated.
- If live web search isn't available in the current environment, say so
  explicitly rather than presenting stale or fabricated numbers as current.
