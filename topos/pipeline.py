from sqlalchemy import select

from topos.backtesting.prices import backfill_tickers
from topos.db.models import Signal as SignalRow
from topos.db.models import Trade as TradeRow
from topos.db.session import SessionLocal, init_db
from topos.execution.alpaca_client import AlpacaExecutionClient
from topos.portfolio.decision import PortfolioDecisionEngine
from topos.ranking.ranker import RankingEngine
from topos.risk.checks import RiskManager
from topos.screening.liquidity import filter_signals, filter_tradeable
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


# SQLite allows 999 bound parameters per statement in builds still widely
# shipped, and a historical backfill hands this function tens of thousands
# of signals at once. Chunking keeps one IN clause well under any dialect's
# ceiling; 500 is small enough to be safe and large enough that the round
# trips are irrelevant next to the parsing that produced the signals.
_LOOKUP_CHUNK = 500


def _existing_keys(session, keys: list[str]) -> set[str]:
    """Which of these dedup keys are already stored, asked in batches."""
    found: set[str] = set()
    for start in range(0, len(keys), _LOOKUP_CHUNK):
        chunk = keys[start : start + _LOOKUP_CHUNK]
        found.update(
            row[0]
            for row in session.execute(
                select(SignalRow.dedup_key).where(SignalRow.dedup_key.in_(chunk))
            ).all()
        )
    return found


def persist_signals(session, signals: list[Signal]) -> int:
    """Stores signals we haven't seen before, keyed on dedup_key.

    The pipeline is meant to run on a schedule over overlapping windows —
    the same Form 4 filing shows up in the feed for hours. Without this,
    every run re-inserted the same filings as fresh signals, which both
    inflates a ticker's apparent signal count in ranking and makes the
    stored history useless for backtesting. Returns the number inserted.
    """
    if not signals:
        return 0

    seen = _existing_keys(session, [s.dedup_key for s in signals])

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
    discovered = sorted({s.ticker for s in discovery_signals})[:_MAX_ENRICHMENT_TICKERS]

    session = SessionLocal()
    try:
        # Price history is fetched once per run and reused: it feeds the
        # liquidity screen now and the backtester later.
        if discovered:
            backfill_tickers(session, discovered)

        # Screen before enrichment, not after — an untradeable name should
        # never reach Ranked Opportunities, and there's no point spending
        # news/technical lookups on one either.
        tickers, rejected = filter_tradeable(session, discovered)
        for verdict in rejected:
            print(f"[screened out] {verdict.ticker}: {verdict.reason}")

        enrichment_signals = _collect_enrichment_signals(tickers) if tickers else []
        signals = discovery_signals + enrichment_signals

        new_signals = persist_signals(session, signals)
        print(f"Persisted {new_signals} new signals ({len(signals) - new_signals} already known).")

        # Rank only what's actually tradeable.
        rankable = filter_signals(session, signals)
        ranked = RankingEngine().rank(rankable)
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
