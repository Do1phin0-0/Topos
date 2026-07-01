---
description: Daily market suggestions based on recent news and current prices
---

Follow `PROMPTS/market-suggestions.md` to build today's suggestions. Optional focus:
$ARGUMENTS (a specific market, sector, or platform, e.g. Kalshi/Polymarket/a stock) — if
empty, cover whatever's currently newsworthy.

Steps:

1. Use `WebSearch` to find recent news/catalysts and any published prices/odds tied to
   them.
2. For each one worth surfacing, pull the current market-implied probability/price.
3. Output using the format in `PROMPTS/market-suggestions.md`: what happened,
   contract/question, suggestion, why.
4. Apply the disclaimer throughout, and don't manufacture picks just to fill out a list —
   fewer (or zero) genuine suggestions beats padded ones.
