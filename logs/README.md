# Calibration log

`picks.jsonl` records predictions made via `/sports`, `/sports-picks`, `/market`, or
`/market-picks` so calibration can be checked later with `/log-review` — i.e. whether a
"70% confident" call actually hits about 70% of the time.

One JSON object per line:

```json
{
  "id": "2026-07-01T20-15-00-messi-anytime-scorer",
  "date": "2026-07-01",
  "domain": "sports",
  "subject": "Messi vs Austria - anytime scorer",
  "your_probability": 0.55,
  "market_probability": 0.49,
  "market_source": "FanDuel",
  "outcome": null,
  "resolved_date": null,
  "reason": null,
  "notes": ""
}
```

- `outcome` is `null` until resolved, then `true` (hit) or `false` (miss).
- `your_probability` / `market_probability` are decimals (0-1), not percentages.
- `reason` is filled in at resolve time: the concrete, causal factor behind the result (e.g.
  "subbed off at 60'", "line moved on injury news that broke after the pick", "overrated one
  outlier game as the new baseline"). This is the raw material `/log-lessons` distills into
  `PROMPTS/lessons.md`.
- Entries are appended by `/log-pick` and updated in place by `/log-resolve`.
- Commands only write to this file — they don't commit to git on their own.
