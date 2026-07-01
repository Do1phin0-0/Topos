---
description: Mark a previously logged pick with its actual outcome
---

Resolve a previously logged pick: $ARGUMENTS (identify which entry — by subject text or
`id` — and what actually happened).

Steps:

1. Read `logs/picks.jsonl` and find the matching entry with `outcome: null` by subject/id
   match. If none match, or more than one matches ambiguously, ask which entry is meant
   rather than guessing.
2. Set `outcome` to `true` (hit) or `false` (miss) based on what actually happened, and set
   `resolved_date` to today.
3. Fill in `reason`: the concrete, causal factor behind the result, not just a restatement
   of the outcome. On a miss, be specific about what the analysis got wrong or missed (e.g.
   "subbed off at 60'", "line moved on injury news that broke after the pick",
   "overrated one outlier game as the new baseline", "ignored travel/rest disadvantage").
   On a hit, note briefly what actually drove it if it's informative. If you don't have
   enough information to say why, ask the user rather than inventing a plausible-sounding
   reason.
4. Rewrite the file with the updated line, leaving every other line untouched (still one
   JSON object per line).
5. Confirm what was updated, and suggest running `/log-lessons` once a few misses have
   reasons logged. Do not commit the change to git unless the user explicitly asks.
