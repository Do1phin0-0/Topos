from topos.config import load_settings

import requests

MAPPING_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 100


class OpenFigiCollector:
    """Resolves CUSIPs to tickers via OpenFIGI's free mapping API — 13F
    filings report holdings by CUSIP, not ticker, and there's no free
    official CUSIP/ticker mapping otherwise (CUSIP data itself is
    commercially licensed). Works unauthenticated at a low rate limit
    (~25 requests/6s); set OPENFIGI_API_KEY (free signup) for a higher
    limit. Coverage isn't complete — delisted or obscure securities may
    not resolve, and those holdings are silently dropped rather than
    guessed at."""

    def __init__(self) -> None:
        settings = load_settings()
        self._headers = {"Content-Type": "application/json"}
        if settings.openfigi_api_key:
            self._headers["X-OPENFIGI-APIKEY"] = settings.openfigi_api_key

    def cusips_to_tickers(self, cusips: list[str]) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for i in range(0, len(cusips), _BATCH_SIZE):
            batch = cusips[i : i + _BATCH_SIZE]
            body = [{"idType": "ID_CUSIP", "idValue": cusip} for cusip in batch]
            response = requests.post(MAPPING_URL, json=body, headers=self._headers, timeout=20)
            response.raise_for_status()
            for cusip, result in zip(batch, response.json()):
                data = result.get("data") or []
                if data and data[0].get("ticker"):
                    resolved[cusip] = data[0]["ticker"].upper()
        return resolved
