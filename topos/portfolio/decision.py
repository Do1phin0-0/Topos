from dataclasses import dataclass

from topos.db.models import RankedOpportunity


@dataclass
class TargetPosition:
    ticker: str
    weight: float
    score: float


class PortfolioDecisionEngine:
    """MVP allocation: equal-weight the top N ranked tickers above a score
    floor. Deliberately simple — this is the seam where smarter sizing
    (Kelly-ish, volatility-scaled, etc.) plugs in later."""

    def __init__(self, top_n: int = 5, min_score: float = 0.5) -> None:
        self.top_n = top_n
        self.min_score = min_score

    def decide(self, ranked: list[RankedOpportunity]) -> list[TargetPosition]:
        candidates = [r for r in ranked if r.score >= self.min_score][: self.top_n]
        if not candidates:
            return []
        weight = round(1.0 / len(candidates), 4)
        return [TargetPosition(ticker=r.ticker, weight=weight, score=r.score) for r in candidates]
