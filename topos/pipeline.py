from sqlalchemy import select

from topos.db.models import Signal as SignalRow
from topos.db.models import Trade as TradeRow
from topos.db.session import SessionLocal, init_db
from topos.execution.alpaca_client import AlpacaExecutionClient
from topos.portfolio.decision import PortfolioDecisionEngine
from topos.ranking.ranker import RankingEngine
from topos.risk.checks import RiskManager
from topos.signals.base import Signal
from topos.signals.congress import CongressSignalExtractor
from topos.signals.earnings import EarningsSignalExtractor
from topos.signals.form4 import Form4SignalExtractor
from topos.signals.institutional import InstitutionalSignalExtractor
from topos.signals.news import NewsSignalExtractor
from topos.signals.reddit import RedditSignalExtractor
from topos.signals.technical import TechnicalSignalExtractor
from topos.signals.twitter import TwitterSignalExtractor

_MAX_ENRICHMENT_TICKERS = 20


def persist_signals(session, signals: list[Signal]) -> int:
    """Stores signals we haven't seen before, keyed on dedup_key.

    The pipeline is meant to run on a schedule over overlapping windows —
    the same Form 4 filing shows up in the feed for hours. Without this,
    every run re-inserted the same filings as fresh signals, which both
    inflates a ticker's apparent signal count in ranking and makes the
    stored history useless for backtesting. Returns the number inserted.
    """
    seen = {
        row[0]
        for row in session.execute(
            select(SignalRow.dedup_key).where(
                SignalRow.dedup_key.in_([s.dedup_key for s in signals] or [""])
            )
        ).all()
    }

    inserted = 0
    for signal in signals:
        if signal.dedup_key in seen:
            continue
        seen.add(signal.dedup_key)  # guard against duplicates within one batch
        session.add(
            SignalRow(
                timestamp=signal.timestamp,
                event_date=signal.event_date,
                dedup_key=signal.dedup_key,
                source=signal.source,
                ticker=signal.ticker,
                confidence=signal.confidence,
                evidence=signal.evidence,
            )
        )
        inserted += 1

    session.commit()
    return inserted


def _collect_discovery_signals(limit: int) -> list[Signal]:
    """Sources that scan recent activity and surface their own tickers.
    The extractor classes are looked up by name on each call (rather than
    captured in a module-level list) so tests can patch e.g.
    topos.pipeline.Form4SignalExtractor and have it take effect."""
    signals: list[Signal] = []
    for name, extractor_cls in [
        ("sec_form4", Form4SignalExtractor),
        ("congress", CongressSignalExtractor),
        ("sec_8k_earnings", EarningsSignalExtractor),
        ("institutional_13f", InstitutionalSignalExtractor),
    ]:
        try:
            signals.extend(extractor_cls().extract(limit=limit))
        except Exception as exc:
            print(f"[warn] {name} extractor failed: {exc}")
    return signals


def _collect_enrichment_signals(tickers: list[str]) -> list[Signal]:
    """Sources that need a ticker to look at — there's no free firehose of
    "sentiment for the whole market," so these only run against tickers the
    discovery sources already flagged this run, not a second blind scan."""
    signals: list[Signal] = []
    for name, extractor_cls in [
        ("news", NewsSignalExtractor),
        ("reddit", RedditSignalExtractor),
        ("twitter", TwitterSignalExtractor),
        ("technical", TechnicalSignalExtractor),
    ]:
        try:
            signals.extend(extractor_cls().extract(tickers))
        except Exception as exc:
            print(f"[warn] {name} extractor failed: {exc}")
    return signals


def run(dry_run: bool = True, account_equity: float = 100_000.0, limit: int = 40) -> None:
    init_db()
    discovery_signals = _collect_discovery_signals(limit)
    tickers = sorted({s.ticker for s in discovery_signals})[:_MAX_ENRICHMENT_TICKERS]
    enrichment_signals = _collect_enrichment_signals(tickers) if tickers else []
    signals = discovery_signals + enrichment_signals

    session = SessionLocal()
    try:
        new_signals = persist_signals(session, signals)
        print(f"Persisted {new_signals} new signals ({len(signals) - new_signals} already known).")

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
