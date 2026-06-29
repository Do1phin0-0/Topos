"""
Real-time market data fetchers.
yfinance  — stocks (free, no key)
CoinGecko — crypto (free public API, no key)

All functions return None / [] on failure — never raise.
"""

import re
import time
import requests
import yfinance as yf
from datetime import datetime, timezone


_COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Comprehensive symbol → CoinGecko ID map; avoids a search API call for common coins
_CRYPTO_IDS: dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "USDC": "usd-coin", "USDT": "tether", "ADA": "cardano",
    "AVAX": "avalanche-2", "DOGE": "dogecoin", "TRX": "tron", "LINK": "chainlink",
    "DOT": "polkadot", "MATIC": "matic-network", "UNI": "uniswap", "LTC": "litecoin",
    "SHIB": "shiba-inu", "PEPE": "pepe", "NEAR": "near", "ARB": "arbitrum",
    "OP": "optimism", "APT": "aptos", "SUI": "sui", "INJ": "injective-protocol",
    "SEI": "sei-network", "WIF": "dogwifcoin", "BONK": "bonk", "FLOKI": "floki",
    "FET": "fetch-ai", "RENDER": "render-token", "TAO": "bittensor",
    "IMX": "immutable-x", "SAND": "the-sandbox", "MANA": "decentraland",
    "AAVE": "aave", "MKR": "maker", "CRV": "curve-dao-token", "SNX": "synthetix-network-token",
    "FIL": "filecoin", "ATOM": "cosmos", "ALGO": "algorand", "VET": "vechain",
    "ICP": "internet-computer", "HBAR": "hedera-hashgraph", "XLM": "stellar",
    "ETC": "ethereum-classic", "BCH": "bitcoin-cash", "XMR": "monero",
    "GALA": "gala", "AXS": "axie-infinity", "CAKE": "pancakeswap-token",
}

# Stocks that have the same ticker as a crypto symbol — always treat as stock
_STOCK_ONLY = {"LINK", "VET"}


def _fmt(val, prefix="$", suffix="", decimals=2):
    """Format a number with suffix (K/M/B/T) and prefix."""
    if val is None:
        return "N/A"
    try:
        val = float(val)
    except (TypeError, ValueError):
        return "N/A"
    for div, sfx in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(val) >= div:
            return f"{prefix}{val/div:.{decimals}f}{sfx}{suffix}"
    return f"{prefix}{val:,.{decimals}f}{suffix}"


def _pct(val) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%b %d %Y %H:%M UTC")


# ---------------------------------------------------------------------------
# Stock data via yfinance
# ---------------------------------------------------------------------------

