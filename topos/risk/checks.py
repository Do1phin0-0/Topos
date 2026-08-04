from dataclasses import dataclass

from topos.portfolio.decision import TargetPosition


@dataclass
class RiskDecision:
    approved: list[TargetPosition]
    rejected: list[tuple[TargetPosition, str]]


class RiskManager:
    """Trades only reach the execution layer after passing these checks."""

    def __init__(self, max_position_weight: float = 0.25, max_positions: int = 10) -> None:
        self.max_position_weight = max_position_weight
        self.max_positions = max_positions

    def check(self, targets: list[TargetPosition]) -> RiskDecision:
        approved: list[TargetPosition] = []
        rejected: list[tuple[TargetPosition, str]] = []

        for target in targets[: self.max_positions]:
            if target.weight > self.max_position_weight:
                target = TargetPosition(
                    ticker=target.ticker, weight=self.max_position_weight, score=target.score
                )
            approved.append(target)

        for target in targets[self.max_positions :]:
            rejected.append((target, "exceeds max open positions"))

        return RiskDecision(approved=approved, rejected=rejected)
