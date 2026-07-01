---
description: Market/contract analysis using the market intelligence agent prompt
---

Follow the market intelligence agent prompt in `PROMPTS/market.md` to answer this request:
$ARGUMENTS

Steps:

1. Identify the specific market question, contract, or asset being asked about. If it's
   ambiguous (which contract, which platform), ask before proceeding.
2. Use `WebSearch` to find current prices/quotes and recent news — do not answer from
   memorized data, since it may be stale or wrong. Cite sources.
3. Answer using the required format from `PROMPTS/market.md`: headline read, key factors,
   your probability estimate, market-implied probability, edge verdict, confidence level.
4. Always close with a **Suggestion** section: if the data supports a better-fitting
   alternative (a different contract, side, or threshold that matches the evidence or has
   better implied value), name it plainly and say why. If the original ask already looks
   well-supported, say that instead of manufacturing an alternative.
5. Apply the disclaimer from `PROMPTS/market.md` throughout — this is analysis, not
   investment advice, and never a guarantee.
