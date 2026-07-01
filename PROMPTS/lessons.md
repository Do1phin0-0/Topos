# Lessons learned

A running, deduplicated list of patterns pulled from resolved picks in `logs/picks.jsonl`
(maintained by `/log-lessons`). `/sports`, `/sports-picks`, `/market`, and `/market-picks`
should check this file before analyzing and apply anything relevant — this is how the
agent's judgment is supposed to actually improve over time instead of repeating the same
mistakes.

Each lesson should be short, general, and actionable — not a play-by-play of one pick.
Consolidate similar lessons instead of letting the list grow indefinitely; if a new
resolved pick confirms an existing lesson, strengthen it (e.g. note it's happened more than
once) rather than adding a near-duplicate entry.

Format per lesson:

```
### <short label>
<1-2 sentence takeaway>
- Seen in: <subject>, <subject>, ... (add to this list each time it recurs)
```

No lessons logged yet. Run `/log-resolve` on some picks with a `reason`, then `/log-lessons`
to populate this.
