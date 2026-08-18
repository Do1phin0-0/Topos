import logging

from sqlalchemy.orm import Session

from topos.db.models import Signal as SignalRow
from topos.db.models import Trade as TradeRow
from topos.db.session import SessionLocal, init_db
from topos.execution.alpaca_client import AlpacaExecutionClient
from topos.portfolio.decision import PortfolioDecisionEngine
from topos.portfolio.rebalancer import Rebalancer
from topos.ranking.ranker import RankingEngine
from topos.risk.checks import RiskManager
from topos.signals.base import Signal
from topos.signals.congress import CongressSignalExtractor
from topos.signals.filing_13f import Filing13FSignalExtractor
from topos.signals.form4 import Form4SignalExtractor

logger = logging.getLogger(__name__)

# Used for position sizing only when running dry (or without Alpaca
# credentials) so a dry run still prints realistic notional amounts. Any
# real (non-dry-run) trading uses the account's actual equity from Alpaca —
# see run() below.
FALLBACK_EQUITY = 100_000.0


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
        except Exception:
            logger.exception("%s extractor failed", name)
    return signals


def _persist_signals(session: Session, signals: list[Signal]) -> int:
    """Insert only signals not already stored (matched by source +
    external_id), so an hourly cron re-pulling the same filings and
    disclosures doesn't duplicate rows on every run. Signals without an
    external_id (no source-provided stable id) are always inserted."""
    keyed_ids = {s.external_id for s in signals if s.external_id}
    existing: set[tuple[str, str]] = set()
    if keyed_ids:
        rows = (
            session.query(SignalRow.source, SignalRow.external_id)
            .filter(SignalRow.external_id.in_(keyed_ids))
            .all()
        )
        existing = set(rows)

    inserted = 0
    for signal in signals:
        if signal.external_id and (signal.source, signal.external_id) in existing:
            continue
        session.add(
            SignalRow(
                timestamp=signal.timestamp,
                source=signal.source,
                ticker=signal.ticker,
                confidence=signal.confidence,
                evidence=signal.evidence,
                external_id=signal.external_id,
            )
        )
        inserted += 1
    session.commit()
    return inserted


def run(dry_run: bool = True, limit: int = 40) -> None:
    init_db()
    signals = _collect_signals(limit)

    session = SessionLocal()
    try:
        inserted = _persist_signals(session, signals)
        logger.info("collected %d signals (%d new)", len(signals), inserted)

        ranked = RankingEngine().rank(signals)
        for opportunity in ranked:
            session.add(opportunity)
        session.commit()
    finally:
        session.close()

    execution_client = AlpacaExecutionClient()
    equity = FALLBACK_EQUITY
    current_positions: dict[str, float] = {}
    if not dry_run:
        try:
            account = execution_client.get_account()
            equity = float(account["equity"])
            current_positions = execution_client.get_positions_by_ticker()
        except Exception:
            logger.exception("could not fetch Alpaca account state; skipping trading this run")
            logger.info(
                "Collected %d signals across %d tickers. Trading skipped: Alpaca unreachable.",
                len(signals),
                len(ranked),
            )
            return

    targets = PortfolioDecisionEngine().decide(ranked)
    risk_decision = RiskManager().check(targets)
    orders = Rebalancer().plan(risk_decision.approved, current_positions, equity)

    session = SessionLocal()
    try:
        for order in orders:
            result = execution_client.place_order(
                order.ticker, order.notional_usd, order.side, dry_run=dry_run
            )
            session.add(
                TradeRow(
                    ticker=result.ticker,
                    side=order.side,
                    weight=order.weight,
                    notional_usd=order.notional_usd,
                    status=result.status,
                    broker_order_id=result.order_id,
                    detail=result.detail,
                )
            )
            logger.info("[%s] %s (%s)", result.status, result.detail, order.reason)
        session.commit()
    finally:
        session.close()

    for target, reason in risk_decision.rejected:
        logger.info("[rejected] %s: %s", target.ticker, reason)

    logger.info(
        "Collected %d signals across %d tickers, %d orders planned.",
        len(signals),
        len(ranked),
        len(orders),
    )
