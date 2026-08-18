from typing import Any
from xml.etree import ElementTree as ET

import requests

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


class NewsCollector:
    """Free, no-API-key headline source via Google News's public RSS
    search feed. Unofficial in the sense that Google could change or
    rate-limit it without notice — swap in a paid provider (NewsAPI,
    Finnhub) for anything that needs guarantees."""

    def headlines(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        response = requests.get(GOOGLE_NEWS_RSS, params=params, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = []
        for item in root.findall("./channel/item")[:limit]:
            items.append(
                {
                    "title": item.findtext("title") or "",
                    "link": item.findtext("link") or "",
                    "pub_date": item.findtext("pubDate") or "",
                }
            )
        return items
