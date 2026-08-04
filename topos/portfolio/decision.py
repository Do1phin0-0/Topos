from dataclasses import dataclass

from topos.db.models import RankedOpportunity


@dataclass
class TargetPosition:
    ticker: str
    weight: float
    score: float


class PortfolioDecisionEngine:
    """MVP allocation: equal-weight the top N tickers the ranking engine
    recommended BUY, above a score floor (both on a 0-100 scale).
    Deliberately simple — this is the seam where smarter sizing (Kelly-ish,
    volatility-scaled, etc.) plugs in later.

    Only considers recommendation == "BUY": a ticker can score high from
    pure attention/agreement but still get SELL or HOLD from the ranking
    engine if its signals lean bearish or don't agree — the portfolio
    engine has to respect that, not just chase the highest number."""

    def __init__(self, top_n: int = 5, min_score: float = 50.0) -> None:
        self.top_n = top_n
        self.min_score = min_score

    def decide(self, ranked: list[RankedOpportunity]) -> list[TargetPosition]:
        candidates = [
            r for r in ranked if r.recommendation == "BUY" and r.score >= self.min_score
        ][: self.top_n]
        if not candidates:
            return []
        weight = round(1.0 / len(candidates), 4)
        return [TargetPosition(ticker=r.ticker, weight=weight, score=r.score) for r in candidates]
