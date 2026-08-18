from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from titan.app.db.models import CongressionalTrade
from titan.app.db.session import get_db
from titan.app.services.congress_service import ingest_congressional_trades

router = APIRouter(prefix="/congress", tags=["congress"])


@router.post("/ingest")
def trigger_ingest(limit: int = 200, db: Session = Depends(get_db)) -> dict:
    inserted = ingest_congressional_trades(db, limit=limit)
    return {"inserted": inserted}


@router.get("/trades")
def list_trades(
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    ticker: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = db.query(CongressionalTrade).order_by(CongressionalTrade.transaction_date.desc())
    if ticker:
        query = query.filter(CongressionalTrade.ticker == ticker.upper())
    rows = query.offset(offset).limit(limit).all()
    return [
        {
            "id": r.id,
            "chamber": r.chamber,
            "member": r.member,
            "ticker": r.ticker,
            "transaction_type": r.transaction_type,
            "transaction_date": r.transaction_date,
            "disclosure_date": r.disclosure_date,
            "amount_range": r.amount_range,
            "amount_midpoint_usd": r.amount_midpoint_usd,
            "source_url": r.source_url,
        }
        for r in rows
    ]
