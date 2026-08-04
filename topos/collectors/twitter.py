from typing import Any

import requests

from topos.config import load_settings

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterCollector:
    """X (Twitter) API v2 recent search. X's free tier does not include
    search/read access as of this writing — this needs a paid Basic-tier
    (or higher) bearer token in TWITTER_BEARER_TOKEN. There is no free or
    scraping fallback: scraping X directly means defeating its anti-bot
    measures, which this project won't do. Returns nothing until a token
    is configured."""

    def __init__(self) -> None:
        settings = load_settings()
        self._bearer_token = settings.twitter_bearer_token

    @property
    def enabled(self) -> bool:
        return bool(self._bearer_token)

    def search_recent(self, query: str, max_results: int = 25) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        response = requests.get(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {self._bearer_token}"},
            params={
                "query": f"{query} -is:retweet lang:en",
                "max_results": max(10, min(max_results, 100)),
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("data", [])
