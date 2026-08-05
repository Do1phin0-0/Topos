"""The point-in-time guarantees backtesting depends on.

Every signal must be dated by when its underlying event happened, not by
when the scraper ran, and repeat ingestion must not duplicate. Both were
broken before Phase 2 and both silently corrupt forward-return
measurement, so they're pinned here.
"""

import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete, select

from topos.db.models import Signal as SignalRow
from topos.db.session import SessionLocal, init_db
from topos.pipeline import persist_signals
from topos.signals.base import Signal
from topos.signals.congress import extract_congress_signal
from topos.signals.form4 import extract_form4_signal

_FORM4_TEMPLATE = """<?xml version="1.0"?>
<ownershipDocument>
  {period}
  <issuer><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><isDirector>0</isDirector></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      {txn_date}
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>42.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def _form4(txn_date: str = "", period: str = "") -> ET.Element:
    return ET.fromstring(_FORM4_TEMPLATE.format(txn_date=txn_date, period=period))


def test_form4_dates_the_insider_trade_not_the_scrape():
    root = _form4(txn_date="<transactionDate><value>2026-07-15</value></transactionDate>")

    signal = extract_form4_signal(root, "https://example.com/a-index.htm")

    assert signal.event_date == date(2026, 7, 15)
    # The whole point: the event date must not drift to whenever we ran.
    assert signal.event_date != datetime.now(timezone.utc).date()


def test_form4_uses_earliest_transaction_when_filing_reports_several():
    xml = _FORM4_TEMPLATE.format(
        period="",
        txn_date="<transactionDate><value>2026-07-20</value></transactionDate>",
    ).replace(
        "</nonDerivativeTable>",
        """<nonDerivativeTransaction>
      <transactionDate><value>2026-07-11</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>10.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction></nonDerivativeTable>""",
    )

    signal = extract_form4_signal(ET.fromstring(xml), "https://example.com/a-index.htm")

    assert signal.event_date == date(2026, 7, 11)


def test_form4_falls_back_to_period_of_report():
    root = _form4(period="<periodOfReport>2026-06-30</periodOfReport>")

    signal = extract_form4_signal(root, "https://example.com/a-index.htm")

    assert signal.event_date == date(2026, 6, 30)


def test_form4_drops_a_filing_it_cannot_date():
    # Rather than backdating to today, which would make any forward return
    # measured from it meaningless.
    assert extract_form4_signal(_form4(), "https://example.com/a-index.htm") is None


def test_form4_dedup_key_is_the_filing():
    root = _form4(txn_date="<transactionDate><value>2026-07-15</value></transactionDate>")

    signal = extract_form4_signal(root, "https://example.com/a-index.htm")

    assert signal.dedup_key == "sec_form4:https://example.com/a-index.htm"


def test_congress_dates_the_trade_not_the_scrape():
    signal = extract_congress_signal(
        {
            "ticker": "NVDA",
            "type": "purchase",
            "amount": "$100,001 - $250,000",
            "representative": "Jane Rep",
            "chamber": "house",
            "transaction_date": "2026-07-15",
        }
    )

    assert signal.event_date == date(2026, 7, 15)
    assert "2026-07-15" in signal.dedup_key


def test_congress_drops_an_undateable_record():
    assert (
        extract_congress_signal(
            {"ticker": "NVDA", "type": "purchase", "transaction_date": "not-a-date"}
        )
        is None
    )


def _signal(dedup_key: str, ticker: str = "ZZZTEST") -> Signal:
    return Signal(
        timestamp=datetime.now(timezone.utc),
        event_date=date(2026, 7, 1),
        dedup_key=dedup_key,
        source="sec_form4",
        ticker=ticker,
        confidence=0.5,
        evidence={"direction": "buy"},
    )


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    session.execute(delete(SignalRow).where(SignalRow.ticker == "ZZZTEST"))
    session.commit()
    try:
        yield session
    finally:
        session.execute(delete(SignalRow).where(SignalRow.ticker == "ZZZTEST"))
        session.commit()
        session.close()


def _stored_count(db) -> int:
    return len(db.execute(select(SignalRow.id).where(SignalRow.ticker == "ZZZTEST")).all())


def test_persist_signals_does_not_duplicate_across_runs(db):
    batch = [_signal("sec_form4:filing-a"), _signal("sec_form4:filing-b")]

    assert persist_signals(db, batch) == 2
    # The scheduled pipeline sees the same filings again on the next run.
    assert persist_signals(db, batch) == 0
    assert _stored_count(db) == 2


def test_persist_signals_does_not_duplicate_within_one_batch(db):
    # Two sources can surface the same filing in a single run.
    batch = [_signal("sec_form4:filing-a"), _signal("sec_form4:filing-a")]

    assert persist_signals(db, batch) == 1
    assert _stored_count(db) == 1


def test_persist_signals_stores_the_event_date(db):
    persist_signals(db, [_signal("sec_form4:filing-a")])

    row = db.query(SignalRow).filter(SignalRow.ticker == "ZZZTEST").one()
    assert row.event_date == date(2026, 7, 1)


def test_persist_signals_adds_genuinely_new_signals(db):
    persist_signals(db, [_signal("sec_form4:filing-a")])

    inserted = persist_signals(
        db, [_signal("sec_form4:filing-a"), _signal("sec_form4:filing-c")]
    )

    assert inserted == 1
    assert _stored_count(db) == 2
