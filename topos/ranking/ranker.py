from collections import defaultdict
from datetime import datetime, timezone

from topos.db.models import RankedOpportunity
from topos.signals.base import Signal

_BUY_THRESHOLD = 60.0
_SELL_THRESHOLD = 60.0
_MIN_NET_DIRECTION = 0.2
_MIN_SOURCES_FOR_RECOMMENDATION = 2


class RankingEngine:
    """Aggregates raw signals per ticker into a single 0-100 combined
    score and a BUY/SELL/HOLD recommendation.

    Two things matter beyond plain multi-source agreement:

    1. Direction. A ticker with three strongly bearish signals shouldn't
       score the same as one with three bullish signals just because
       three sources fired — the score is scaled down when signals
       disagree on direction, not just averaged away.
    2. "Not blindly follow any single source" (the project's own stated
       principle) means a recommendation needs at least two agreeing
       sources, however strong the one signal is. One source can push the
       score up, but it caps out at HOLD alone.
    """

    def rank(self, signals: list[Signal]) -> list[RankedOpportunity]:
        by_ticker: dict[str, list[Signal]] = defaultdict(list)
        for signal in signals:
            by_ticker[signal.ticker].append(signal)

        ranked = [self._score_ticker(ticker, s) for ticker, s in by_ticker.items()]
        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked

    def _score_ticker(self, ticker: str, ticker_signals: list[Signal]) -> RankedOpportunity:
        avg_confidence = sum(s.confidence for s in ticker_signals) / len(ticker_signals)
        source_diversity = len({s.source for s in ticker_signals})

        buy_weight = sum(s.confidence for s in ticker_signals if s.evidence.get("direction") == "buy")
        sell_weight = sum(s.confidence for s in ticker_signals if s.evidence.get("direction") == "sell")
        total_directional = buy_weight + sell_weight
        net_direction = (buy_weight - sell_weight) / total_directional if total_directional else 0.0

        diversity_bonus = 1 + 0.1 * (source_diversity - 1)
        conviction = 0.5 + 0.5 * abs(net_direction)
        score = round(min(avg_confidence * diversity_bonus * conviction, 1.0) * 100, 2)

        recommendation = "HOLD"
        if source_diversity >= _MIN_SOURCES_FOR_RECOMMENDATION:
            if net_direction >= _MIN_NET_DIRECTION and score >= _BUY_THRESHOLD:
                recommendation = "BUY"
            elif net_direction <= -_MIN_NET_DIRECTION and score >= _SELL_THRESHOLD:
                recommendation = "SELL"

        return RankedOpportunity(
            ticker=ticker,
            score=score,
            recommendation=recommendation,
            net_direction=round(net_direction, 3),
            signal_count=len(ticker_signals),
            sources=sorted({s.source for s in ticker_signals}),
            rank_timestamp=datetime.now(timezone.utc),
        )
