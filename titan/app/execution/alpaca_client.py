from dataclasses import dataclass
from typing import Any

import requests

from titan.app.config import get_settings


@dataclass
class OrderResult:
    ticker: str
    status: str
    detail: str
    order_id: str | None = None


class AlpacaExecutionClient:
    """Talks to Alpaca's paper trading endpoint by default
    (ALPACA_BASE_URL in .env.example). dry_run=True never hits the
    network."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.alpaca_base_url
        self._headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

    def _get(self, path: str) -> Any:
        response = requests.get(f"{self._base_url}{path}", headers=self._headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def place_order(self, ticker: str, notional_usd: float, dry_run: bool = True) -> OrderResult:
        if dry_run:
            return OrderResult(
                ticker=ticker,
                status="dry_run",
                detail=f"would buy ~${notional_usd:.2f} of {ticker}",
            )
        response = requests.post(
            f"{self._base_url}/v2/orders",
            headers=self._headers,
            json={
                "symbol": ticker,
                "notional": round(notional_usd, 2),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        return OrderResult(
            ticker=ticker,
            status="submitted",
            detail=f"submitted market order for ${notional_usd:.2f}",
            order_id=body.get("id"),
        )

    def get_account(self) -> dict[str, Any]:
        return self._get("/v2/account")

    def get_positions(self) -> list[dict[str, Any]]:
        return self._get("/v2/positions")
