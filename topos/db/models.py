from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String
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
    created_at = Column(DateTime, default=datetime.utcnow)


class RankedOpportunity(Base):
    __tablename__ = "ranked_opportunities"

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False)
    signal_count = Column(Integer, nullable=False)
    sources = Column(JSON, nullable=False)
    rank_timestamp = Column(DateTime, default=datetime.utcnow)
