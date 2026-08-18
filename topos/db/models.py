from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    source = Column(String, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    evidence = Column(JSON, nullable=False)
    # Stable per-source id (filing URL, PTR link, ...) used to dedupe
    # re-collected records across pipeline runs. Nullable for sources that
    # can't produce one.
    external_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("uq_signals_source_external_id", "source", "external_id", unique=True),
    )


class RankedOpportunity(Base):
    __tablename__ = "ranked_opportunities"

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False)
    signal_count = Column(Integer, nullable=False)
    sources = Column(JSON, nullable=False)
    rank_timestamp = Column(DateTime, default=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)
    weight = Column(Float, nullable=False)
    notional_usd = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    broker_order_id = Column(String, nullable=True)
    detail = Column(String, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
