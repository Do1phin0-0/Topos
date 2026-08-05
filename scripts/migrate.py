"""Brings an existing database up to the current schema.

SQLAlchemy's create_all() only creates missing *tables*. It will not add
columns to a table that already exists, so a deployed database silently
keeps an old schema and the next pipeline run fails mid-flight with
"column ... does not exist".

Two changes need applying, and they're handled differently on purpose:

`signals` gained event_date and dedup_key as NOT NULL. Existing rows
can't be migrated forward — they were stamped with scrape time rather
than event time and duplicated on every scheduled run, so their real
event dates were never recorded and can't be reconstructed. The table is
dropped and recreated.

`ranked_opportunities` gained a nullable `attribution` column. That table
is the backtester's entire sample, so it is ALTERed in place and the
history is preserved; rows predating attribution simply have none.

    python scripts/migrate.py            # report what needs doing
    python scripts/migrate.py --apply    # apply it
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from topos.db.models import Base, Signal
from topos.db.session import SessionLocal, engine, init_db

_SIGNALS_REQUIRED = {"event_date", "dedup_key"}
_RANKED_REQUIRED = {"attribution"}


def _columns(table: str) -> set[str] | None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def _row_count(table: str) -> int:
    session = SessionLocal()
    try:
        return session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
    except Exception:
        return 0
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Topos to the current schema.")
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes. Without this, only reports."
    )
    args = parser.parse_args()

    init_db()  # creates anything entirely missing; never alters existing tables

    signals_cols = _columns("signals")
    ranked_cols = _columns("ranked_opportunities")

    signals_missing = (_SIGNALS_REQUIRED - signals_cols) if signals_cols else set()
    ranked_missing = (_RANKED_REQUIRED - ranked_cols) if ranked_cols else set()

    if not signals_missing and not ranked_missing:
        print("Database is already on the current schema. Nothing to do.")
        return

    if signals_missing:
        count = _row_count("signals")
        print(f"`signals` is missing: {', '.join(sorted(signals_missing))}")
        print(f"  {count} row(s) present — these will be DISCARDED.")
        print(
            "  They were dated by scrape time, not event time, and repeat runs\n"
            "  duplicated them, so they cannot support backtesting and their\n"
            "  real event dates were never recorded."
        )

    if ranked_missing:
        count = _row_count("ranked_opportunities")
        print(f"`ranked_opportunities` is missing: {', '.join(sorted(ranked_missing))}")
        print(f"  {count} row(s) present — these will be PRESERVED (added as a nullable column).")

    if not args.apply:
        print("\nRe-run with --apply to make these changes.")
        return

    if signals_missing:
        print("\nDropping and recreating `signals`...")
        Signal.__table__.drop(engine, checkfirst=True)
        Base.metadata.create_all(engine)

    if ranked_missing:
        print("Adding `attribution` to `ranked_opportunities` (preserving rows)...")
        with engine.begin() as connection:
            for column in sorted(ranked_missing):
                connection.execute(
                    text(f"ALTER TABLE ranked_opportunities ADD COLUMN IF NOT EXISTS {column} JSON")
                )

    remaining_signals = (_SIGNALS_REQUIRED - (_columns("signals") or set()))
    remaining_ranked = (_RANKED_REQUIRED - (_columns("ranked_opportunities") or set()))
    if remaining_signals or remaining_ranked:
        print(f"FAILED — still missing: {remaining_signals | remaining_ranked}")
        raise SystemExit(1)

    print("Done — database is on the current schema.")


if __name__ == "__main__":
    from _cli import run

    run(main)
