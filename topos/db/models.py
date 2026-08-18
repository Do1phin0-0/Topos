from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_signals_dedup_key"),)

    id = Column(Integer, primary_key=True)
    # When we observed the signal.
    timestamp = Column(DateTime, nullable=False)
    # When the underlying event actually happened — what backtesting
    # measures forward returns from.
    event_date = Column(Date, nullable=False, index=True)
    # Stable natural identity, so repeat ingestion doesn't duplicate.
    dedup_key = Column(String, nullable=False)
    source = Column(String, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    evidence = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RankedOpportunity(Base):
    __tablename__ = "ranked_opportunities"

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False)  # 0-100
    recommendation = Column(String, nullable=False)  # BUY | SELL | HOLD
    net_direction = Column(Float, nullable=False)  # -1 (all sell) .. +1 (all buy)
    signal_count = Column(Integer, nullable=False)
    sources = Column(JSON, nullable=False)
    # Additive derivation of the score (contributions, bonuses,
    # penalties). Nullable so it can be added to an existing deployment
    # without discarding ranking history, which is the backtester's
    # sample — rows predating attribution simply have none.
    #
    # none_as_null=True because the default writes Python None as a JSON
    # `null` *value*, not SQL NULL — two representations of "no
    # attribution" that `IS NULL` cannot both find, which would silently
    # misclassify rows when telling old scores apart from new ones.
    attribution = Column(JSON(none_as_null=True), nullable=True)
    rank_timestamp = Column(DateTime, default=datetime.utcnow)


class PriceBar(Base):
    """Cached daily OHLCV history. Backtesting needs to look up "what was
    this ticker's price on date X" and "what did it do for the N days
    after" — that can't come from a live API call at scoring time, so
    bars are stored once and reused."""

    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_price_bars_ticker_date"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow)


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
