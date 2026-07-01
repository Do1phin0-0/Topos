---
description: Review calibration — how well your probability estimates matched outcomes
---

Read `logs/picks.jsonl` and produce a calibration report. Optional filter: $ARGUMENTS (e.g.
"sports" or "market") — if empty, cover everything.

Steps:

1. Load all entries; separate resolved (`outcome` is `true`/`false`) from unresolved
   (`outcome: null`).
2. For resolved entries, bucket by `your_probability` (e.g. 0-20%, 20-40%, 40-60%, 60-80%,
   80-100%) and compute the actual hit rate in each bucket. Compare each bucket's hit rate
   to its midpoint to say whether estimates ran over- or under-confident.
3. Do the same bucketing for `market_probability` on the same entries, so the report shows
   whether the agent's read or the market's read was better calibrated on these specific
   picks.
4. Report sample size honestly — call out any bucket with too few entries (e.g. fewer than
   5) to draw a real conclusion from.
5. List unresolved entries separately as a reminder to `/log-resolve` them.
