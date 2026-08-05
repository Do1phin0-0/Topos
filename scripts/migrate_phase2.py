"""Migrates an existing database to the Phase 2 signals schema.

Phase 2 added `event_date` and `dedup_key` to `signals` (both NOT NULL,
with a unique constraint on dedup_key). SQLAlchemy's create_all() only
creates missing *tables* — it will not add columns to a table that
already exists, so a deployed database silently keeps the old schema and
the next pipeline run fails with "column event_date does not exist".

Existing rows can't be migrated forward in any meaningful way: they were
stamped with scrape time rather than event time, and the same filing was
re-inserted on every scheduled run, so they're both mis-dated and
duplicated. They're unusable for backtesting, which is the entire point
of the new columns. This drops and recreates the table rather than
inventing event dates for rows whose real dates were never recorded.

    python scripts/migrate_phase2.py            # report what needs doing
    python scripts/migrate_phase2.py --apply    # actually do it
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from topos.db.models import Base, Signal
from topos.db.session import SessionLocal, engine, init_db

_REQUIRED = {"event_date", "dedup_key"}


def _existing_columns() -> set[str] | None:
    inspector = inspect(engine)
    if "signals" not in inspector.get_table_names():
        return None
    return {col["name"] for col in inspector.get_columns("signals")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate to the Phase 2 signals schema.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Drop and recreate `signals`. Without this, only reports status.",
    )
    args = parser.parse_args()

    columns = _existing_columns()

    if columns is None:
        print("No `signals` table yet — creating the current schema.")
        init_db()
        print("Done.")
        return

    missing = _REQUIRED - columns
    if not missing:
        print("`signals` is already on the Phase 2 schema. Nothing to do.")
        return

    session = SessionLocal()
    try:
        row_count = session.execute(text("SELECT COUNT(*) FROM signals")).scalar() or 0
    finally:
        session.close()

    print(f"`signals` is missing: {', '.join(sorted(missing))}")
    print(f"It currently holds {row_count} row(s).")
    print(
        "\nThose rows were dated by scrape time, not event time, and repeat\n"
        "pipeline runs duplicated them — they can't support backtesting and\n"
        "can't be migrated forward, because their real event dates were\n"
        "never recorded."
    )

    if not args.apply:
        print("\nRe-run with --apply to drop and recreate the table.")
        return

    print("\nDropping and recreating `signals`...")
    Signal.__table__.drop(engine, checkfirst=True)
    Base.metadata.create_all(engine)

    columns = _existing_columns() or set()
    if _REQUIRED - columns:
        print("FAILED: new columns still missing after recreate.")
        raise SystemExit(1)
    print("Done — `signals` is on the Phase 2 schema.")


if __name__ == "__main__":
    main()
