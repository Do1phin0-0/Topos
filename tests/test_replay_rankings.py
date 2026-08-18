"""Replayed rankings must be point-in-time, or they validate nothing.

The dangerous failure modes are quiet ones: a snapshot seeing signals
from its own future, staleness measured against today instead of the
snapshot date, or a re-run doubling the sample. Each would make the
score look better or worse for reasons that have nothing to do with the
score.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from topos.backtesting.replay import replay_rankings, snapshot_dates
from topos.db.models import Base, RankedOpportunity
from topos.db.models import Signal as SignalRow


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'replay.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()


def _signal(db, ticker: str, event: date, source: str = "congress_house",
            direction: str = "buy", confidence: float = 0.6) -> None:
    db.add(
        SignalRow(
            ticker=ticker, source=source, confidence=confidence,
            evidence={"direction": direction},
            dedup_key=f"replay:{source}:{ticker}:{event}:{direction}:{confidence}",
            event_date=event, timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
    )


def test_snapshot_dates_step_through_the_range():
    dates = snapshot_dates(date(2026, 1, 1), date(2026, 3, 1), step_days=28)

    assert dates == [date(2026, 1, 1), date(2026, 1, 29), date(2026, 2, 26)]


def test_a_snapshot_never_sees_signals_from_its_own_future(session):
    _signal(session, "AAPL", date(2026, 1, 10))
    _signal(session, "MSFT", date(2026, 2, 20))  # after the first snapshot
    session.commit()

    replay_rankings(
        session, since=date(2026, 1, 15), until=date(2026, 1, 15), step_days=28
    )

    tickers = {r.ticker for r in session.query(RankedOpportunity).all()}
    assert tickers == {"AAPL"}


def test_stale_signals_age_out_of_later_snapshots(session):
    # 90-day staleness horizon: a January filing is fresh in February and
    # gone by June. If it appeared in the June snapshot, staleness would
    # be measured against the wrong clock.
    _signal(session, "AAPL", date(2026, 1, 10))
    session.commit()

    replay_rankings(
        session, since=date(2026, 2, 1), until=date(2026, 2, 1), step_days=28
    )
    replay_rankings(
        session, since=date(2026, 6, 1), until=date(2026, 6, 1), step_days=28
    )

    by_stamp = {}
    for row in session.query(RankedOpportunity).all():
        by_stamp.setdefault(row.rank_timestamp.date(), []).append(row.ticker)
    assert by_stamp == {date(2026, 2, 1): ["AAPL"]}


def test_rankings_carry_the_snapshot_date_not_today(session):
    _signal(session, "AAPL", date(2026, 1, 10))
    session.commit()

    replay_rankings(
        session, since=date(2026, 1, 15), until=date(2026, 1, 15), step_days=28
    )

    row = session.query(RankedOpportunity).one()
    assert row.rank_timestamp.date() == date(2026, 1, 15)
    # Replayed rows are current-formula rows: attribution present.
    assert row.attribution is not None


def test_rerunning_a_window_replaces_rows_instead_of_doubling_them(session):
    _signal(session, "AAPL", date(2026, 1, 10))
    _signal(session, "MSFT", date(2026, 1, 12))
    session.commit()

    first = replay_rankings(
        session, since=date(2026, 1, 15), until=date(2026, 1, 15), step_days=28
    )
    second = replay_rankings(
        session, since=date(2026, 1, 15), until=date(2026, 1, 15), step_days=28
    )

    assert first.rankings_written == 2
    assert second.rankings_replaced == 2
    assert session.query(RankedOpportunity).count() == 2


def test_replay_does_not_touch_live_pipeline_rankings(session):
    # A live ranking from the same day, stamped at wall-clock time.
    session.add(
        RankedOpportunity(
            ticker="LIVE", score=70.0, recommendation="HOLD", net_direction=1.0,
            signal_count=1, sources=["sec_form4"], attribution={"total": 70.0},
            rank_timestamp=datetime(2026, 1, 15, 14, 32, 11),
        )
    )
    _signal(session, "AAPL", date(2026, 1, 10))
    session.commit()

    replay_rankings(
        session, since=date(2026, 1, 15), until=date(2026, 1, 15), step_days=28
    )
    replay_rankings(
        session, since=date(2026, 1, 15), until=date(2026, 1, 15), step_days=28
    )

    assert session.query(RankedOpportunity).filter_by(ticker="LIVE").count() == 1


def test_multi_source_agreement_scores_above_single_source(session):
    # The property the whole validation wants to interrogate must at
    # least be present in the replayed data: same-direction corroboration
    # scores higher than one source alone.
    _signal(session, "SOLO", date(2026, 1, 10))
    _signal(session, "BOTH", date(2026, 1, 10))
    _signal(session, "BOTH", date(2026, 1, 11), source="sec_form4")
    session.commit()

    replay_rankings(
        session, since=date(2026, 1, 15), until=date(2026, 1, 15), step_days=28
    )

    scores = {r.ticker: r.score for r in session.query(RankedOpportunity).all()}
    assert scores["BOTH"] > scores["SOLO"]
