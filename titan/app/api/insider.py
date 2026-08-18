from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from titan.app.db.models import InsiderTrade
from titan.app.db.session import get_db
from titan.app.services.insider_service import ingest_insider_trades

router = APIRouter(prefix="/insider", tags=["insider"])


@router.post("/ingest")
def trigger_ingest(limit: int = 40, db: Session = Depends(get_db)) -> dict:
    inserted = ingest_insider_trades(db, limit=limit)
    return {"inserted": inserted}


@router.get("/trades")
def list_trades(
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    ticker: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = db.query(InsiderTrade).order_by(InsiderTrade.ingested_at.desc())
    if ticker:
        query = query.filter(InsiderTrade.ticker == ticker.upper())
    rows = query.offset(offset).limit(limit).all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "owner_name": r.owner_name,
            "is_officer": r.is_officer,
            "is_director": r.is_director,
            "transaction_code": r.transaction_code,
            "direction": r.direction,
            "shares": r.shares,
            "total_value_usd": r.total_value_usd,
            "filing_url": r.filing_url,
            "transaction_date": r.transaction_date,
        }
        for r in rows
    ]
