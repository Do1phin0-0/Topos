# Topos

System prompts for two agents:

- [`PROMPTS/market.md`](PROMPTS/market.md) — market intelligence agent
- [`PROMPTS/sports.md`](PROMPTS/sports.md) — sports intelligence agent

## Commands

- `/sports <player/team, matchup, and prop>` — runs the sports intelligence agent: looks up
  current odds/form via web search, answers in the standard format (headline, key factors,
  your probability vs. market-implied probability, edge verdict, confidence), and always
  closes with a suggestion for a better-fitting alternative line if the data supports one.
