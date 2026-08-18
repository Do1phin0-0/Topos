from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete

from titan.app.db.models import CongressionalTrade, InsiderTrade, SignalScore
from titan.app.db.session import SessionLocal
from titan.app.main import app


def _clear_fixture_rows() -> None:
    session = SessionLocal()
    try:
        session.execute(delete(CongressionalTrade).where(CongressionalTrade.ticker == "ZZZTEST"))
        session.execute(delete(InsiderTrade).where(InsiderTrade.ticker == "ZZZTEST"))
        session.execute(delete(SignalScore).where(SignalScore.ticker == "ZZZTEST"))
        session.commit()
    finally:
        session.close()


def test_scoring_run_persists_and_scores_endpoint_returns_it():
    _clear_fixture_rows()
    try:
        session = SessionLocal()
        try:
            session.add(
                CongressionalTrade(
                    chamber="house",
                    member="Test Rep",
                    ticker="ZZZTEST",
                    transaction_type="purchase",
                    transaction_date=datetime(2026, 7, 1),
                    amount_midpoint_usd=500_000,
                )
            )
            session.add(
                InsiderTrade(
                    ticker="ZZZTEST",
                    owner_name="Test Owner",
                    is_officer=True,
                    is_director=False,
                    transaction_code="P",
                    direction="buy",
                    shares=1000.0,
                    total_value_usd=800_000,
                    transaction_date=datetime(2026, 7, 2),
                )
            )
            session.commit()
        finally:
            session.close()

        with TestClient(app) as client:
            run_response = client.post("/scoring/run")
            assert run_response.status_code == 200
            run_body = run_response.json()
            fixture_entry = next(r for r in run_body if r["ticker"] == "ZZZTEST")
            assert fixture_entry["recommendation"] == "BUY"
            assert fixture_entry["congress_signal_count"] == 1
            assert fixture_entry["insider_signal_count"] == 1

            scores_response = client.get("/scoring/scores", params={"recommendation": "BUY"})
            assert scores_response.status_code == 200
            tickers = [r["ticker"] for r in scores_response.json()]
            assert "ZZZTEST" in tickers
    finally:
        _clear_fixture_rows()
