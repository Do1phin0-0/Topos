---
description: Daily cross-sport suggestions based on recent results and current odds
---

Follow `PROMPTS/sports-suggestions.md` to build today's suggestions. Optional focus:
$ARGUMENTS (a specific sport, league, or team) — if empty, cover whatever major
sports/leagues had games in roughly the last 24-48 hours (e.g. an ongoing tournament),
unless told otherwise.

Steps:

1. Use `WebSearch` to find last night's / recent notable results and standout performers.
2. For each one worth surfacing, find their next scheduled game and current relevant
   odds/props.
3. Output using the format in `PROMPTS/sports-suggestions.md`: what happened, next game,
   suggestion, why.
4. Apply the responsible-gambling guidance throughout, and don't manufacture picks just to
   fill out a list — fewer (or zero) genuine suggestions beats padded ones.
