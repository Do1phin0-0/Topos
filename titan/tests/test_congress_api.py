from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from titan.app.db.models import CongressionalTrade
from titan.app.db.session import SessionLocal
from titan.app.main import app

_FIXTURE_RECORD = {
    "ticker": "ZZZTEST",
    "type": "purchase",
    "amount": "$15,001 - $50,000",
    "representative": "Test Rep",
    "chamber": "house",
    "transaction_date": "2026-07-01",
    "disclosure_date": "2026-07-20",
    "ptr_link": "https://example.com/ptr.pdf",
}


def _clear_fixture_rows() -> None:
    session = SessionLocal()
    try:
        session.execute(delete(CongressionalTrade).where(CongressionalTrade.ticker == "ZZZTEST"))
        session.commit()
    finally:
        session.close()


def test_ingest_persists_and_list_returns_it_and_ingest_is_idempotent():
    _clear_fixture_rows()
    try:
        with patch(
            "titan.app.services.congress_service.CongressTradeCollector"
        ) as MockCollector:
            MockCollector.return_value.latest_transactions.return_value = [_FIXTURE_RECORD]

            with TestClient(app) as client:
                first = client.post("/congress/ingest")
                assert first.status_code == 200
                assert first.json()["inserted"] == 1

                # Running ingestion again with the same source data should
                # not create a duplicate row.
                second = client.post("/congress/ingest")
                assert second.json()["inserted"] == 0

                listed = client.get("/congress/trades", params={"ticker": "ZZZTEST"})
                assert listed.status_code == 200
                body = listed.json()
                assert len(body) == 1
                assert body[0]["ticker"] == "ZZZTEST"
                assert body[0]["transaction_type"] == "purchase"
    finally:
        _clear_fixture_rows()
