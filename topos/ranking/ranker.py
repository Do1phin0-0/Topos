from collections import defaultdict
from datetime import datetime, timezone

from topos.db.models import RankedOpportunity
from topos.signals.base import Signal


class RankingEngine:
    """Aggregates raw signals per ticker. Agreement across independent
    sources is weighted more heavily than one loud source.

    Only "buy"-direction signals are considered: the portfolio/execution
    layers are long-only, so a ticker insiders/congress/funds are net
    *selling* must not still rank and get bought just because the trade
    was large (confidence measures conviction strength, not direction)."""

    def rank(self, signals: list[Signal]) -> list[RankedOpportunity]:
        by_ticker: dict[str, list[Signal]] = defaultdict(list)
        for signal in signals:
            if signal.direction != "buy":
                continue
            by_ticker[signal.ticker].append(signal)

        ranked = []
        for ticker, ticker_signals in by_ticker.items():
            avg_confidence = sum(s.confidence for s in ticker_signals) / len(ticker_signals)
            source_diversity = len({s.source for s in ticker_signals})
            score = min(round(avg_confidence * (1 + 0.1 * (source_diversity - 1)), 4), 1.0)
            ranked.append(
                RankedOpportunity(
                    ticker=ticker,
                    score=score,
                    signal_count=len(ticker_signals),
                    sources=sorted({s.source for s in ticker_signals}),
                    rank_timestamp=datetime.now(timezone.utc),
                )
            )
        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked
