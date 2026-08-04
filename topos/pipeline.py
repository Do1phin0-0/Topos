from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db
from topos.execution.alpaca_client import AlpacaExecutionClient
from topos.portfolio.decision import PortfolioDecisionEngine
from topos.ranking.ranker import RankingEngine
from topos.risk.checks import RiskManager
from topos.signals.form4 import Form4SignalExtractor


def run(dry_run: bool = True, account_equity: float = 100_000.0) -> None:
    init_db()
    signals = Form4SignalExtractor().extract(limit=40)

    session = SessionLocal()
    try:
        for signal in signals:
            session.add(
                SignalRow(
                    timestamp=signal.timestamp,
                    source=signal.source,
                    ticker=signal.ticker,
                    confidence=signal.confidence,
                    evidence=signal.evidence,
                )
            )
        session.commit()

        ranked = RankingEngine().rank(signals)
        for opportunity in ranked:
            session.add(opportunity)
        session.commit()
    finally:
        session.close()

    targets = PortfolioDecisionEngine().decide(ranked)
    risk_decision = RiskManager().check(targets)

    execution_client = AlpacaExecutionClient()
    for target in risk_decision.approved:
        result = execution_client.place_order(
            target, notional_usd=account_equity * target.weight, dry_run=dry_run
        )
        print(f"[{result.status}] {result.detail}")

    for target, reason in risk_decision.rejected:
        print(f"[rejected] {target.ticker}: {reason}")

    print(f"\nCollected {len(signals)} signals across {len(ranked)} tickers.")
