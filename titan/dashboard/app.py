import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("TITAN_API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Titan", layout="wide")
st.title("Titan — Trading Signal Dashboard")


def api_get(path: str, params: dict | None = None):
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"API error calling GET {path}: {exc}")
        return None


def api_post(path: str, params: dict | None = None):
    try:
        response = requests.post(f"{API_BASE_URL}{path}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"API error calling POST {path}: {exc}")
        return None


def fetch_alpaca_or_none(path: str):
    """Alpaca-backed endpoints return 400 when credentials aren't
    configured — that's an expected state, not an error, so it gets a
    quiet None instead of a red error box."""
    try:
        response = requests.get(f"{API_BASE_URL}{path}", timeout=15)
        if response.status_code == 400:
            return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.warning(f"Could not reach Titan API: {exc}")
        return None


health = api_get("/health")
if health:
    st.caption(f"API: {API_BASE_URL} — status: {health.get('status')}, database: {health.get('database')}")

st.header("Pipeline controls")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Ingest congressional trades"):
        result = api_post("/congress/ingest")
        if result is not None:
            st.success(f"Ingested {result['inserted']} new congressional trades")
with col2:
    if st.button("Ingest insider trades"):
        result = api_post("/insider/ingest")
        if result is not None:
            st.success(f"Ingested {result['inserted']} new insider trades")
with col3:
    if st.button("Run scoring"):
        result = api_post("/scoring/run")
        if result is not None:
            st.success(f"Scored {len(result)} tickers")

st.subheader("Execute trades (paper)")
col4, col5, col6 = st.columns(3)
top_n = col4.number_input("Top N", min_value=1, max_value=20, value=5)
account_equity = col5.number_input("Account equity ($)", min_value=1000.0, value=100_000.0, step=1000.0)
execute_live = col6.checkbox("Submit real paper orders (execute=true)", value=False)
if st.button("Run execution"):
    result = api_post(
        "/execution/run",
        params={"top_n": top_n, "account_equity": account_equity, "execute": execute_live},
    )
    if result is not None:
        st.success(f"Executed {len(result)} trade attempts")
        st.dataframe(result)

st.header("Signal Scores")
recommendation_filter = st.selectbox("Filter by recommendation", ["All", "BUY", "SELL", "HOLD"])
params = {} if recommendation_filter == "All" else {"recommendation": recommendation_filter}
scores = api_get("/scoring/scores", params=params)
if scores:
    st.dataframe(scores)
else:
    st.info("No scores yet. Ingest congressional/insider data, then run scoring.")

st.header("Congressional Trades")
congress_trades = api_get("/congress/trades")
if congress_trades:
    st.dataframe(congress_trades)
else:
    st.info("No congressional trades ingested yet.")

st.header("Insider Trades")
insider_trades = api_get("/insider/trades")
if insider_trades:
    st.dataframe(insider_trades)
else:
    st.info("No insider trades ingested yet.")

st.header("Trade History")
trades = api_get("/execution/trades")
if trades:
    st.dataframe(trades)
else:
    st.info("No trades logged yet.")

st.header("Alpaca Account")
account = fetch_alpaca_or_none("/execution/account")
if account:
    col7, col8 = st.columns(2)
    col7.metric("Equity", f"${float(account['equity']):,.2f}")
    col8.metric("Cash", f"${float(account['cash']):,.2f}")
    positions = fetch_alpaca_or_none("/execution/positions")
    if positions:
        st.dataframe(positions)
    else:
        st.info("No open paper positions yet.")
else:
    st.info(
        "Set ALPACA_API_KEY / ALPACA_SECRET_KEY on the Titan API service to "
        "see live paper-account equity and positions here."
    )
