"""Daily price history, from whichever free source is actually answering.

`PriceCollector` is a fallback chain, not a single client, because the
single-client version failed in the field: Stooq began returning 404 for
plainly real symbols (AAPL, ADBE) mixed with DNS failures and timeouts,
and a 250-ticker backfill burned a quarter hour discovering the same
dead host 250 times. Each source here is tried in order per ticker, and
a source that keeps failing to *connect* is benched for the rest of the
run rather than re-timed-out once per ticker.

A miss (404, empty history) does not bench a source — an OTC symbol one
source lacks says nothing about the next ticker. Only connection-level
failures do, because those are about the host, cost a full timeout each,
and repeat identically.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone

import requests

STOOQ_URL = "https://stooq.com/q/d/l/"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Yahoo rejects requests that announce themselves as a script.
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Topos research)"}

# Consecutive connection failures before a source is benched for the run.
BENCH_AFTER = 3


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


def parse_yahoo_chart(payload: dict) -> list[Bar]:
    """Parses Yahoo's chart JSON into bars, oldest first.

    Yahoo pads its arrays with nulls for halted days and sometimes for
    the still-open current session; a row with any missing field is
    dropped rather than fabricated, for the same reason as everywhere
    else in this codebase — a made-up bar poisons the forward returns
    measured through it.
    """
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return []

    bars: list[Bar] = []
    for i, ts in enumerate(timestamps):
        try:
            values = (
                quote["open"][i],
                quote["high"][i],
                quote["low"][i],
                quote["close"][i],
                quote["volume"][i],
            )
        except (KeyError, IndexError, TypeError):
            continue
        if any(v is None for v in values):
            continue
        bars.append(
            Bar(
                date=datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                open=float(values[0]),
                high=float(values[1]),
                low=float(values[2]),
                close=float(values[3]),
                volume=float(values[4]),
            )
        )
    bars.sort(key=lambda b: b.date)
    return bars


class StooqCollector:
    """Stooq's public CSV export, no API key. US equities are '<symbol>.us'."""

    name = "stooq"

    def daily_bars(self, ticker: str) -> list[Bar]:
        response = requests.get(
            STOOQ_URL, params={"s": f"{ticker.lower()}.us", "i": "d"}, timeout=15
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return parse_stooq_csv(response.text)


class YahooCollector:
    """Yahoo Finance's chart endpoint, no API key. Five years of daily
    bars covers every horizon the backtester measures."""

    name = "yahoo"

    def daily_bars(self, ticker: str) -> list[Bar]:
        response = requests.get(
            YAHOO_URL.format(symbol=ticker.upper()),
            params={"range": "5y", "interval": "1d"},
            headers=_YAHOO_HEADERS,
            timeout=15,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return parse_yahoo_chart(response.json())


class PriceCollector:
    """The fallback chain. Drop-in for the old single-source collector —
    same `daily_bars` / `daily_closes` interface, same no-key operation."""

    def __init__(self, sources: list | None = None) -> None:
        self._sources = sources if sources is not None else [StooqCollector(), YahooCollector()]
        self._consecutive_failures = {source.name: 0 for source in self._sources}
        self._benched: set[str] = set()

    def _bench(self, source) -> None:
        self._benched.add(source.name)
        print(
            f"[warn] price source '{source.name}' benched for this run after "
            f"{BENCH_AFTER} consecutive connection failures."
        )

    def daily_bars(self, ticker: str) -> list[Bar]:
        """Bars from the first source that has them. Raises only when every
        source failed with an error (as opposed to cleanly having no data),
        so callers can still tell 'unknown ticker' from 'nothing worked'."""
        last_error: Exception | None = None

        for source in self._sources:
            if source.name in self._benched:
                continue
            try:
                bars = source.daily_bars(ticker)
            except (requests.ConnectionError, requests.Timeout) as error:
                last_error = error
                self._consecutive_failures[source.name] += 1
                if self._consecutive_failures[source.name] >= BENCH_AFTER:
                    self._bench(source)
                continue
            except requests.RequestException as error:
                # An HTTP-level rejection is cheap and may be per-ticker;
                # it neither benches the source nor counts toward it.
                last_error = error
                continue

            self._consecutive_failures[source.name] = 0
            if bars:
                return bars
            # A clean empty answer: this source just doesn't know the
            # symbol. The next one might.

        if last_error is not None:
            raise last_error
        return []

    def daily_closes(self, ticker: str, days: int = 90) -> list[float]:
        """Closing prices only, oldest first — used by the technical
        indicator signal, which doesn't need the rest of the bar."""
        return [bar.close for bar in self.daily_bars(ticker)][-days:]
