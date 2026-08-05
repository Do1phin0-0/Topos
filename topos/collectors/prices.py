import csv
import io
from dataclasses import dataclass
from datetime import date, datetime

import requests

STOOQ_URL = "https://stooq.com/q/d/l/"


@dataclass(frozen=True)
class Bar:
    """One daily OHLCV bar."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_stooq_csv(text: str) -> list[Bar]:
    """Parses Stooq's daily CSV export into bars, oldest first.

    Stooq returns a plain-text error body (not a CSV) for unknown symbols,
    and occasionally emits rows with 'N/D' in place of a value — both are
    skipped rather than raising, so one bad ticker can't abort a backfill.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Date" not in reader.fieldnames:
        return []

    bars: list[Bar] = []
    for row in reader:
        try:
            bars.append(
                Bar(
                    date=datetime.strptime(row["Date"], "%Y-%m-%d").date(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda b: b.date)
    return bars


class PriceCollector:
    """Free daily OHLCV history via Stooq's public CSV export, no API key
    required. Stooq tickers for US equities are '<symbol>.us'."""

    def daily_bars(self, ticker: str) -> list[Bar]:
        """Full available daily history, oldest first."""
        response = requests.get(
            STOOQ_URL, params={"s": f"{ticker.lower()}.us", "i": "d"}, timeout=15
        )
        response.raise_for_status()
        return parse_stooq_csv(response.text)

    def daily_closes(self, ticker: str, days: int = 90) -> list[float]:
        """Closing prices only, oldest first — used by the technical
        indicator signal, which doesn't need the rest of the bar."""
        return [bar.close for bar in self.daily_bars(ticker)][-days:]
