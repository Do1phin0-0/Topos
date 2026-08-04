from datetime import datetime, timezone

from topos.collectors.prices import PriceCollector
from topos.signals.base import Signal


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _rsi(values: list[float], window: int = 14) -> float | None:
    if len(values) < window + 1:
        return None
    changes = [curr - prev for prev, curr in zip(values[-window - 1 : -1], values[-window:])]
    avg_gain = sum(max(c, 0.0) for c in changes) / window
    avg_loss = sum(max(-c, 0.0) for c in changes) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class TechnicalSignalExtractor:
    def __init__(self, collector: PriceCollector | None = None) -> None:
        self._collector = collector or PriceCollector()

    def extract(self, tickers: list[str]) -> list[Signal]:
        signals: list[Signal] = []
        for ticker in tickers:
            try:
                closes = self._collector.daily_closes(ticker, days=90)
            except Exception:
                continue
            signal = self._score(ticker, closes)
            if signal:
                signals.append(signal)
        return signals

    def _score(self, ticker: str, closes: list[float]) -> Signal | None:
        rsi = _rsi(closes)
        sma20 = _sma(closes, 20)
        sma50 = _sma(closes, 50)
        if rsi is None or sma20 is None or sma50 is None:
            return None

        crossover = "bullish" if sma20 > sma50 else "bearish"
        if rsi <= 30:
            direction, strength = "buy", (30 - rsi) / 30
        elif rsi >= 70:
            direction, strength = "sell", (rsi - 70) / 30
        else:
            direction = "buy" if crossover == "bullish" else "sell"
            strength = abs(sma20 - sma50) / sma50

        confidence = max(0.0, min(1.0, 0.2 + min(strength, 1.0) * 0.5))
        return Signal(
            timestamp=datetime.now(timezone.utc),
            source="technical",
            ticker=ticker,
            confidence=round(confidence, 3),
            evidence={
                "direction": direction,
                "rsi_14": round(rsi, 2),
                "sma_20": round(sma20, 2),
                "sma_50": round(sma50, 2),
                "crossover": crossover,
            },
        )
