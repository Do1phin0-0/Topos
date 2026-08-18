from dataclasses import dataclass
from typing import Any

import requests

from topos.config import load_settings
from topos.http import build_session


@dataclass
class OrderResult:
    ticker: str
    status: str
    detail: str
    order_id: str | None = None


class AlpacaExecutionClient:
    """Talks to Alpaca's paper trading endpoint by default (ALPACA_BASE_URL
    in .env.example). dry_run=True never hits the network. Account/position
    lookups are used for returns tracking rather than computing P&L
    ourselves — Alpaca's paper account already does that correctly."""

    def __init__(self) -> None:
        settings = load_settings()
        self._base_url = settings.alpaca_base_url
        self._headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }
        # GET-only retry session: order placement below uses a bare
        # single-attempt POST so a retried request can never double-submit.
        self._session = build_session()

    def _get(self, path: str) -> Any:
        response = self._session.get(f"{self._base_url}{path}", headers=self._headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def place_order(
        self, ticker: str, notional_usd: float, side: str, dry_run: bool = True
    ) -> OrderResult:
        if dry_run:
            return OrderResult(
                ticker=ticker,
                status="dry_run",
                detail=f"would {side} ~${notional_usd:.2f} of {ticker}",
            )
        response = requests.post(
            f"{self._base_url}/v2/orders",
            headers=self._headers,
            json={
                "symbol": ticker,
                "notional": round(notional_usd, 2),
                "side": side,
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
            detail=f"submitted {side} market order for ${notional_usd:.2f} of {ticker}",
            order_id=body.get("id"),
        )

    def get_account(self) -> dict[str, Any]:
        return self._get("/v2/account")

    def get_positions(self) -> list[dict[str, Any]]:
        return self._get("/v2/positions")

    def get_positions_by_ticker(self) -> dict[str, float]:
        """Current market value per held ticker, used by the rebalancer to
        diff target weights against what's actually in the account."""
        return {p["symbol"]: float(p["market_value"]) for p in self.get_positions()}
