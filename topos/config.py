import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    sec_user_agent: str
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str
    twitter_bearer_token: str
    openfigi_api_key: str


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
        reddit_client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
        reddit_client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
        reddit_user_agent=os.environ.get("REDDIT_USER_AGENT", "topos-signal-bot/0.1"),
        twitter_bearer_token=os.environ.get("TWITTER_BEARER_TOKEN", ""),
        openfigi_api_key=os.environ.get("OPENFIGI_API_KEY", ""),
    )
