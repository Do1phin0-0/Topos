"""
Watchlist management — local JSON storage.
"""

import json
import os
from datetime import datetime

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")


def load_watchlist() -> dict:
    """Load watchlist from disk, or return empty default."""
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "assets": [],
        "notes": {},
        "added_dates": {},
        "last_updated": None
    }


def save_watchlist(watchlist: dict):
    """Save watchlist to disk."""
    watchlist["last_updated"] = datetime.now().isoformat()
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f, indent=2)


def add_to_watchlist(watchlist: dict, symbol: str, note: str = ""):
    """Add a symbol to the watchlist."""
    symbol = symbol.upper()
    if symbol not in watchlist["assets"]:
        watchlist["assets"].append(symbol)
        watchlist["added_dates"][symbol] = datetime.now().isoformat()
        if note:
            watchlist["notes"][symbol] = note


def remove_from_watchlist(watchlist: dict, symbol: str):
    """Remove a symbol from the watchlist."""
    symbol = symbol.upper()
    if symbol in watchlist["assets"]:
        watchlist["assets"].remove(symbol)
        watchlist["notes"].pop(symbol, None)
        watchlist["added_dates"].pop(symbol, None)
