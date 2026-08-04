import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from topos.config import load_settings
from topos.db.models import RankedOpportunity, Signal, Trade
from topos.db.session import SessionLocal, init_db
from topos.execution.alpaca_client import AlpacaExecutionClient

st.set_page_config(page_title="Topos", layout="wide")
st.title("Topos — Investment Signal Dashboard")

init_db()
session = SessionLocal()

st.header("Performance")
settings = load_settings()
if settings.alpaca_api_key and settings.alpaca_secret_key:
    try:
        account = AlpacaExecutionClient().get_account()
        positions = AlpacaExecutionClient().get_positions()
        col1, col2, col3 = st.columns(3)
        col1.metric("Equity", f"${float(account['equity']):,.2f}")
        col2.metric("Cash", f"${float(account['cash']):,.2f}")
        pl = float(account["equity"]) - float(account["last_equity"])
        col3.metric("Change since last close", f"${pl:,.2f}")
        if positions:
            st.dataframe(
                [
                    {
                        "ticker": p["symbol"],
                        "qty": p["qty"],
                        "market_value": float(p["market_value"]),
                        "unrealized_pl": float(p["unrealized_pl"]),
                        "unrealized_plpc": f"{float(p['unrealized_plpc']) * 100:.2f}%",
                    }
                    for p in positions
                ]
            )
        else:
            st.info("No open paper positions yet.")
    except Exception as exc:
        st.warning(f"Could not reach Alpaca: {exc}")
else:
    st.info(
        "Set ALPACA_API_KEY / ALPACA_SECRET_KEY to see live paper-account "
        "equity and positions here. Trade attempts (including dry runs) are "
        "logged in the table below regardless."
    )

trades = session.query(Trade).order_by(Trade.submitted_at.desc()).limit(50).all()
if trades:
    st.dataframe(
        [
            {
                "ticker": t.ticker,
                "side": t.side,
                "weight": t.weight,
                "notional_usd": t.notional_usd,
                "status": t.status,
                "broker_order_id": t.broker_order_id,
                "submitted_at": t.submitted_at,
            }
            for t in trades
        ]
    )
else:
    st.info("No trade attempts logged yet. Run `python scripts/run_pipeline.py`.")

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
                "recommendation": r.recommendation,
                "combined_score": f"{r.score:.0f}/100",
                "net_direction": r.net_direction,
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
