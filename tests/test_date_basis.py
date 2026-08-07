"""Transaction date and disclosure date answer different questions.

The STOCK Act allows up to 45 days between a member trading and the
filing becoming public. Dating a signal by the transaction asks whether
the trade was informed — nobody outside Congress could act on that date.
Dating by disclosure asks whether *following* Congress works, which is
the only question a bot cares about.

The first validation run measured the informational question and was
read as if it answered the tradeable one.
"""

import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from backfill_congress import drop_other_basis  # noqa: E402

from topos.db.models import Base  # noqa: E402
from topos.db.models import Signal as SignalRow  # noqa: E402
from topos.pipeline import persist_signals  # noqa: E402
from topos.signals.congress import extract_congress_signal  # noqa: E402

RECORD = {
    "ticker": "AAPL",
    "type": "purchase",
    "amount": "$1,001 - $15,000",
    "representative": "Jane Doe",
    "transaction_date": "2024-01-02",
    "disclosure_date": "2024-02-14",  # 43 days later, within the STOCK Act window
    "chamber": "house",
}


def test_transaction_basis_dates_the_trade():
    signal = extract_congress_signal(RECORD, "transaction")

    assert signal.event_date == date(2024, 1, 2)
    assert signal.evidence["date_basis"] == "transaction"


def test_disclosure_basis_dates_the_filing():
    signal = extract_congress_signal(RECORD, "disclosure")

    assert signal.event_date == date(2024, 2, 14)
    assert signal.evidence["date_basis"] == "disclosure"


def test_the_default_is_unchanged():
    # Every existing signal in the database was built this way; changing
    # the default would silently reinterpret them.
    assert extract_congress_signal(RECORD).event_date == date(2024, 1, 2)


def test_disclosure_basis_never_falls_back_to_the_transaction_date():
    """The fallback would be worse than dropping the row.

    A record with no disclosure date, silently dated by its transaction,
    would sit in a disclosure-basis run claiming to be tradeable when
    nobody could have traded it — mixing the two questions inside one
    column with no way to tell which rows are which.
    """
    undisclosed = {**RECORD, "disclosure_date": None}

    assert extract_congress_signal(undisclosed, "disclosure") is None
    # The transaction basis still accepts it, since it has what it needs.
    assert extract_congress_signal(undisclosed, "transaction") is not None


def test_the_two_bases_produce_different_identities():
    # Otherwise a disclosure-dated backfill would dedup against the
    # transaction-dated rows and silently store nothing.
    transaction = extract_congress_signal(RECORD, "transaction")
    disclosure = extract_congress_signal(RECORD, "disclosure")

    assert transaction.dedup_key != disclosure.dedup_key


# --- keeping one basis in the database at a time ----------------------


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'basis.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()


def _ingest(session, basis: str) -> None:
    records = [
        {**RECORD, "ticker": t, "transaction_date": f"2024-01-{d:02d}",
         "disclosure_date": f"2024-02-{d:02d}"}
        for d, t in enumerate(["AAPL", "MSFT", "NVDA"], start=2)
    ]
    persist_signals(
        session, [extract_congress_signal(r, basis) for r in records]
    )


def test_switching_basis_removes_the_old_dating(session):
    _ingest(session, "transaction")
    assert session.query(SignalRow).count() == 3

    removed = drop_other_basis(session, "disclosure")
    _ingest(session, "disclosure")

    assert removed == 3
    rows = session.query(SignalRow).all()
    assert len(rows) == 3
    assert {r.evidence["date_basis"] for r in rows} == {"disclosure"}


def test_the_same_disclosure_never_appears_twice_under_two_dates(session):
    """The hazard this guards against.

    Both datings of one trade would put the same disclosure into a
    snapshot twice, on two different dates, doubling its weight in the
    signal count and dragging the staleness penalty around.
    """
    _ingest(session, "transaction")
    drop_other_basis(session, "disclosure")
    _ingest(session, "disclosure")

    aapl = session.query(SignalRow).filter(SignalRow.ticker == "AAPL").all()
    assert len(aapl) == 1


def test_dropping_is_a_no_op_when_the_basis_already_matches(session):
    _ingest(session, "transaction")

    assert drop_other_basis(session, "transaction") == 0
    assert session.query(SignalRow).count() == 3


def test_signals_from_other_sources_are_untouched(session):
    session.add(
        SignalRow(
            ticker="AAPL", source="sec_form4", confidence=0.7,
            evidence={"direction": "buy"}, dedup_key="form4:keep-me",
            event_date=date(2024, 1, 2), timestamp=datetime(2024, 1, 2, 12),
        )
    )
    session.commit()
    _ingest(session, "transaction")

    drop_other_basis(session, "disclosure")

    assert session.query(SignalRow).filter_by(source="sec_form4").count() == 1


def test_legacy_rows_without_a_basis_count_as_transaction_dated(session):
    # Rows stored before this flag existed carry no date_basis in their
    # evidence; they were all dated by transaction.
    session.add(
        SignalRow(
            ticker="AAPL", source="congress_house", confidence=0.3,
            evidence={"direction": "buy"}, dedup_key="congress:legacy",
            event_date=date(2024, 1, 2), timestamp=datetime(2024, 1, 2, 12),
        )
    )
    session.commit()

    assert drop_other_basis(session, "transaction") == 0
    assert drop_other_basis(session, "disclosure") == 1
