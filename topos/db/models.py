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


class Filing13FPosition(Base):
    """Latest known holding snapshot per (filer CIK, CUSIP). 13F-HR filings
    only change quarterly, so each pipeline run diffs the newly parsed
    filing against this table to find new/closed/materially-changed
    positions, then updates it in place — this table is a cursor, not a
    history log."""

    __tablename__ = "filing_13f_positions"

    id = Column(Integer, primary_key=True)
    cik = Column(String, nullable=False, index=True)
    filer_name = Column(String, nullable=False)
    cusip = Column(String, nullable=False, index=True)
    name_of_issuer = Column(String, nullable=True)
    filed_at = Column(String, nullable=False)
    shares = Column(Float, nullable=False)
    value_usd = Column(Float, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("uq_13f_position_cik_cusip", "cik", "cusip", unique=True),
    )


class CusipTickerCache(Base):
    """Permanent cache of CUSIP -> ticker resolutions. A CUSIP that fails
    to resolve is cached too (ticker=None) so it isn't re-queried forever."""

    __tablename__ = "cusip_ticker_cache"

    cusip = Column(String, primary_key=True)
    ticker = Column(String, nullable=True)
    resolved_at = Column(DateTime, default=datetime.utcnow)
