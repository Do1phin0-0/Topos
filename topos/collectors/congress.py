from typing import Any

import requests

HOUSE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
SENATE_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"


class CongressTradeCollector:
    """Pulls congressional trade disclosures from House Stock Watcher and
    Senate Stock Watcher. There is no free official structured API for
    these — the House Clerk and Senate eFD systems only publish PDFs. These
    two open-source projects parse those official disclosures into public
    JSON and are the de facto free source everyone in this space uses."""

    def _get_json(self, url: str) -> list[dict[str, Any]]:
        response = requests.get(url, timeout=30)
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

    def all_transactions(self) -> list[dict[str, Any]]:
        """Every disclosure both mirrors publish, newest first.

        These endpoints return the complete archive (House Stock Watcher
        covers 2020 onward) on every request, so historical backfill costs
        no more than a normal poll — the data was already being fetched
        and then discarded by the truncation in latest_transactions().
        """
        combined = self.house_transactions() + self.senate_transactions()
        combined.sort(key=lambda r: r.get("transaction_date") or "", reverse=True)
        return combined

    def latest_transactions(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.all_transactions()[:limit]
