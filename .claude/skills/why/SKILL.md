---
name: why
description: Explains why an asset is moving the way it has recently. Use when the user runs /why ASSET.
---

# Why

## Steps

1. Establish the timeframe — default to today's session unless the user
   means a longer move (e.g. "why is it up this month").
2. Pull the price action for that window.
3. Search news, filings, and analyst notes for the specific catalyst(s)
   behind the move.
4. If no clear catalyst turns up, say so explicitly ("no specific news
   found; may be sector-wide or technical flow") rather than fabricating
   a reason.

## Output

- Move: ±% over the timeframe
- Catalyst(s), with source
- Context: isolated to this asset, or part of a sector-wide/market-wide
  move?
