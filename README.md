# Topos

System prompts for two agents:

- [`PROMPTS/market.md`](PROMPTS/market.md) — market intelligence agent
- [`PROMPTS/sports.md`](PROMPTS/sports.md) — sports intelligence agent
- [`PROMPTS/sports-suggestions.md`](PROMPTS/sports-suggestions.md) — cross-sport daily suggestions agent
- [`PROMPTS/market-suggestions.md`](PROMPTS/market-suggestions.md) — cross-market daily suggestions agent

## Commands

- `/sports <player/team, matchup, and prop>` — runs the sports intelligence agent: looks up
  current odds/form via web search, answers in the standard format (headline, key factors,
  your probability vs. market-implied probability, edge verdict, confidence), and always
  closes with a suggestion for a better-fitting alternative line if the data supports one.
- `/sports-picks [optional sport/league/team]` — scans recent results across sports (e.g.
  "last night's scorers") and suggests the best-supported angles for each standout
  performer's next game, with the reasoning and market-implied odds behind each one.
- `/market <question/contract>` — the market equivalent of `/sports`: current price/news via
  web search, same answer format, closes with a suggestion.
- `/market-picks [optional market/sector/platform]` — the market equivalent of
  `/sports-picks`: scans recent news/catalysts and suggests angles on contracts/assets that
  look interesting right now.
- `/log-pick <pick details>` — records a prediction (from any of the above) to
  `logs/picks.jsonl` for later calibration review.
- `/log-resolve <pick, outcome>` — marks a previously logged pick as a hit or miss.
- `/log-review [optional sports|market filter]` — reports how well past probability
  estimates matched actual outcomes, bucketed by confidence level, and compares against how
  well the market's own odds were calibrated on the same picks.

See [`logs/README.md`](logs/README.md) for the log schema.
