"""The report has to tell you which formula produced the scores it grades.

59 rankings survived the migration that added `attribution`, and they were
scored by the old multiplicative formula. Bucketed silently alongside new
rows, a "70-80" from one formula sits next to a "70-80" from another and
the correlation is measured across both — a finding about nothing.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from research_report import _no_attribution, build_report, formula_mix_warning  # noqa: E402

from topos.db.models import RankedOpportunity  # noqa: E402
from topos.db.session import SessionLocal, init_db  # noqa: E402


def test_no_warning_when_every_ranking_uses_the_current_formula():
    assert formula_mix_warning(legacy=0, current=120) is None


def test_no_warning_on_an_empty_database():
    assert formula_mix_warning(legacy=0, current=0) is None


def test_mixed_formulas_are_called_out_with_their_share():
    warning = formula_mix_warning(legacy=59, current=141)

    assert "Mixed scoring formulas" in warning
    # 59/200 — the share is of all rankings, not of the current-formula ones.
    assert "30%" in warning


def test_all_legacy_says_the_results_validate_the_old_formula():
    warning = formula_mix_warning(legacy=59, current=0)

    assert "predate the additive rewrite" in warning
    assert "rather than the one now in use" in warning


@pytest.fixture
def db():
    init_db()
    session = SessionLocal()
    tickers = ["RPT01", "RPT02", "RPT03"]

    def _clean():
        session.execute(delete(RankedOpportunity).where(RankedOpportunity.ticker.in_(tickers)))
        session.commit()

    _clean()
    try:
        yield session, tickers
    finally:
        _clean()
        session.close()


def _ranking(session, ticker: str, attribution) -> None:
    session.add(
        RankedOpportunity(
            ticker=ticker, score=72.0, recommendation="BUY", net_direction=1.0,
            signal_count=1, sources=["sec_form4"], attribution=attribution,
            rank_timestamp=datetime(2026, 1, 5, 12, 0, 0),
        )
    )


def test_report_counts_rows_without_attribution_as_legacy(db):
    session, tickers = db
    sql_null, current, _ = tickers

    _ranking(session, sql_null, None)
    _ranking(session, current, {"total": 72.0, "contributions": []})
    session.commit()

    report = build_report(session, horizon=20)

    # Both kinds are present, so the mixed-formula branch must fire
    # regardless of whatever else the local database holds.
    assert "Mixed scoring formulas" in report
    assert "scored by the older (multiplicative) formula" in report


def test_json_null_attribution_counts_as_legacy_too(db):
    """A None written before `none_as_null=True` landed as a JSON `null`.

    `IS NULL` does not match that, so such a row would be counted as
    current-formula — the misclassification this split exists to prevent.
    """
    session, tickers = db
    _, _, json_null = tickers

    session.execute(
        text(
            "INSERT INTO ranked_opportunities "
            "(ticker, score, recommendation, net_direction, signal_count, "
            " sources, attribution, rank_timestamp) "
            "VALUES (:t, 72.0, 'BUY', 1.0, 1, '[\"sec_form4\"]', 'null', :ts)"
        ),
        {"t": json_null, "ts": datetime(2026, 1, 5, 12, 0, 0)},
    )
    session.commit()

    legacy = session.query(RankedOpportunity).filter(_no_attribution()).count()

    assert legacy >= 1
    assert session.query(RankedOpportunity).filter(
        RankedOpportunity.ticker == json_null
    ).filter(_no_attribution()).count() == 1


def test_the_report_survives_a_windows_console(db):
    """The report must be writable where it is actually read.

    A Greek rho in a verdict string crashed the run on Windows:
    `Path.write_text` defaults to the locale encoding, cp1252 has no
    U+03C1, and the whole report was lost at the final write. The file is
    now written as UTF-8, and this keeps the *content* within reach of a
    cp1252 console too, so `Get-Content` renders it rather than mangling
    it.
    """
    session, tickers = db
    _ranking(session, tickers[0], {"total": 72.0})
    session.commit()

    report = build_report(session, horizon=20)

    report.encode("cp1252")  # raises if a character slipped back in
