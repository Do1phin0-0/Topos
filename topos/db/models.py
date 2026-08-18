from datetime import datetime

from sqlalchemy import JSON, Column, Date, DateTime, Float, Integer, String, UniqueConstraint
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


class Filing13FHolding(Base):
    """A single issuer position from a fund's 13F-HR, one row per
    (filer, period, cusip). Kept around so the next quarter's filing can be
    diffed against it — 13F itself has no concept of "change", just a
    snapshot of holdings as of the period end."""

    __tablename__ = "filing_13f_holdings"
    __table_args__ = (
        UniqueConstraint("filer_cik", "period_of_report", "cusip", name="uq_13f_filer_period_cusip"),
    )

    id = Column(Integer, primary_key=True)
    filer_cik = Column(String, nullable=False, index=True)
    filer_name = Column(String, nullable=False)
    period_of_report = Column(Date, nullable=False, index=True)
    cusip = Column(String, nullable=False, index=True)
    name_of_issuer = Column(String, nullable=False)
    shares = Column(Float, nullable=False)
    value_usd = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
