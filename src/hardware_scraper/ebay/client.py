from __future__ import annotations

import base64
import time
from typing import Optional

import httpx


class EbayClient:
    """
    Thin wrapper around the eBay OAuth token endpoint and Browse/Finding APIs.
    Caches the app-level OAuth token and refreshes it before expiry.
    """

    _PRODUCTION_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    _SANDBOX_TOKEN_URL = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    _PRODUCTION_BROWSE_URL = "https://api.ebay.com/buy/browse/v1"
    _SANDBOX_BROWSE_URL = "https://api.sandbox.ebay.com/buy/browse/v1"

    def __init__(self, app_id: str, cert_id: str, environment: str = "production") -> None:
        self._app_id = app_id
        self._cert_id = cert_id
        self._sandbox = environment == "sandbox"
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def _token_url(self) -> str:
        return self._SANDBOX_TOKEN_URL if self._sandbox else self._PRODUCTION_TOKEN_URL

    @property
    def _browse_url(self) -> str:
        return self._SANDBOX_BROWSE_URL if self._sandbox else self._PRODUCTION_BROWSE_URL

    def _credentials_b64(self) -> str:
        return base64.b64encode(f"{self._app_id}:{self._cert_id}".encode()).decode()

    async def _ensure_token(self, client: httpx.AsyncClient) -> None:
        if self._token and time.time() < self._token_expires_at - 60:
            return
        resp = await client.post(
            self._token_url,
            headers={
                "Authorization": f"Basic {self._credentials_b64()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200)

    async def get_sold_listings(
        self,
        query: str,
        days_back: int = 60,
        limit: int = 50,
        condition: Optional[str] = None,
    ) -> list[dict]:
        """
        Search eBay sold listings using the Browse API itemSummary/search endpoint
        filtered to SOLD items. Returns raw item dicts.
        """
        if not self._app_id or not self._cert_id:
            raise RuntimeError("eBay API credentials not configured. Set app_id and cert_id in config.yaml.")

        async with httpx.AsyncClient(timeout=20.0) as client:
            await self._ensure_token(client)

            params: dict = {
                "q": query,
                "filter": "buyingOptions:{FIXED_PRICE},conditionIds:{3000}",  # used/sold
                "limit": str(min(limit, 200)),
                "fieldgroups": "EXTENDED",
            }
            if condition:
                params["filter"] += f",conditions:{{{condition.upper()}}}"

            resp = await client.get(
                f"{self._browse_url}/itemSummary/search",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                },
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("itemSummaries", [])
