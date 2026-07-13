---
name: watch
description: Status check on the user's watchlist — price moves, news, and anything actionable since the last check. Use when the user runs /watch.
---

# Watch

## Steps

1. Establish the watchlist. If it hasn't been stated in this
   conversation, ask the user which assets to track — this agent has no
   persistent storage across sessions, so the watchlist lives in the
   conversation.
2. For each asset, pull the latest price/move and any news since the
   last check-in.
3. Flag anything material: earnings surprises, large price moves,
   analyst actions, or macro events touching the name.
4. Present as a compact table: Asset | Price | % change | Notable news.
   Mark quiet names explicitly rather than omitting them.

## Notes

- This is a status update, not a signal to act on any position.
