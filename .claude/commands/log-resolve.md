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
3. Rewrite the file with the updated line, leaving every other line untouched (still one
   JSON object per line).
4. Confirm what was updated. Do not commit the change to git unless the user explicitly
   asks.
