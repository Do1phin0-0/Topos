import csv
import io

import requests

STOOQ_URL = "https://stooq.com/q/d/l/"


class PriceCollector:
    """Free daily OHLCV history via Stooq's public CSV export, no API key
    required. Stooq tickers for US equities are '<symbol>.us'."""

    def daily_closes(self, ticker: str, days: int = 90) -> list[float]:
        response = requests.get(STOOQ_URL, params={"s": f"{ticker.lower()}.us", "i": "d"}, timeout=15)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        closes = [float(row["Close"]) for row in reader if row.get("Close")]
        return closes[-days:]
