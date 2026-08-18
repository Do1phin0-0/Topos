import time
from typing import Any

import requests

from topos.config import load_settings

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"


class RedditCollector:
    """Uses Reddit's OAuth2 client_credentials flow via a registered
    'script' app (reddit.com/prefs/apps) for read-only access. Returns
    nothing if REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET aren't set — Reddit's
    terms require a registered app for programmatic access, so this
    deliberately doesn't fall back to unauthenticated scraping."""

    def __init__(self) -> None:
        settings = load_settings()
        self._client_id = settings.reddit_client_id
        self._client_secret = settings.reddit_client_secret
        self._user_agent = settings.reddit_user_agent
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        response = requests.post(
            TOKEN_URL,
            auth=(self._client_id, self._client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self._user_agent},
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + body.get("expires_in", 3600) - 60
        return self._token

    def search_posts(self, subreddit: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        response = requests.get(
            f"{API_BASE}/r/{subreddit}/search",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "User-Agent": self._user_agent,
            },
            params={"q": query, "restrict_sr": "true", "sort": "new", "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
        return [child["data"] for child in response.json().get("data", {}).get("children", [])]
