import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from topos.backtesting.evaluate import evaluate_score_buckets
from topos.config import load_settings
from topos.db.models import RankedOpportunity, Signal, Trade
from topos.db.session import SessionLocal, init_db
from topos.execution.alpaca_client import AlpacaExecutionClient

st.set_page_config(page_title="Topos", layout="wide")
st.title("Topos — Investment Signal Dashboard")

try:
    init_db()
    session = SessionLocal()
except Exception as exc:
    st.error(
        f"Could not connect to the database: {exc}\n\n"
        "If this just deployed, the database may still be provisioning — "
        "try refreshing in a minute. Otherwise check DATABASE_URL."
    )
    st.stop()

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

st.header("Signal Validation")
st.caption(
    "Does a higher score actually earn a higher return? Returns are "
    "direction-adjusted (a correct SELL counts as a gain), and signals too "
    "recent to have a full forward window are excluded rather than counted "
    "as 0%."
)

validation_horizon = st.selectbox("Holding period (trading days)", [5, 20, 60], index=1)
try:
    buckets = evaluate_score_buckets(session, horizons=(validation_horizon,))
except Exception as exc:
    buckets = []
    st.warning(f"Could not evaluate score buckets: {exc}")

if buckets:
    rows = []
    thin = False
    for bucket in buckets:
        stats = bucket.horizons[validation_horizon]
        if not stats.is_meaningful:
            thin = True
        rows.append(
            {
                "score bucket": bucket.label,
                "n": stats.sample_size,
                "win rate": "—" if stats.win_rate is None else f"{stats.win_rate:.0%}",
                "avg return": "—" if stats.avg_return is None else f"{stats.avg_return * 100:+.2f}%",
                "median": "—" if stats.median_return is None else f"{stats.median_return * 100:+.2f}%",
                "sharpe": "—" if stats.sharpe is None else f"{stats.sharpe:.2f}",
                "enough data?": "yes" if stats.is_meaningful else "thin — treat as noise",
            }
        )
    st.dataframe(rows)

    chartable = {
        b.label: b.horizons[validation_horizon].avg_return
        for b in buckets
        if b.horizons[validation_horizon].avg_return is not None
    }
    if chartable:
        st.bar_chart(chartable)

    if thin:
        st.info(
            "Buckets marked thin have too few observations (under 20) to "
            "read as evidence. This fills in as the pipeline accumulates "
            "history — the scoring weights should not be tuned off these "
            "numbers yet."
        )
else:
    st.info(
        "No measurable history yet. Score validation needs ranked "
        "opportunities that are old enough for their forward window to have "
        "closed, plus price history covering it."
    )

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
