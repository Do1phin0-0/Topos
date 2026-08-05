from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from topos.collectors.reddit import RedditCollector
from topos.signals.base import Signal

_analyzer = SentimentIntensityAnalyzer()
_NEUTRAL_BAND = 0.05
_SUBREDDITS = ["wallstreetbets", "stocks", "investing"]


class RedditSignalExtractor:
    def __init__(self, collector: RedditCollector | None = None) -> None:
        self._collector = collector or RedditCollector()

    def extract(self, tickers: list[str], posts_per_ticker: int = 15) -> list[Signal]:
        if not self._collector.enabled:
            return []
        signals: list[Signal] = []
        for ticker in tickers:
            posts: list[dict] = []
            for subreddit in _SUBREDDITS:
                try:
                    posts.extend(self._collector.search_posts(subreddit, ticker, limit=posts_per_ticker))
                except Exception:
                    continue
            signal = self._score(ticker, posts)
            if signal:
                signals.append(signal)
        return signals

    def _score(self, ticker: str, posts: list[dict]) -> Signal | None:
        if not posts:
            return None
        texts = [f"{p.get('title', '')} {p.get('selftext', '')}" for p in posts]
        scores = [_analyzer.polarity_scores(t)["compound"] for t in texts]
        avg = sum(scores) / len(scores)
        if abs(avg) < _NEUTRAL_BAND:
            return None

        direction = "buy" if avg > 0 else "sell"
        engagement = sum(p.get("score", 0) for p in posts)
        confidence = max(0.0, min(1.0, 0.15 + abs(avg) * 0.5 + min(engagement / 5000, 0.25)))
        observed_at = datetime.now(timezone.utc)
        event_date = observed_at.date()
        return Signal(
            timestamp=observed_at,
            event_date=event_date,
            # A daily sentiment aggregate: one snapshot per ticker per day,
            # so re-running the scan refreshes rather than stacks.
            dedup_key=f"reddit_sentiment:{ticker}:{event_date.isoformat()}",
            source="reddit_sentiment",
            ticker=ticker,
            confidence=round(confidence, 3),
            evidence={
                "direction": direction,
                "avg_compound": round(avg, 3),
                "post_count": len(posts),
                "total_engagement": engagement,
            },
        )
