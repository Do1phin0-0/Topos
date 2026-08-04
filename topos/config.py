import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    sec_user_agent: str
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://topos:topos@localhost:5432/topos"
        ),
        sec_user_agent=os.environ.get(
            "SEC_EDGAR_USER_AGENT", "Topos Research contact@example.com"
        ),
        alpaca_api_key=os.environ.get("ALPACA_API_KEY", ""),
        alpaca_secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
        alpaca_base_url=os.environ.get(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        ),
    )
