---
description: Sports/betting-line analysis using the sports intelligence agent prompt
---

Follow the sports intelligence agent prompt in `PROMPTS/sports.md` to answer this request: $ARGUMENTS

Steps:

1. Read `PROMPTS/lessons.md` and note anything relevant to this matchup/prop/sport — apply
   it in the analysis below rather than repeating a past mistake.
2. Identify the specific player/team, matchup, and prop or line being asked about. If it's
   ambiguous (which game, which market), ask before proceeding.
3. Use `WebSearch` to find current odds, props, and recent form/stats — do not answer from
   memorized data, since it may be stale or wrong. Cite sources.
4. Answer using the required format from `PROMPTS/sports.md`: headline read, key factors,
   your probability estimate, market-implied probability, edge verdict, confidence level.
5. Always close with a **Suggestion** section: if the data supports a better-fitting
   alternative (a different number, side, or line that matches recent form or has better
   implied value), name it plainly and say why. If the original ask already looks
   well-supported, say that instead of manufacturing an alternative.
6. Apply the responsible-gambling guidance from `PROMPTS/sports.md` throughout — no
   guarantees, extra caution on parlays/heavy-vig lines/loss-chasing signals.
7. Suggest `/log-pick` so this prediction can be checked for calibration later.
