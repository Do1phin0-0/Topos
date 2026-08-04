import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from topos.db.models import RankedOpportunity, Signal
from topos.db.session import SessionLocal, init_db

st.set_page_config(page_title="Topos", layout="wide")
st.title("Topos — Investment Signal Dashboard")

init_db()
session = SessionLocal()

st.header("Ranked Opportunities")
ranked = (
    session.query(RankedOpportunity)
    .order_by(RankedOpportunity.rank_timestamp.desc(), RankedOpportunity.score.desc())
    .limit(50)
    .all()
)
if ranked:
    st.dataframe(
        [
            {
                "ticker": r.ticker,
                "score": r.score,
                "signal_count": r.signal_count,
                "sources": ", ".join(r.sources),
                "ranked_at": r.rank_timestamp,
            }
            for r in ranked
        ]
    )
else:
    st.info("No ranked opportunities yet. Run `python scripts/run_pipeline.py`.")

st.header("Raw Signals")
signals = session.query(Signal).order_by(Signal.timestamp.desc()).limit(100).all()
if signals:
    st.dataframe(
        [
            {
                "ticker": s.ticker,
                "source": s.source,
                "confidence": s.confidence,
                "timestamp": s.timestamp,
                "evidence": s.evidence,
            }
            for s in signals
        ]
    )
else:
    st.info("No signals collected yet.")

session.close()
