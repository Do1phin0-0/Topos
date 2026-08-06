from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from topos.collectors.prices import PriceCollector
from topos.db.models import PriceBar

# The default yardstick. A strategy that returns +3% while SPY returns
# +4% is losing money in the only sense that matters.
BENCHMARK_TICKER = "SPY"


def backfill_ticker(db: Session, ticker: str, collector: PriceCollector | None = None) -> int:
    """Fetches daily history for a ticker and stores any bars we don't
    already have. Returns the number of new bars inserted."""
    collector = collector or PriceCollector()
    ticker = ticker.upper()

    bars = collector.daily_bars(ticker)
    if not bars:
        return 0

    existing = {
        row[0]
        for row in db.execute(select(PriceBar.date).where(PriceBar.ticker == ticker)).all()
    }

    inserted = 0
    for bar in bars:
        if bar.date in existing:
            continue
        db.add(
            PriceBar(
                ticker=ticker,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )
        inserted += 1

    db.commit()
    return inserted


def backfill_tickers(
    db: Session, tickers: list[str], collector: PriceCollector | None = None
) -> dict[str, int]:
    """Backfills several tickers. One ticker failing (delisted, unknown
    symbol, upstream hiccup) must not abort the rest of the run."""
    collector = collector or PriceCollector()
    results: dict[str, int] = {}
    for ticker in tickers:
        try:
            results[ticker] = backfill_ticker(db, ticker, collector=collector)
        except Exception as exc:
            print(f"[warn] price backfill failed for {ticker}: {exc}")
            results[ticker] = 0
    return results


def get_bars(db: Session, ticker: str, since: date | None = None) -> list[PriceBar]:
    """Stored bars for a ticker, oldest first."""
    query = db.query(PriceBar).filter(PriceBar.ticker == ticker.upper())
    if since is not None:
        query = query.filter(PriceBar.date >= since)
    return query.order_by(PriceBar.date).all()


def forward_return(
    db: Session, ticker: str, from_date: date, horizon_trading_days: int
) -> float | None:
    """Return over the N trading days following `from_date`.

    Entry is the first bar on or after `from_date` — a signal dated on a
    weekend or holiday is entered at the next open session, which is what
    could actually have been traded. Horizons are counted in trading days
    (bar offsets), not calendar days, so a 5-day horizon is one market
    week rather than a window that may land on no data at all.

    Returns None when there isn't enough history to measure the full
    horizon, rather than a partial or fabricated number — an unmeasurable
    signal must not be silently scored as a flat 0% result.
    """
    bars = get_bars(db, ticker, since=from_date)
    if len(bars) <= horizon_trading_days:
        return None

    entry = bars[0]
    exit_bar = bars[horizon_trading_days]
    if entry.close <= 0:
        return None

    return (exit_bar.close - entry.close) / entry.close


def excess_forward_return(
    db: Session,
    ticker: str,
    from_date: date,
    horizon_trading_days: int,
    benchmark: str = BENCHMARK_TICKER,
) -> float | None:
    """Forward return *minus* the benchmark's over the same window.

    Absolute returns cannot answer the question this project asks. Over 60
    trading days of a rising market, every bucket earns roughly +3% and the
    score looks like it works; measured against the index, the same +3%
    may be a loss. A signal is only worth acting on if it beats buying
    SPY and doing nothing.

    Returns None when either leg is unmeasurable — including when the
    benchmark has no stored history. Silently falling back to the absolute
    return would relabel beta as alpha, which is the exact error this
    exists to prevent.
    """
    asset = forward_return(db, ticker, from_date, horizon_trading_days)
    if asset is None:
        return None

    market = forward_return(db, benchmark, from_date, horizon_trading_days)
    if market is None:
        return None

    return asset - market


def has_benchmark_history(db: Session, benchmark: str = BENCHMARK_TICKER) -> bool:
    """Whether benchmark bars are stored at all — so a report can say
    'no benchmark' rather than quietly reporting nothing."""
    return (
        db.query(PriceBar.id).filter(PriceBar.ticker == benchmark.upper()).first()
        is not None
    )


def average_dollar_volume(
    db: Session, ticker: str, lookback_bars: int = 20
) -> float | None:
    """Mean daily dollar volume (close x volume) over the most recent
    bars — the liquidity measure used to screen out untradeable tickers.

    Dollar volume rather than raw share volume: 10M shares of a $0.30
    stock is not the same tradeable liquidity as 100k shares of a $200
    stock, and raw share counts would rank the penny stock higher.
    """
    bars = (
        db.query(PriceBar)
        .filter(PriceBar.ticker == ticker.upper())
        .order_by(PriceBar.date.desc())
        .limit(lookback_bars)
        .all()
    )
    if not bars:
        return None
    return sum(bar.close * bar.volume for bar in bars) / len(bars)
