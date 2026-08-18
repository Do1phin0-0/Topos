"""Topos must run its research on a plain file, with no server involved.

The deployed dashboard uses Postgres, but validation is local work, and
tying it to a remote database means a VPN or a firewall can block a
question about a scoring model. Every research path therefore has to work
against SQLite — which is a real constraint on the code, not a preference:
`JSON(none_as_null=True)`, the attribution NULL/JSON-null query, and the
score-bucket aggregation all have to stay dialect-neutral.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from research_report import build_report, _no_attribution  # noqa: E402

from topos.backtesting.prices import backfill_ticker  # noqa: E402
from topos.backtesting.research import score_return_correlation  # noqa: E402
from topos.collectors.prices import Bar  # noqa: E402
from topos.db.models import Base, RankedOpportunity  # noqa: E402
from topos.db.models import Signal as SignalRow  # noqa: E402

_START = date(2026, 1, 5)


class _Stub:
    def __init__(self, closes):
        self._closes = closes

    def daily_bars(self, ticker):
        return [
            Bar(date=_START + timedelta(days=i), open=c, high=c, low=c, close=c, volume=2e6)
            for i, c in enumerate(self._closes)
        ]


@pytest.fixture
def sqlite_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'topos.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _populate(session, count: int = 40) -> None:
    import random

    rng = random.Random(4)
    for index in range(count):
        ticker = f"SQ{index:02d}"
        score = 25.0 + index * 1.8
        drift = (score - 60) / 60 * 0.004
        price, closes = 100.0, []
        for _ in range(40):
            price *= 1 + drift + rng.gauss(0, 0.002)
            closes.append(round(price, 2))
        backfill_ticker(db=session, ticker=ticker, collector=_Stub(closes))
        session.add(
            SignalRow(
                ticker=ticker, source="congress_house", confidence=0.6, evidence={},
                dedup_key=f"sqlite-{ticker}", event_date=_START,
                timestamp=datetime(2026, 1, 5, 12, 0, 0),
            )
        )
        session.add(
            RankedOpportunity(
                ticker=ticker, score=score, recommendation="BUY", net_direction=1.0,
                signal_count=1, sources=["congress_house"],
                # Half with attribution, half without, so the formula split
                # is exercised on this dialect too.
                attribution=None if index < count // 2 else {"total": score},
                rank_timestamp=datetime(2026, 1, 5, 12, 0, 0),
            )
        )
    session.commit()


def test_the_schema_builds_on_sqlite(sqlite_session):
    assert sqlite_session.query(SignalRow).count() == 0
    assert sqlite_session.query(RankedOpportunity).count() == 0


def test_the_full_research_report_runs_on_sqlite(sqlite_session):
    _populate(sqlite_session)

    report = build_report(sqlite_session, horizon=20)

    assert "Signal validation research report" in report
    assert "No data to analyse" not in report
    # The planted relationship should come through the statistics intact.
    assert "POSITIVE" in report


def test_attribution_null_detection_works_on_sqlite(sqlite_session):
    # `cast(json_column AS VARCHAR)` is the part most likely to differ
    # between dialects, and it decides which scoring formula a row used.
    _populate(sqlite_session, count=10)

    legacy = sqlite_session.query(RankedOpportunity).filter(_no_attribution()).count()

    assert legacy == 5


def test_forward_return_correlation_works_on_sqlite(sqlite_session):
    _populate(sqlite_session)

    result = score_return_correlation(sqlite_session, horizon_days=20)

    assert result.n == 40
    assert result.spearman > 0.5
