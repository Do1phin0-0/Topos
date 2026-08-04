from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from topos.collectors.news import NewsCollector
from topos.signals.base import Signal

_analyzer = SentimentIntensityAnalyzer()
_NEUTRAL_BAND = 0.05


class NewsSignalExtractor:
    def __init__(self, collector: NewsCollector | None = None) -> None:
        self._collector = collector or NewsCollector()

    def extract(self, tickers: list[str], headlines_per_ticker: int = 10) -> list[Signal]:
        signals: list[Signal] = []
        for ticker in tickers:
            try:
                headlines = self._collector.headlines(f"{ticker} stock", limit=headlines_per_ticker)
            except Exception:
                continue
            signal = self._score(ticker, headlines)
            if signal:
                signals.append(signal)
        return signals

    def _score(self, ticker: str, headlines: list[dict]) -> Signal | None:
        if not headlines:
            return None
        scores = [_analyzer.polarity_scores(h["title"])["compound"] for h in headlines]
        avg = sum(scores) / len(scores)
        if abs(avg) < _NEUTRAL_BAND:
            return None

        direction = "buy" if avg > 0 else "sell"
        confidence = max(0.0, min(1.0, 0.2 + abs(avg) * 0.6 + min(len(headlines) / 20, 0.2)))
        return Signal(
            timestamp=datetime.now(timezone.utc),
            source="news_sentiment",
            ticker=ticker,
            confidence=round(confidence, 3),
            evidence={
                "direction": direction,
                "avg_compound": round(avg, 3),
                "headline_count": len(headlines),
                "sample_headlines": [h["title"] for h in headlines[:3]],
            },
        )
