from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from topos.collectors.twitter import TwitterCollector
from topos.signals.timestamps import latest_date, parse_iso8601
from topos.signals.base import Signal

_analyzer = SentimentIntensityAnalyzer()
_NEUTRAL_BAND = 0.05


class TwitterSignalExtractor:
    def __init__(self, collector: TwitterCollector | None = None) -> None:
        self._collector = collector or TwitterCollector()

    def extract(self, tickers: list[str], tweets_per_ticker: int = 25) -> list[Signal]:
        if not self._collector.enabled:
            return []
        signals: list[Signal] = []
        for ticker in tickers:
            try:
                tweets = self._collector.search_recent(f"${ticker}", max_results=tweets_per_ticker)
            except Exception:
                continue
            signal = self._score(ticker, tweets)
            if signal:
                signals.append(signal)
        return signals

    def _score(self, ticker: str, tweets: list[dict]) -> Signal | None:
        if not tweets:
            return None
        scores = [_analyzer.polarity_scores(t.get("text", ""))["compound"] for t in tweets]
        avg = sum(scores) / len(scores)
        if abs(avg) < _NEUTRAL_BAND:
            return None

        direction = "buy" if avg > 0 else "sell"
        confidence = max(0.0, min(1.0, 0.15 + abs(avg) * 0.5 + min(len(tweets) / 50, 0.25)))

        # Dated by the newest tweet, not by when we scanned. Requires the
        # collector to request created_at, which X omits by default.
        event_date = latest_date([parse_iso8601(t.get("created_at")) for t in tweets])
        if event_date is None:
            return None

        observed_at = datetime.now(timezone.utc)
        return Signal(
            timestamp=observed_at,
            event_date=event_date,
            # Keyed to the newest tweet's date, so re-scanning an unchanged
            # result set dedupes instead of recording stale sentiment daily.
            dedup_key=f"twitter_sentiment:{ticker}:{event_date.isoformat()}",
            source="twitter_sentiment",
            ticker=ticker,
            confidence=round(confidence, 3),
            evidence={
                "direction": direction,
                "avg_compound": round(avg, 3),
                "tweet_count": len(tweets),
                "latest_tweet_date": event_date.isoformat(),
            },
        )
