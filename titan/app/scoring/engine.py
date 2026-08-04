from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from titan.app.db.models import CongressionalTrade, InsiderTrade, SignalScore

_BUY_THRESHOLD = 60.0
_SELL_THRESHOLD = 60.0
_MIN_NET_DIRECTION = 0.2
_MIN_SOURCES_FOR_RECOMMENDATION = 2
_DEFAULT_LOOKBACK_DAYS = 90


class SignalScoringEngine:
    """Combines congressional and insider trade activity per ticker into
    a 0-100 combined score and a BUY/SELL/HOLD recommendation.

    Two principles, same ones used elsewhere in this project:

    1. Direction matters. Agreement between the two trackers pushes the
       score up; disagreement pulls it down rather than averaging away.
    2. No single-source recommendations. A ticker needs BOTH the
       congressional and insider trackers to have activity — not just
       one — before it can get BUY or SELL. With only two trackers in
       Titan today, that's a strict bar by design: it means most tickers
       will sit at HOLD, which is the intended behavior for "don't
       blindly follow a single source," not a bug.
    """

    def score_all(self, db: Session, lookback_days: int = _DEFAULT_LOOKBACK_DAYS) -> list[SignalScore]:
        since = datetime.utcnow() - timedelta(days=lookback_days)

        congress_by_ticker: dict[str, list[CongressionalTrade]] = defaultdict(list)
        for row in db.query(CongressionalTrade).filter(CongressionalTrade.transaction_date >= since):
            congress_by_ticker[row.ticker].append(row)

        insider_by_ticker: dict[str, list[InsiderTrade]] = defaultdict(list)
        for row in db.query(InsiderTrade).filter(InsiderTrade.transaction_date >= since):
            insider_by_ticker[row.ticker].append(row)

        tickers = set(congress_by_ticker) | set(insider_by_ticker)
        scores = [
            self._score_ticker(ticker, congress_by_ticker.get(ticker, []), insider_by_ticker.get(ticker, []))
            for ticker in tickers
        ]
        scores.sort(key=lambda s: s.score, reverse=True)

        for score in scores:
            db.add(score)
        db.commit()
        return scores

    def _score_ticker(
        self,
        ticker: str,
        congress_trades: list[CongressionalTrade],
        insider_trades: list[InsiderTrade],
    ) -> SignalScore:
        buy_weight = 0.0
        sell_weight = 0.0
        source_count = 0

        if congress_trades:
            source_count += 1
            for trade in congress_trades:
                weight = self._congress_weight(trade)
                if trade.transaction_type == "purchase":
                    buy_weight += weight
                else:
                    sell_weight += weight

        if insider_trades:
            source_count += 1
            for trade in insider_trades:
                weight = self._insider_weight(trade)
                if trade.direction == "buy":
                    buy_weight += weight
                else:
                    sell_weight += weight

        total_weight = buy_weight + sell_weight
        net_direction = (buy_weight - sell_weight) / total_weight if total_weight else 0.0
        event_count = len(congress_trades) + len(insider_trades)
        avg_weight = total_weight / event_count if event_count else 0.0
        conviction = 0.5 + 0.5 * abs(net_direction)
        score = round(min(avg_weight * conviction, 1.0) * 100, 2)

        recommendation = "HOLD"
        if source_count >= _MIN_SOURCES_FOR_RECOMMENDATION:
            if net_direction >= _MIN_NET_DIRECTION and score >= _BUY_THRESHOLD:
                recommendation = "BUY"
            elif net_direction <= -_MIN_NET_DIRECTION and score >= _SELL_THRESHOLD:
                recommendation = "SELL"

        return SignalScore(
            ticker=ticker,
            score=score,
            recommendation=recommendation,
            net_direction=round(net_direction, 3),
            congress_signal_count=len(congress_trades),
            insider_signal_count=len(insider_trades),
            computed_at=datetime.utcnow(),
        )

    @staticmethod
    def _congress_weight(trade: CongressionalTrade) -> float:
        size_weight = min(trade.amount_midpoint_usd / 250_000, 1.0) * 0.4
        return max(0.0, min(1.0, 0.25 + size_weight))

    @staticmethod
    def _insider_weight(trade: InsiderTrade) -> float:
        role_weight = 0.3 if (trade.is_officer or trade.is_director) else 0.15
        size_weight = min(trade.total_value_usd / 1_000_000, 1.0) * 0.5
        return max(0.0, min(1.0, 0.2 + role_weight + size_weight))
