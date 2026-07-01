---
description: Daily market suggestions based on recent news and current prices
---

Follow `PROMPTS/market-suggestions.md` to build today's suggestions. Optional focus:
$ARGUMENTS (a specific market, sector, or platform, e.g. Kalshi/Polymarket/a stock) — if
empty, cover whatever's currently newsworthy.

Steps:

1. Read `PROMPTS/lessons.md` and note anything relevant to today's scope — apply it below
   rather than repeating a past mistake.
2. Use `WebSearch` to find recent news/catalysts and any published prices/odds tied to
   them.
3. For each one worth surfacing, pull the current market-implied probability/price.
4. Output using the format in `PROMPTS/market-suggestions.md`: what happened,
   contract/question, suggestion, why.
5. Apply the disclaimer throughout, and don't manufacture picks just to fill out a list —
   fewer (or zero) genuine suggestions beats padded ones.
6. Suggest `/log-pick` for any suggestion worth tracking for calibration later.
