from dataclasses import dataclass

from sqlalchemy.orm import Session

from topos.backtesting.prices import average_dollar_volume
from topos.db.models import PriceBar
from topos.signals.base import Signal

# A name has to be liquid enough that a position could actually be opened
# and closed without moving the price, and priced high enough not to be a
# sub-dollar shell. These are deliberately permissive — the goal is to
# exclude the untradeable, not to pick winners.
MIN_AVG_DOLLAR_VOLUME = 1_000_000.0
MIN_PRICE = 1.00
MIN_BARS = 20


@dataclass(frozen=True)
class LiquidityVerdict:
    ticker: str
    tradeable: bool
    reason: str
    avg_dollar_volume: float | None = None
    last_close: float | None = None


def assess(
    db: Session,
    ticker: str,
    min_dollar_volume: float = MIN_AVG_DOLLAR_VOLUME,
    min_price: float = MIN_PRICE,
    min_bars: int = MIN_BARS,
) -> LiquidityVerdict:
    """Decides whether a ticker is liquid enough to act on.

    A ticker with no stored price history is treated as NOT tradeable
    rather than given the benefit of the doubt: unknown liquidity is
    exactly the case that produced the untradeable names showing up in
    Ranked Opportunities, and a backtest run over them measures returns
    nobody could have captured.
    """
    ticker = ticker.upper()
    bar_count = db.query(PriceBar).filter(PriceBar.ticker == ticker).count()
    if bar_count < min_bars:
        return LiquidityVerdict(ticker, False, f"only {bar_count} price bars (need {min_bars})")

    last_bar = (
        db.query(PriceBar)
        .filter(PriceBar.ticker == ticker)
        .order_by(PriceBar.date.desc())
        .first()
    )
    if last_bar.close < min_price:
        return LiquidityVerdict(
            ticker, False, f"last close ${last_bar.close:.2f} below ${min_price:.2f}",
            last_close=last_bar.close,
        )

    adv = average_dollar_volume(db, ticker)
    if adv is None or adv < min_dollar_volume:
        return LiquidityVerdict(
            ticker,
            False,
            f"avg dollar volume ${adv or 0:,.0f} below ${min_dollar_volume:,.0f}",
            avg_dollar_volume=adv,
            last_close=last_bar.close,
        )

    return LiquidityVerdict(
        ticker, True, "tradeable", avg_dollar_volume=adv, last_close=last_bar.close
    )


def filter_tradeable(db: Session, tickers: list[str], **kwargs) -> tuple[list[str], list[LiquidityVerdict]]:
    """Splits tickers into tradeable ones and the verdicts that rejected
    the rest — the rejections are returned rather than swallowed so the
    pipeline can log *why* a name was dropped."""
    keep: list[str] = []
    rejected: list[LiquidityVerdict] = []
    for ticker in tickers:
        verdict = assess(db, ticker, **kwargs)
        if verdict.tradeable:
            keep.append(verdict.ticker)
        else:
            rejected.append(verdict)
    return keep, rejected


def filter_signals(db: Session, signals: list[Signal], **kwargs) -> list[Signal]:
    """Drops signals for tickers that fail the liquidity screen, assessing
    each distinct ticker once rather than once per signal."""
    verdicts = {
        ticker: assess(db, ticker, **kwargs)
        for ticker in {s.ticker.upper() for s in signals}
    }
    return [s for s in signals if verdicts[s.ticker.upper()].tradeable]