def fetch_stock(ticker: str) -> dict | None:
    """Return key stock metrics. Returns None if ticker is unrecognised."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        # yfinance returns a minimal dict for unknown tickers
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            # Try fast_info as fallback
            fi = t.fast_info
            price = getattr(fi, "last_price", None)
            if not price:
                return None
            prev = getattr(fi, "previous_close", None)
            chg = (price - prev) / prev * 100 if prev else None
            return {
                "type": "stock",
                "ticker": ticker.upper(),
                "price": round(price, 2),
                "change_pct": round(chg, 2) if chg is not None else None,
                "market_cap": getattr(fi, "market_cap", None),
                "volume": getattr(fi, "three_month_average_volume", None),
            }

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev = info.get("previousClose") or info.get("regularMarketPreviousClose")
        volume = info.get("volume") or info.get("regularMarketVolume")
        chg = (price - prev) / prev * 100 if (price and prev) else None

        return {
            "type": "stock",
            "ticker": ticker.upper(),
            "price": round(price, 4) if price else None,
            "change_pct": round(chg, 2) if chg is not None else None,
            "volume": volume,
            "avg_volume": info.get("averageVolume"),
            "market_cap": info.get("marketCap"),
            "pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "revenue": info.get("totalRevenue"),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low": info.get("fiftyTwoWeekLow"),
            "analyst_target": info.get("targetMeanPrice"),
            "short_float": info.get("shortPercentOfFloat"),
            "beta": info.get("beta"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "name": info.get("longName") or info.get("shortName"),
        }
    except Exception:
        return None


def fetch_insiders(ticker: str) -> list[dict]:
    """Return last 5 insider transactions. Returns [] on any failure."""
    try:
        t = yf.Ticker(ticker)
        df = t.insider_transactions
        if df is None or df.empty:
            return []
        cols = [c for c in ("Shares", "Value", "Transaction", "Start Date", "Insider") if c in df.columns]
        rows = df[cols].head(5).to_dict("records")
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Crypto data via CoinGecko
# ---------------------------------------------------------------------------

def _coingecko_id(symbol: str) -> str | None:
    sym = symbol.upper()
    if sym in _CRYPTO_IDS:
        return _CRYPTO_IDS[sym]
    # Fallback: search
    try:
        r = requests.get(f"{_COINGECKO_BASE}/search", params={"query": sym}, timeout=6)
        coins = r.json().get("coins", [])
        if coins:
            return coins[0]["id"]
    except Exception:
        pass
    return None


def fetch_crypto(symbol: str) -> dict | None:
    """Return crypto market data from CoinGecko. Returns None on failure."""
    coin_id = _coingecko_id(symbol)
    if not coin_id:
        return None
    try:
        r = requests.get(
            f"{_COINGECKO_BASE}/coins/{coin_id}",
            params={"localization": "false", "tickers": "false", "community_data": "false"},
            timeout=8,
        )
        d = r.json()
        m = d.get("market_data", {})
        return {
            "type": "crypto",
            "symbol": symbol.upper(),
            "name": d.get("name"),
            "price_usd": m.get("current_price", {}).get("usd"),
            "change_24h": m.get("price_change_percentage_24h"),
            "change_7d": m.get("price_change_percentage_7d"),
            "change_30d": m.get("price_change_percentage_30d"),
            "market_cap": m.get("market_cap", {}).get("usd"),
            "market_cap_rank": d.get("market_cap_rank"),
            "volume_24h": m.get("total_volume", {}).get("usd"),
            "ath": m.get("ath", {}).get("usd"),
            "ath_change_pct": m.get("ath_change_percentage", {}).get("usd"),
            "circulating_supply": m.get("circulating_supply"),
            "total_supply": m.get("total_supply"),
            "categories": d.get("categories", [])[:4],
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Smart dispatcher: try stock, then crypto, return whichever has data
# ---------------------------------------------------------------------------

def fetch_asset(symbol: str, hint: str = "auto") -> dict | None:
    """
    hint: "stock" | "crypto" | "auto"
    Returns a data dict with a "type" key, or None.
    """
    sym = symbol.upper()

    if hint == "stock":
        return fetch_stock(sym)

    if hint == "crypto":
        return fetch_crypto(sym)

    # auto: try stock first (unless it's a known crypto-only symbol)
    is_known_crypto = sym in _CRYPTO_IDS and sym not in _STOCK_ONLY
    stock_data = None if is_known_crypto else fetch_stock(sym)

    # If stock returned a price, use it (may still also be a crypto)
    if stock_data and stock_data.get("price"):
        # Also check if it's a known crypto — if so, return both sets
        if is_known_crypto or sym in _CRYPTO_IDS:
            crypto_data = fetch_crypto(sym)
            if crypto_data:
                return {"type": "both", "stock": stock_data, "crypto": crypto_data}
        return stock_data

    # Fall back to crypto
    crypto_data = fetch_crypto(sym)
    if crypto_data:
        return crypto_data

    return None


# ---------------------------------------------------------------------------
# Market snapshot for /scan
# ---------------------------------------------------------------------------

def fetch_market_snapshot() -> dict:
    """Snapshot of major indices + BTC/ETH for /scan context."""
    result = {}

    index_tickers = {
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ",
        "^RUT":  "Russell 2000",
        "^VIX":  "VIX",
        "SPY":   "SPY ETF",
        "QQQ":   "QQQ ETF",
    }

    for sym, label in index_tickers.items():
        try:
            t = yf.Ticker(sym)
            fi = t.fast_info
            price = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
            if price and prev:
                chg = (price - prev) / prev * 100
                result[label] = {"price": round(price, 2), "change_pct": round(chg, 2)}
        except Exception:
            pass

    for sym in ("BTC", "ETH", "SOL"):
        try:
            d = fetch_crypto(sym)
            if d:
                result[sym] = {
                    "price": d.get("price_usd"),
                    "change_pct": d.get("change_24h"),
                }
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Formatters — produce a text block to inject into the AI prompt
# ---------------------------------------------------------------------------

def format_stock_block(d: dict) -> str:
    if not d:
        return ""
    lines = [f"[LIVE STOCK DATA — {d['ticker']} — {_now_utc()}]"]

    price_str = f"${d['price']:,.4f}" if d.get("price") else "N/A"
    chg_str = _pct(d.get("change_pct"))
    lines.append(f"Price: {price_str} ({chg_str} today)")

    if d.get("volume") and d.get("avg_volume"):
        vol_ratio = d["volume"] / d["avg_volume"]
        vol_flag = f" — {vol_ratio:.1f}x average" if vol_ratio > 1.2 or vol_ratio < 0.8 else ""
        lines.append(f"Volume: {_fmt(d['volume'], prefix='', suffix=' shares')} (avg: {_fmt(d['avg_volume'], prefix='', suffix='')}){vol_flag}")
    elif d.get("volume"):
        lines.append(f"Volume: {_fmt(d['volume'], prefix='', suffix=' shares')}")

    if d.get("market_cap"):
        lines.append(f"Market Cap: {_fmt(d['market_cap'])}")

    pe_parts = []
    if d.get("pe"):
        pe_parts.append(f"P/E: {d['pe']:.1f}")
    if d.get("forward_pe"):
        pe_parts.append(f"Fwd P/E: {d['forward_pe']:.1f}")
    if d.get("eps"):
        pe_parts.append(f"EPS: ${d['eps']:.2f}")
    if pe_parts:
        lines.append(" | ".join(pe_parts))

    if d.get("revenue"):
        lines.append(f"Revenue (TTM): {_fmt(d['revenue'])}")

    if d.get("week52_high") and d.get("week52_low") and d.get("price"):
        rng = f"${d['week52_low']:,.2f} — ${d['week52_high']:,.2f}"
        pct_of_high = d["price"] / d["week52_high"] * 100
        lines.append(f"52W Range: {rng} (at {pct_of_high:.0f}% of 52W high)")

    if d.get("analyst_target") and d.get("price"):
        upside = (d["analyst_target"] - d["price"]) / d["price"] * 100
        lines.append(f"Analyst Target: ${d['analyst_target']:,.2f} ({_pct(upside)} upside)")

    extras = []
    if d.get("short_float"):
        extras.append(f"Short: {d['short_float']*100:.1f}% of float")
    if d.get("beta"):
        extras.append(f"Beta: {d['beta']:.2f}")
    if extras:
        lines.append(" | ".join(extras))

    if d.get("sector"):
        sec = d["sector"]
        if d.get("industry"):
            sec += f" — {d['industry']}"
        lines.append(f"Sector: {sec}")

    return "\n".join(lines)


def format_crypto_block(d: dict) -> str:
    if not d:
        return ""
    price = d.get("price_usd")
    price_str = f"${price:,.6f}" if price and price < 0.01 else (f"${price:,.2f}" if price else "N/A")
    lines = [f"[LIVE CRYPTO DATA — {d['symbol']} ({d.get('name', '')}) — {_now_utc()}]"]
    lines.append(f"Price: {price_str}")

    changes = []
    if d.get("change_24h") is not None:
        changes.append(f"24h: {_pct(d['change_24h'])}")
    if d.get("change_7d") is not None:
        changes.append(f"7d: {_pct(d['change_7d'])}")
    if d.get("change_30d") is not None:
        changes.append(f"30d: {_pct(d['change_30d'])}")
    if changes:
        lines.append(" | ".join(changes))

    if d.get("market_cap"):
        rank = f" (Rank #{d['market_cap_rank']})" if d.get("market_cap_rank") else ""
        lines.append(f"Market Cap: {_fmt(d['market_cap'])}{rank}")

    if d.get("volume_24h"):
        lines.append(f"24h Volume: {_fmt(d['volume_24h'])}")

    if d.get("ath") and price:
        down_from_ath = (price - d["ath"]) / d["ath"] * 100
        lines.append(f"ATH: ${d['ath']:,.4f} (currently {_pct(down_from_ath)} from ATH)")

    supply_parts = []
    if d.get("circulating_supply"):
        supply_parts.append(f"Circulating: {_fmt(d['circulating_supply'], prefix='', suffix='')}")
    if d.get("total_supply"):
        supply_parts.append(f"Total: {_fmt(d['total_supply'], prefix='', suffix='')}")
    if supply_parts:
        lines.append(" | ".join(supply_parts))

    if d.get("categories"):
        lines.append(f"Categories: {', '.join(d['categories'])}")

    return "\n".join(lines)


def format_insider_block(rows: list) -> str:
    if not rows:
        return ""
    lines = ["Recent Insider Activity:"]
    for r in rows:
        insider = r.get("Insider", "Unknown")
        txn = r.get("Transaction", "")
        shares = r.get("Shares")
        value = r.get("Value")
        date = str(r.get("Start Date", ""))[:10]
        shares_str = f"{shares:,}" if shares else "?"
        value_str = _fmt(value) if value else ""
        lines.append(f"  • {insider}: {txn} {shares_str} shares {value_str} on {date}")
    return "\n".join(lines)


def format_snapshot_block(snap: dict) -> str:
    if not snap:
        return ""
    lines = [f"[MARKET SNAPSHOT — {_now_utc()}]"]
    for label, d in snap.items():
        price = d.get("price")
        chg = d.get("change_pct")
        price_str = f"${price:,.2f}" if price else "N/A"
        chg_str = _pct(chg) if chg is not None else ""
        lines.append(f"  {label:<16} {price_str}  ({chg_str})")
    return "\n".join(lines)


def build_data_context(user_input: str, watchlist: dict) -> str:
    """
    Parse the command and return a formatted live-data block to inject
    into the message before sending to Claude.
    Returns an empty string if no data is relevant.
    """
    parts = user_input.strip().split()
    if not parts:
        return ""
    cmd = parts[0].lower()

    # /scan — market snapshot
    if cmd == "/scan":
        snap = fetch_market_snapshot()
        return format_snapshot_block(snap)

    # /watch with no args — fetch all watchlist assets
    if cmd == "/watch" and len(parts) == 1:
        assets = watchlist.get("assets", [])
        if not assets:
            return ""
        blocks = []
        for sym in assets:
            d = fetch_asset(sym)
            if d:
                if d.get("type") == "crypto":
                    blocks.append(format_crypto_block(d))
                elif d.get("type") == "stock":
                    blocks.append(format_stock_block(d))
                elif d.get("type") == "both":
                    blocks.append(format_stock_block(d["stock"]))
                    blocks.append(format_crypto_block(d["crypto"]))
        return "\n\n".join(blocks)

    # Commands that take a single symbol
    hint_map = {
        "/stock": "stock",
        "/risk": "stock",
        "/analyze": "auto",
        "/coin": "crypto",
        "/sentiment": "auto",
        "/why": "auto",
        "/bubble": "auto",
        "/compare": "auto",
    }

    if cmd in hint_map and len(parts) >= 2:
        hint = hint_map[cmd]
        symbols = []

        # /compare takes two symbols
        if cmd == "/compare":
            for raw in parts[1:3]:
                sym = raw.upper().lstrip("$")
                if re.match(r"^[A-Z0-9]{1,10}$", sym):
                    symbols.append(sym)
        else:
            sym = parts[1].upper().lstrip("$")
            if re.match(r"^[A-Z0-9]{1,10}$", sym):
                symbols.append(sym)

        blocks = []
        for sym in symbols:
            d = fetch_asset(sym, hint=hint)
            if not d:
                continue
            if d.get("type") == "stock":
                blocks.append(format_stock_block(d))
                insiders = fetch_insiders(sym)
                ib = format_insider_block(insiders)
                if ib:
                    blocks.append(ib)
            elif d.get("type") == "crypto":
                blocks.append(format_crypto_block(d))
            elif d.get("type") == "both":
                blocks.append(format_stock_block(d["stock"]))
                insiders = fetch_insiders(sym)
                ib = format_insider_block(insiders)
                if ib:
                    blocks.append(ib)
                blocks.append(format_crypto_block(d["crypto"]))

        return "\n\n".join(blocks)

    return ""
