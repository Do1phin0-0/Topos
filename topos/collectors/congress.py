from typing import Any

from topos.http import build_session

HOUSE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
SENATE_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"


class CongressTradeCollector:
    """Pulls congressional trade disclosures from House Stock Watcher and
    Senate Stock Watcher. There is no free official structured API for
    these — the House Clerk and Senate eFD systems only publish PDFs. These
    two open-source projects parse those official disclosures into public
    JSON and are the de facto free source everyone in this space uses."""

    def __init__(self) -> None:
        self._session = build_session()

    def _get_json(self, url: str) -> list[dict[str, Any]]:
        response = self._session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def house_transactions(self) -> list[dict[str, Any]]:
        rows = self._get_json(HOUSE_URL)
        for row in rows:
            row["chamber"] = "house"
        return rows

    def senate_transactions(self) -> list[dict[str, Any]]:
        rows = self._get_json(SENATE_URL)
        for row in rows:
            row["chamber"] = "senate"
        return rows

    def latest_transactions(self, limit: int = 200) -> list[dict[str, Any]]:
        combined = self.house_transactions() + self.senate_transactions()
        combined.sort(key=lambda r: r.get("transaction_date") or "", reverse=True)
        return combined[:limit]
