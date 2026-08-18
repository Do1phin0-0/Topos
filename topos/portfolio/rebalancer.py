from dataclasses import dataclass

from topos.portfolio.decision import TargetPosition


@dataclass
class RebalanceOrder:
    ticker: str
    side: str  # "buy" | "sell"
    notional_usd: float
    weight: float
    reason: str


class Rebalancer:
    """Diffs target portfolio weights against the broker's actual current
    positions to produce the minimal set of orders needed to reach the
    target — instead of resubmitting a full-weight buy for every top-ranked
    ticker on every pipeline run. Without this, an hourly cron would place
    a fresh buy order for the same ticker every hour it stays top-ranked,
    compounding the position far past any risk cap instead of holding it."""

    def __init__(self, min_order_usd: float = 25.0) -> None:
        self.min_order_usd = min_order_usd

    def plan(
        self,
        targets: list[TargetPosition],
        current_positions: dict[str, float],
        equity: float,
    ) -> list[RebalanceOrder]:
        orders: list[RebalanceOrder] = []
        target_by_ticker = {t.ticker: t for t in targets}

        for ticker, target in target_by_ticker.items():
            target_value = target.weight * equity
            current_value = current_positions.get(ticker, 0.0)
            delta = target_value - current_value
            if delta > self.min_order_usd:
                orders.append(
                    RebalanceOrder(ticker, "buy", delta, target.weight, "rebalance up to target weight")
                )
            elif delta < -self.min_order_usd:
                orders.append(
                    RebalanceOrder(ticker, "sell", -delta, target.weight, "trim to target weight")
                )

        for ticker, current_value in current_positions.items():
            if ticker not in target_by_ticker and current_value > self.min_order_usd:
                orders.append(RebalanceOrder(ticker, "sell", current_value, 0.0, "dropped from target list"))

        return orders
