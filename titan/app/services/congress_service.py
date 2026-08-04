from sqlalchemy import select
from sqlalchemy.orm import Session

from titan.app.collectors.congress import CongressTradeCollector
from titan.app.db.models import CongressionalTrade
from titan.app.signals.congress import normalize_congress_record


def ingest_congressional_trades(
    db: Session, collector: CongressTradeCollector | None = None, limit: int = 200
) -> int:
    """Fetches, normalizes, and persists congressional trades. Dedupes on
    (chamber, member, ticker, transaction_date, transaction_type) so
    repeat ingestion runs (e.g. hourly) don't pile up duplicate rows for
    the same disclosed trade."""
    collector = collector or CongressTradeCollector()
    inserted = 0

    for record in collector.latest_transactions(limit=limit):
        normalized = normalize_congress_record(record)
        if normalized is None:
            continue

        exists = db.execute(
            select(CongressionalTrade.id).where(
                CongressionalTrade.chamber == normalized["chamber"],
                CongressionalTrade.member == normalized["member"],
                CongressionalTrade.ticker == normalized["ticker"],
                CongressionalTrade.transaction_date == normalized["transaction_date"],
                CongressionalTrade.transaction_type == normalized["transaction_type"],
            )
        ).first()
        if exists:
            continue

        db.add(CongressionalTrade(**normalized))
        inserted += 1

    db.commit()
    return inserted
