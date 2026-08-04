import xml.etree.ElementTree as ET
from typing import Any, ClassVar

import requests

from topos.config import load_settings

ATOM_NS = "{http://www.w3.org/2005/Atom}"
BASE_URL = "https://www.sec.gov"


class SECEdgarCollector:
    """Pulls filing metadata and documents from SEC EDGAR. No API key
    required, but SEC requires a descriptive User-Agent (name + contact
    email) on every request."""

    _ticker_map: ClassVar[dict[int, str] | None] = None

    def __init__(self) -> None:
        settings = load_settings()
        self._headers = {"User-Agent": settings.sec_user_agent}

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        response = requests.get(url, headers=self._headers, timeout=15, **kwargs)
        response.raise_for_status()
        return response

    def latest_filings(self, form_type: str, count: int = 40) -> list[dict[str, Any]]:
        """Most recent filings of a given form type, across all filers."""
        url = (
            f"{BASE_URL}/cgi-bin/browse-edgar"
            f"?action=getcurrent&type={form_type}&output=atom&count={count}"
        )
        root = ET.fromstring(self._get(url).content)
        filings = []
        for entry in root.findall(f"{ATOM_NS}entry"):
            title = entry.findtext(f"{ATOM_NS}title", default="")
            link_el = entry.find(f"{ATOM_NS}link")
            index_url = link_el.get("href") if link_el is not None else None
            updated = entry.findtext(f"{ATOM_NS}updated", default="")
            if not index_url:
                continue
            filings.append(
                {
                    "form_type": form_type,
                    "title": title,
                    "index_url": index_url,
                    "filed_at": updated,
                    "cik": self._cik_from_index_url(index_url),
                }
            )
        return filings

    def filing_documents(self, index_url: str) -> list[dict[str, str]]:
        """Every document (name + url) in a filing's directory."""
        base = index_url.rsplit("/", 1)[0]
        try:
            data = self._get(f"{base}/index.json").json()
        except (requests.HTTPError, ValueError):
            return []
        items = data.get("directory", {}).get("item", [])
        return [{"name": item["name"], "url": f"{base}/{item['name']}"} for item in items]

    def fetch_xml(self, url: str) -> ET.Element:
        return ET.fromstring(self._get(url).content)

    def fetch_text(self, url: str) -> str:
        return self._get(url).text

    def ticker_for_cik(self, cik: int | None) -> str | None:
        """Resolves a CIK to a trading ticker via SEC's own CIK/ticker
        mapping — the atom feeds only give CIK + company name, not ticker."""
        if cik is None:
            return None
        if SECEdgarCollector._ticker_map is None:
            SECEdgarCollector._ticker_map = self._load_ticker_map()
        return SECEdgarCollector._ticker_map.get(cik)

    def _load_ticker_map(self) -> dict[int, str]:
        try:
            data = self._get(f"{BASE_URL}/files/company_tickers.json").json()
        except (requests.HTTPError, ValueError):
            return {}
        return {row["cik_str"]: row["ticker"].upper() for row in data.values()}

    @staticmethod
    def _cik_from_index_url(index_url: str) -> int | None:
        try:
            return int(index_url.split("/edgar/data/")[1].split("/")[0])
        except (IndexError, ValueError):
            return None
