import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from titan.app.db.models import InsiderTrade
from titan.app.db.session import SessionLocal
from titan.app.main import app

_FIXTURE_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>ZZZTEST</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Fixture Owner</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><isDirector>0</isDirector></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-07-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>20.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

_FILING_INDEX_URL = "https://sec.gov/Archives/edgar/data/1/fixture-index.htm"


def _clear_fixture_rows() -> None:
    session = SessionLocal()
    try:
        session.execute(delete(InsiderTrade).where(InsiderTrade.ticker == "ZZZTEST"))
        session.commit()
    finally:
        session.close()


def test_ingest_persists_and_list_returns_it_and_ingest_is_idempotent():
    _clear_fixture_rows()
    try:
        mock_collector = MagicMock()
        mock_collector.latest_filings.return_value = [{"index_url": _FILING_INDEX_URL}]
        mock_collector.filing_documents.return_value = [
            {"name": "primary_doc.xml", "url": "https://sec.gov/primary_doc.xml"}
        ]
        mock_collector.fetch_xml.return_value = ET.fromstring(_FIXTURE_XML)

        with patch("titan.app.services.insider_service.SECEdgarCollector", return_value=mock_collector):
            with TestClient(app) as client:
                first = client.post("/insider/ingest")
                assert first.status_code == 200
                assert first.json()["inserted"] == 1

                second = client.post("/insider/ingest")
                assert second.json()["inserted"] == 0

                listed = client.get("/insider/trades", params={"ticker": "ZZZTEST"})
                assert listed.status_code == 200
                body = listed.json()
                assert len(body) == 1
                assert body[0]["direction"] == "buy"
                assert body[0]["is_officer"] is True
    finally:
        _clear_fixture_rows()
