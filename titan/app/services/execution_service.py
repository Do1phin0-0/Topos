from sqlalchemy.orm import Session

from titan.app.db.models import SignalScore, Trade
from titan.app.execution.alpaca_client import AlpacaExecutionClient


def execute_top_buys(
    db: Session,
    client: AlpacaExecutionClient | None = None,
    top_n: int = 5,
    account_equity: float = 100_000.0,
    dry_run: bool = True,
) -> list[Trade]:
    """Takes the BUY recommendations from the most recent scoring run,
    equal-weights the top N by score, and submits paper orders (or logs a
    dry run). Every attempt is recorded in `trades`, regardless of
    outcome — this is a trade *log*, not just a log of successes.

    "Most recent scoring run" is every SignalScore row sharing the exact
    same computed_at as the newest one — score_all() gives every ticker
    scored together the same timestamp specifically so this query works."""
    client = client or AlpacaExecutionClient()

    latest_computed_at = (
        db.query(SignalScore.computed_at).order_by(SignalScore.computed_at.desc()).limit(1).scalar()
    )
    if latest_computed_at is None:
        return []

    buys = (
        db.query(SignalScore)
        .filter(SignalScore.computed_at == latest_computed_at, SignalScore.recommendation == "BUY")
        .order_by(SignalScore.score.desc())
        .limit(top_n)
        .all()
    )
    if not buys:
        return []

    weight = 1.0 / len(buys)
    trades = []
    for score in buys:
        notional = account_equity * weight
        result = client.place_order(score.ticker, notional_usd=notional, dry_run=dry_run)
        trade = Trade(
            ticker=result.ticker,
            side="buy",
            notional_usd=notional,
            status=result.status,
            broker_order_id=result.order_id,
            detail=result.detail,
        )
        db.add(trade)
        trades.append(trade)

    db.commit()
    return trades
