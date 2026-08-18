from topos.db.models import Signal as SignalRow
from topos.db.models import Trade as TradeRow
from topos.db.session import SessionLocal, init_db
from topos.execution.alpaca_client import AlpacaExecutionClient
from topos.portfolio.decision import PortfolioDecisionEngine
from topos.ranking.ranker import RankingEngine
from topos.risk.checks import RiskManager
from topos.signals.base import Signal
from topos.signals.congress import CongressSignalExtractor
from topos.signals.filing_13f import Filing13FSignalExtractor
from topos.signals.form4 import Form4SignalExtractor


def _collect_signals(limit: int) -> list[Signal]:
    """Each source fails independently — a dead congressional-data mirror
    shouldn't take down Form 4 collection, or vice versa."""
    signals: list[Signal] = []
    for name, extractor_cls in [
        ("sec_form4", Form4SignalExtractor),
        ("congress", CongressSignalExtractor),
        ("sec_13f", Filing13FSignalExtractor),
    ]:
        try:
            signals.extend(extractor_cls().extract(limit=limit))
        except Exception as exc:
            print(f"[warn] {name} extractor failed: {exc}")
    return signals


def run(dry_run: bool = True, account_equity: float = 100_000.0, limit: int = 40) -> None:
    init_db()
    signals = _collect_signals(limit)

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
    session = SessionLocal()
    try:
        for target in risk_decision.approved:
            notional = account_equity * target.weight
            result = execution_client.place_order(target, notional_usd=notional, dry_run=dry_run)
            session.add(
                TradeRow(
                    ticker=result.ticker,
                    side="buy",
                    weight=target.weight,
                    notional_usd=notional,
                    status=result.status,
                    broker_order_id=result.order_id,
                    detail=result.detail,
                )
            )
            print(f"[{result.status}] {result.detail}")
        session.commit()
    finally:
        session.close()

    for target, reason in risk_decision.rejected:
        print(f"[rejected] {target.ticker}: {reason}")

    print(f"\nCollected {len(signals)} signals across {len(ranked)} tickers.")
