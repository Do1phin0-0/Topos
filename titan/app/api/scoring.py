from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from titan.app.db.models import SignalScore
from titan.app.db.session import get_db
from titan.app.scoring.engine import SignalScoringEngine

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/run")
def run_scoring(lookback_days: int = 90, db: Session = Depends(get_db)) -> list[dict]:
    scores = SignalScoringEngine().score_all(db, lookback_days=lookback_days)
    return [
        {
            "ticker": s.ticker,
            "score": s.score,
            "recommendation": s.recommendation,
            "net_direction": s.net_direction,
            "congress_signal_count": s.congress_signal_count,
            "insider_signal_count": s.insider_signal_count,
        }
        for s in scores
    ]


@router.get("/scores")
def list_scores(
    limit: int = Query(default=50, le=500),
    recommendation: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = db.query(SignalScore).order_by(SignalScore.computed_at.desc(), SignalScore.score.desc())
    if recommendation:
        query = query.filter(SignalScore.recommendation == recommendation.upper())
    rows = query.limit(limit).all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "score": r.score,
            "recommendation": r.recommendation,
            "net_direction": r.net_direction,
            "congress_signal_count": r.congress_signal_count,
            "insider_signal_count": r.insider_signal_count,
            "computed_at": r.computed_at,
        }
        for r in rows
    ]
