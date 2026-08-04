from dataclasses import dataclass

import requests

from topos.config import load_settings
from topos.portfolio.decision import TargetPosition


@dataclass
class OrderResult:
    ticker: str
    status: str
    detail: str


class AlpacaExecutionClient:
    """Talks to Alpaca's paper trading endpoint by default (ALPACA_BASE_URL
    in .env.example). dry_run=True never hits the network."""

    def __init__(self) -> None:
        settings = load_settings()
        self._base_url = settings.alpaca_base_url
        self._headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }

    def place_order(
        self, target: TargetPosition, notional_usd: float, dry_run: bool = True
    ) -> OrderResult:
        if dry_run:
            return OrderResult(
                ticker=target.ticker,
                status="dry_run",
                detail=f"would buy ~${notional_usd:.2f} of {target.ticker} (weight {target.weight})",
            )
        response = requests.post(
            f"{self._base_url}/v2/orders",
            headers=self._headers,
            json={
                "symbol": target.ticker,
                "notional": round(notional_usd, 2),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            timeout=15,
        )
        response.raise_for_status()
        return OrderResult(ticker=target.ticker, status="submitted", detail=response.json().get("id", ""))
