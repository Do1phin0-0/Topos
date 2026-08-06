"""Persisting a historical backfill must not depend on the batch size.

The Form 4 backfill parsed 44,435 signals and then died writing them:
`persist_signals` asked SQLite about every dedup key in one IN clause, and
SQLite caps bound parameters per statement. Hours of downloading, nothing
stored, and the failure only appears at a scale no unit test had reached.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from topos.db.models import Base
from topos.db.models import Signal as SignalRow
from topos.pipeline import _LOOKUP_CHUNK, persist_signals
from topos.signals.base import Signal


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'batch.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()


def _signals(count: int, prefix: str = "big") -> list[Signal]:
    return [
        Signal(
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            event_date=date(2026, 1, 2),
            dedup_key=f"{prefix}:{i}",
            source="sec_form4",
            ticker=f"T{i % 500:03d}",
            confidence=0.5,
            evidence={"direction": "buy"},
        )
        for i in range(count)
    ]


def test_a_batch_far_past_the_sqlite_parameter_limit_persists(session):
    # SQLite's historical ceiling is 999 parameters per statement; the real
    # backfill handed this 44,110 signals.
    signals = _signals(5000)

    inserted = persist_signals(session, signals)

    assert inserted == 5000
    assert session.query(SignalRow).count() == 5000


def test_dedup_still_holds_across_a_large_rerun(session):
    signals = _signals(2500)
    persist_signals(session, signals)

    # Re-running a backfill must recognise everything, not re-insert it.
    inserted = persist_signals(session, signals)

    assert inserted == 0
    assert session.query(SignalRow).count() == 2500


def test_a_large_batch_overlapping_stored_signals_inserts_only_the_new(session):
    persist_signals(session, _signals(2000))

    # 2000 already stored, 2000 new, in one call spanning many chunks.
    inserted = persist_signals(session, _signals(4000))

    assert inserted == 2000
    assert session.query(SignalRow).count() == 4000


def test_duplicates_inside_one_batch_are_collapsed(session):
    signals = _signals(1500) + _signals(1500)

    inserted = persist_signals(session, signals)

    assert inserted == 1500
    assert session.query(SignalRow).count() == 1500


def test_an_empty_batch_is_a_no_op(session):
    assert persist_signals(session, []) == 0


def test_no_single_query_exceeds_the_chunk_size(session):
    """The regression test proper.

    A size-based test only fails once the batch passes whatever limit the
    local SQLite build happens to have — 999 in older builds, 32,766 in
    newer ones, and the real failure came at 44,110. Asserting on the
    queries actually issued fails on the old code at any size, and on
    every dialect.
    """
    widths: list[int] = []
    real_execute = session.execute

    def spy(statement, *args, **kwargs):
        compiled = statement.compile()
        widths.append(len(compiled.params))
        return real_execute(statement, *args, **kwargs)

    session.execute = spy
    try:
        persist_signals(session, _signals(3000))
    finally:
        session.execute = real_execute

    assert widths, "no lookup query was issued"
    assert max(widths) <= _LOOKUP_CHUNK
    # And it really did split rather than silently dropping keys.
    assert len(widths) == 6  # 3000 / 500
