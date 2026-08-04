from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class CongressionalTrade(Base):
    __tablename__ = "congressional_trades"

    id = Column(Integer, primary_key=True)
    chamber = Column(String, nullable=False, index=True)  # house | senate
    member = Column(String, nullable=False)
    ticker = Column(String, nullable=False, index=True)
    transaction_type = Column(String, nullable=False)  # purchase | sale
    transaction_date = Column(DateTime, nullable=False)
    disclosure_date = Column(DateTime, nullable=True)
    amount_range = Column(String, nullable=True)
    amount_midpoint_usd = Column(Float, nullable=False, default=0.0)
    source_url = Column(String, nullable=True)
    ingested_at = Column(DateTime, default=datetime.utcnow)


class InsiderTrade(Base):
    __tablename__ = "insider_trades"

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    owner_name = Column(String, nullable=False)
    is_officer = Column(Boolean, default=False)
    is_director = Column(Boolean, default=False)
    transaction_code = Column(String, nullable=False)  # P, S, A, D, ...
    direction = Column(String, nullable=False)  # buy | sell
    shares = Column(Float, nullable=False, default=0.0)
    total_value_usd = Column(Float, nullable=False, default=0.0)
    filing_url = Column(String, nullable=True)
    transaction_date = Column(DateTime, nullable=True)
    ingested_at = Column(DateTime, default=datetime.utcnow)


class SignalScore(Base):
    __tablename__ = "signal_scores"

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False)  # 0-100
    recommendation = Column(String, nullable=False)  # BUY | SELL | HOLD
    net_direction = Column(Float, nullable=False)  # -1..+1
    congress_signal_count = Column(Integer, nullable=False, default=0)
    insider_signal_count = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)
    notional_usd = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # dry_run | submitted | failed
    broker_order_id = Column(String, nullable=True)
    detail = Column(String, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
