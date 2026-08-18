import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from topos.config import load_settings
from topos.db.models import Base, Signal

logger = logging.getLogger(__name__)

settings = load_settings()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate_signal_external_id()


def _migrate_signal_external_id() -> None:
    """Additive, idempotent migration for databases created before the
    `external_id` dedup column existed. Safe to call on every startup:
    every step checks first and never touches existing rows, so it's a
    no-op once applied. This is a stopgap for a single-table schema tweak
    on a personal project's DB, not a substitute for real migrations if
    the schema keeps growing — Alembic would be the next step for that."""
    inspector = inspect(engine)
    if "signals" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("signals")}
    if "external_id" not in columns:
        logger.info("migrating signals table: adding external_id column")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE signals ADD COLUMN external_id VARCHAR"))
    for index in Signal.__table__.indexes:
        index.create(engine, checkfirst=True)
