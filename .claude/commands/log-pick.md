---
description: Record a prediction/pick to the calibration log for later review
---

Append a new entry to `logs/picks.jsonl` for this pick: $ARGUMENTS

If $ARGUMENTS doesn't include enough detail — subject, your probability estimate, and the
market-implied probability plus its source — ask for whatever's missing rather than
guessing. If this follows directly from a `/sports`, `/sports-picks`, `/market`, or
`/market-picks` answer earlier in the conversation, pull the values from that instead of
asking again.

Steps:

1. Build one JSON object matching the schema in `logs/README.md`: `id` (timestamp + short
   slug), `date` (today), `domain` ("sports" or "market"), `subject`, `your_probability`,
   `market_probability`, `market_source`, `outcome: null`, `resolved_date: null`,
   `reason: null`, `notes` (optional).
2. Append it as a single line to `logs/picks.jsonl` (create the file if it doesn't exist —
   do not overwrite existing lines).
3. Confirm what was logged. Do not commit the change to git unless the user explicitly
   asks.
