from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from titan.app.config import get_settings
from titan.app.db.models import Trade
from titan.app.db.session import get_db
from titan.app.execution.alpaca_client import AlpacaExecutionClient
from titan.app.services.execution_service import execute_top_buys

router = APIRouter(prefix="/execution", tags=["execution"])


@router.post("/run")
def run_execution(
    top_n: int = 5,
    account_equity: float = 100_000.0,
    execute: bool = False,
    db: Session = Depends(get_db),
) -> list[dict]:
    """execute=False (default) is a dry run — logs intended trades but
    submits nothing. execute=True submits real paper orders and requires
    Alpaca credentials to be configured."""
    trades = execute_top_buys(db, top_n=top_n, account_equity=account_equity, dry_run=not execute)
    return [
        {
            "ticker": t.ticker,
            "side": t.side,
            "notional_usd": t.notional_usd,
            "status": t.status,
            "broker_order_id": t.broker_order_id,
            "detail": t.detail,
        }
        for t in trades
    ]


@router.get("/trades")
def list_trades(limit: int = Query(default=50, le=500), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Trade).order_by(Trade.submitted_at.desc()).limit(limit).all()
    return [
        {
            "id": t.id,
            "ticker": t.ticker,
            "side": t.side,
            "notional_usd": t.notional_usd,
            "status": t.status,
            "broker_order_id": t.broker_order_id,
            "detail": t.detail,
            "submitted_at": t.submitted_at,
        }
        for t in rows
    ]


@router.get("/account")
def get_account() -> dict:
    settings = get_settings()
    if not (settings.alpaca_api_key and settings.alpaca_secret_key):
        raise HTTPException(status_code=400, detail="ALPACA_API_KEY/ALPACA_SECRET_KEY not configured")
    return AlpacaExecutionClient().get_account()


@router.get("/positions")
def get_positions() -> list[dict]:
    settings = get_settings()
    if not (settings.alpaca_api_key and settings.alpaca_secret_key):
        raise HTTPException(status_code=400, detail="ALPACA_API_KEY/ALPACA_SECRET_KEY not configured")
    return AlpacaExecutionClient().get_positions()
