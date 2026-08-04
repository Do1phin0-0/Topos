from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete

from titan.app.db.models import SignalScore, Trade
from titan.app.db.session import SessionLocal
from titan.app.main import app

_RUN_TIMESTAMP = datetime(2026, 1, 1, 12, 0, 0)


def _clear_fixture_rows() -> None:
    session = SessionLocal()
    try:
        session.execute(delete(SignalScore).where(SignalScore.ticker.in_(["ZZZBUY1", "ZZZBUY2", "ZZZHOLD"])))
        session.execute(delete(Trade).where(Trade.ticker.in_(["ZZZBUY1", "ZZZBUY2", "ZZZHOLD"])))
        session.commit()
    finally:
        session.close()


def _seed_scores() -> None:
    session = SessionLocal()
    try:
        session.add_all(
            [
                SignalScore(
                    ticker="ZZZBUY1",
                    score=90.0,
                    recommendation="BUY",
                    net_direction=1.0,
                    congress_signal_count=1,
                    insider_signal_count=1,
                    computed_at=_RUN_TIMESTAMP,
                ),
                SignalScore(
                    ticker="ZZZBUY2",
                    score=70.0,
                    recommendation="BUY",
                    net_direction=1.0,
                    congress_signal_count=1,
                    insider_signal_count=1,
                    computed_at=_RUN_TIMESTAMP,
                ),
                SignalScore(
                    ticker="ZZZHOLD",
                    score=95.0,  # deliberately higher score than the BUYs
                    recommendation="HOLD",
                    net_direction=0.0,
                    congress_signal_count=1,
                    insider_signal_count=0,
                    computed_at=_RUN_TIMESTAMP,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()


def test_execution_run_only_trades_buys_from_latest_run_and_equal_weights():
    _clear_fixture_rows()
    try:
        _seed_scores()

        with TestClient(app) as client:
            response = client.post(
                "/execution/run", params={"top_n": 5, "account_equity": 100_000.0}
            )
            assert response.status_code == 200
            body = response.json()

            traded_tickers = {t["ticker"] for t in body}
            # HOLD is excluded even though its score (95) beats both BUYs —
            # only recommendation == "BUY" ever gets traded.
            assert traded_tickers == {"ZZZBUY1", "ZZZBUY2"}

            for trade in body:
                assert trade["status"] == "dry_run"
                assert trade["notional_usd"] == 50_000.0  # equal-weighted across 2 BUYs

            listed = client.get("/execution/trades")
            listed_tickers = {t["ticker"] for t in listed.json() if t["ticker"] in {"ZZZBUY1", "ZZZBUY2"}}
            assert listed_tickers == {"ZZZBUY1", "ZZZBUY2"}
    finally:
        _clear_fixture_rows()


def test_account_and_positions_require_alpaca_credentials():
    with TestClient(app) as client:
        account_response = client.get("/execution/account")
        positions_response = client.get("/execution/positions")

    assert account_response.status_code == 400
    assert positions_response.status_code == 400
