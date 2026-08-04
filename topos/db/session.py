from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from topos.config import load_settings
from topos.db.models import Base

settings = load_settings()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
