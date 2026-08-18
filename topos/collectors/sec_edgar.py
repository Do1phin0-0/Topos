import xml.etree.ElementTree as ET
from typing import Any

import requests

from topos.config import load_settings

ATOM_NS = "{http://www.w3.org/2005/Atom}"
BASE_URL = "https://www.sec.gov"


class SECEdgarCollector:
    """Pulls filing metadata and documents from SEC EDGAR. No API key
    required, but SEC requires a descriptive User-Agent (name + contact
    email) on every request."""

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
                }
            )
        return filings

    def filing_documents(self, index_url: str) -> list[str]:
        """URLs of every XML document in a filing's directory."""
        base = index_url.rsplit("/", 1)[0]
        try:
            data = self._get(f"{base}/index.json").json()
        except (requests.HTTPError, ValueError):
            return []
        items = data.get("directory", {}).get("item", [])
        return [f"{base}/{item['name']}" for item in items if item["name"].endswith(".xml")]

    def fetch_xml(self, url: str) -> ET.Element:
        return ET.fromstring(self._get(url).content)

    def company_tickers(self) -> list[dict[str, Any]]:
        """Raw {cik_str, ticker, title} records from SEC's free
        company_tickers.json. 13F filings identify issuers by CUSIP + name,
        never a ticker, so this is used as a best-effort name-based
        fallback for resolving 13F holdings to tickers."""
        data = self._get(f"{BASE_URL}/files/company_tickers.json").json()
        return list(data.values())
