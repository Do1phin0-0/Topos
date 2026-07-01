---
description: Distill resolved picks in the log into reusable lessons
---

Read `logs/picks.jsonl` and update `PROMPTS/lessons.md` with generalizable lessons drawn
from resolved entries that have a `reason` filled in. Optional filter: $ARGUMENTS (e.g.
"sports" or "market") — if empty, cover everything.

Steps:

1. Load all resolved entries (`outcome` is `true` or `false`) that have a non-empty
   `reason`. Skip entries without a reason — there's nothing to generalize from yet.
2. Group them by recurring pattern (e.g. "overrated a single outlier performance as the new
   baseline," "missed a late injury/lineup change," "ignored travel or rest disadvantage,"
   "market was actually right and the analysis overrode it without enough justification").
   A pattern only needs 1 occurrence to be worth recording, but note the count so real
   patterns (3+ occurrences) stand out from one-offs.
3. Update `PROMPTS/lessons.md` using the format already in that file: merge into existing
   lessons where a new entry confirms one already there (add to its "Seen in" list) rather
   than creating a near-duplicate; add new lessons as new entries; keep each lesson to 1-2
   sentences.
4. Keep the file a manageable length — if it's getting long, prefer consolidating
   overlapping lessons into a broader one over keeping every narrow variant.
5. Report what was added or strengthened. Do not commit the change to git unless the user
   explicitly asks.
