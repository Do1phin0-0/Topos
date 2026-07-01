# Topos

System prompts for two agents:

- [`PROMPTS/market.md`](PROMPTS/market.md) — market intelligence agent
- [`PROMPTS/sports.md`](PROMPTS/sports.md) — sports intelligence agent
- [`PROMPTS/sports-suggestions.md`](PROMPTS/sports-suggestions.md) — cross-sport daily suggestions agent

## Commands

- `/sports <player/team, matchup, and prop>` — runs the sports intelligence agent: looks up
  current odds/form via web search, answers in the standard format (headline, key factors,
  your probability vs. market-implied probability, edge verdict, confidence), and always
  closes with a suggestion for a better-fitting alternative line if the data supports one.
- `/sports-picks [optional sport/league/team]` — scans recent results across sports (e.g.
  "last night's scorers") and suggests the best-supported angles for each standout
  performer's next game, with the reasoning and market-implied odds behind each one.
