from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from topos.db.models import Base, Signal as SignalRow
from topos.pipeline import _persist_signals
from topos.signals.base import Signal


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_persist_signals_skips_duplicates_across_runs():
    """An hourly cron re-collecting the same filings must not keep
    inserting duplicate rows for the same underlying filing."""
    session = _make_session()
    signal = Signal(
        timestamp=datetime.now(timezone.utc),
        source="sec_form4",
        ticker="AAPL",
        confidence=0.5,
        external_id="https://sec.gov/filing/123",
    )

    first = _persist_signals(session, [signal])
    second = _persist_signals(session, [signal])

    assert first == 1
    assert second == 0
    assert session.query(SignalRow).count() == 1


def test_persist_signals_inserts_unkeyed_signals_every_time():
    session = _make_session()
    signal = Signal(
        timestamp=datetime.now(timezone.utc),
        source="unknown_source",
        ticker="AAPL",
        confidence=0.5,
    )

    _persist_signals(session, [signal])
    _persist_signals(session, [signal])

    assert session.query(SignalRow).count() == 2


def test_persist_signals_distinguishes_by_source():
    session = _make_session()
    shared_id = "https://example.com/ptr.pdf"
    house = Signal(
        timestamp=datetime.now(timezone.utc),
        source="congress_house",
        ticker="AAPL",
        confidence=0.5,
        external_id=shared_id,
    )
    senate = Signal(
        timestamp=datetime.now(timezone.utc),
        source="congress_senate",
        ticker="AAPL",
        confidence=0.5,
        external_id=shared_id,
    )

    inserted = _persist_signals(session, [house, senate])

    assert inserted == 2
    assert session.query(SignalRow).count() == 2
