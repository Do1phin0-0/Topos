import os
from dataclasses import dataclass
from pathlib import Path

try:  # pragma: no cover - exercised implicitly whenever the package imports
    from dotenv import load_dotenv

    # The README tells you to `cp .env.example .env`, and python-dotenv has
    # always been a dependency, but nothing actually read the file — so
    # locally every variable had to be exported by hand each session, while
    # Docker worked because Compose injects them directly.
    #
    # override=False so an explicitly exported variable still wins over the
    # file: a one-off `$env:DATABASE_URL = ...` should point at that
    # database, not silently fall back to whatever .env holds.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:  # python-dotenv absent: environment variables still work
    pass


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


def _normalize_database_url(url: str) -> str:
    """Render (and Heroku) hand out `postgres://` URLs, which SQLAlchemy 2.0
    refuses to parse — it only accepts `postgresql://`. Copying the URL
    straight out of the Render dashboard would otherwise fail with an
    opaque dialect error before anything else runs."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def load_settings() -> Settings:
    return Settings(
        database_url=_normalize_database_url(
            os.environ.get("DATABASE_URL", "postgresql://topos:topos@localhost:5432/topos")
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
