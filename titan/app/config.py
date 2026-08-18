import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    sec_user_agent: str
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://titan:titan@localhost:5433/titan"
        ),
        sec_user_agent=os.environ.get(
            "SEC_EDGAR_USER_AGENT", "Titan Research contact@example.com"
        ),
        alpaca_api_key=os.environ.get("ALPACA_API_KEY", ""),
        alpaca_secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
        alpaca_base_url=os.environ.get(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        ),
    )
