from collections import defaultdict
from datetime import date, datetime, timezone

from topos.db.models import RankedOpportunity
from topos.ranking.attribution import build_breakdown
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

    def _score_ticker(
        self, ticker: str, ticker_signals: list[Signal], as_of: date | None = None
    ) -> RankedOpportunity:
        breakdown = build_breakdown(ticker, ticker_signals, as_of=as_of)
        score = breakdown.score
        net_direction = breakdown.net_direction
        source_diversity = len({s.source for s in ticker_signals})

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
            net_direction=net_direction,
            signal_count=len(ticker_signals),
            sources=sorted({s.source for s in ticker_signals}),
            # The full additive derivation, stored so the dashboard can
            # show why a ticker scored what it did without recomputing
            # against signals that may have changed since.
            attribution=breakdown.to_dict(),
            rank_timestamp=datetime.now(timezone.utc),
        )
