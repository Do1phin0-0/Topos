from sqlalchemy import select
from sqlalchemy.orm import Session

from titan.app.collectors.sec_edgar import SECEdgarCollector
from titan.app.db.models import InsiderTrade
from titan.app.signals.insider import normalize_form4_xml


def ingest_insider_trades(
    db: Session, collector: SECEdgarCollector | None = None, limit: int = 40
) -> int:
    """Fetches recent Form 4 filings, parses their ownership documents,
    and persists normalized trades. Dedupes on filing_url (one Form 4
    filing maps to at most one InsiderTrade row) so repeat ingestion runs
    don't pile up duplicates."""
    collector = collector or SECEdgarCollector()
    inserted = 0

    for filing in collector.latest_filings("4", count=limit):
        for doc in collector.filing_documents(filing["index_url"]):
            if not doc["name"].endswith(".xml"):
                continue
            try:
                root = collector.fetch_xml(doc["url"])
            except Exception:
                continue
            if not root.tag.endswith("ownershipDocument"):
                continue

            normalized = normalize_form4_xml(root, filing["index_url"])
            if normalized is None:
                break

            exists = db.execute(
                select(InsiderTrade.id).where(InsiderTrade.filing_url == normalized["filing_url"])
            ).first()
            if not exists:
                db.add(InsiderTrade(**normalized))
                inserted += 1
            break

    db.commit()
    return inserted
