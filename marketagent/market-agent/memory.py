"""
Persistent memory database for the Market Intelligence Agent.
Stores historical analyses, thesis evolution, and custom skills.
"""

import json
import os
from datetime import datetime

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")


def load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "analyses": {},
        "skills": {},
        "preferences": {},
    }


def save_memory(memory: dict):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)


def store_analysis(memory: dict, symbol: str, analysis_text: str, command: str = "/analyze"):
    symbol = symbol.upper()
    if symbol not in memory["analyses"]:
        memory["analyses"][symbol] = []

    entry = {
        "date": datetime.now().isoformat(),
        "command": command,
        "text": analysis_text[:2000],  # cap stored text
    }
    memory["analyses"][symbol].append(entry)
    # Keep last 10 analyses per symbol
    memory["analyses"][symbol] = memory["analyses"][symbol][-10:]
    save_memory(memory)


def get_analysis_history(memory: dict, symbol: str) -> list:
    return memory.get("analyses", {}).get(symbol.upper(), [])


def get_prior_thesis_context(memory: dict, symbol: str) -> str:
    """Return a compact prior-thesis summary to inject into the prompt."""
    history = get_analysis_history(memory, symbol)
    if not history:
        return ""
    last = history[-1]
    date_str = last["date"][:10]
    snippet = last["text"][:600].replace("\n", " ")
    return (
        f"[PRIOR ANALYSIS of {symbol.upper()} on {date_str} "
        f"(command: {last['command']}): {snippet}...]"
    )


def register_skill(memory: dict, name: str, description: str, data_sources: str, output_format: str):
    memory["skills"][name.lower()] = {
        "created": datetime.now().isoformat(),
        "description": description,
        "data_sources": data_sources,
        "output_format": output_format,
    }
    save_memory(memory)


def get_skills(memory: dict) -> dict:
    return memory.get("skills", {})


def list_all_analyzed_symbols(memory: dict) -> list:
    return list(memory.get("analyses", {}).keys())
