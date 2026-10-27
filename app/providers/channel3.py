"""Channel3 commercial catalog and offers provider adapter.

Provides an isolated adapter for the Channel3 API (https://api.trychannel3.com).
Adheres strictly to the verified endpoint contracts without fabricating endpoints or claims.
Honors unconfigured states honestly when no API key is supplied.
"""

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class Channel3Error(Exception):
    """Base exception for Channel3 operations."""

    pass


class Channel3NotConfiguredError(Channel3Error):
    """Raised when Channel3 is called without a valid configured API key."""

    pass


class Channel3AuthenticationError(Channel3Error):
    """Raised when Channel3 rejects the API key with 401 or 403."""

    pass


class Channel3RateLimitError(Channel3Error):
    """Raised when Channel3 rate limits requests with 429."""

    pass


class Channel3UnavailableError(Channel3Error):
    """Raised when Channel3 is unreachable, times out, or returns 5xx."""

    pass


@dataclass(frozen=True)
class Channel3ProductOffer:
    """Structured commercial offer returned from Channel3."""

    merchant_name: str
    product_name: str
    price_minor_units: int
    currency: str
    offer_url: str | None = None
    is_in_stock: bool = True
    barcode: str | None = None


class Channel3Adapter(BaseProvider):
    """Adapter for Channel3 search and commercial product offers API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = (
            api_key
            if api_key is not None
            else (
                settings.CHANNEL3_API_KEY.get_secret_value() if settings.CHANNEL3_API_KEY else None
            )
        )
        self._base_url = (base_url or settings.CHANNEL3_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "channel3"

    @property
    def is_configured(self) -> bool:
        """True if a non-empty API key is configured."""
        return bool(self._api_key and self._api_key.strip())

    async def check_health(self) -> tuple[bool, str | None]:
        """Check provider status without exposing credentials."""
        if not self.is_configured:
            return False, "Channel3 API key is not configured."

        url = f"{self._base_url}/search"
        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {"query": "test", "limit": 1}

        try:
            if self._client is not None:
                resp = await self._client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code == 200:
                return True, "Channel3 API reachable and authenticated."
            if resp.status_code in (401, 403):
                return False, "Channel3 API key rejected (unauthorized)."
            if resp.status_code == 429:
                return False, "Channel3 API rate limit exceeded."
            return False, f"Channel3 returned HTTP {resp.status_code}."
        except Exception as exc:
            logger.warning("Channel3 health check failed: %s", exc)
            return False, f"Channel3 unreachable: {exc}"

    async def search_offers(self, query: str, limit: int = 10) -> list[Channel3ProductOffer]:
        """Query Channel3 for commercial product offers.

        Raises Channel3NotConfiguredError if API key is missing.
        Raises Channel3AuthenticationError on 401/403.
        Raises Channel3RateLimitError on 429.
        Raises Channel3UnavailableError on 5xx or connection failures.
        """
        if not self.is_configured:
            raise Channel3NotConfiguredError(
                "Channel3 is not configured. Supply CHANNEL3_API_KEY in environment."
            )

        url = f"{self._base_url}/search"
        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        body = {"query": query.strip(), "limit": max(1, min(limit, 50))}

        try:
            if self._client is not None:
                response = await self._client.post(url, headers=headers, json=body)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=body)

            if response.status_code in (401, 403):
                raise Channel3AuthenticationError(
                    f"Channel3 authentication failed: HTTP {response.status_code}"
                )
            if response.status_code == 429:
                raise Channel3RateLimitError("Channel3 rate limit exceeded.")
            if response.status_code >= 500:
                raise Channel3UnavailableError(
                    f"Channel3 server error: HTTP {response.status_code}"
                )
            if response.status_code != 200:
                raise Channel3Error(f"Channel3 unexpected response: HTTP {response.status_code}")

            data = response.json()
            return self._parse_search_results(data)

        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            logger.error("Channel3 connection error: %s", net_err)
            raise Channel3UnavailableError(
                f"Channel3 request timed out or network error: {net_err}"
            ) from net_err

    def _parse_search_results(self, data: dict) -> list[Channel3ProductOffer]:
        """Conservatively parse offers from Channel3 response."""
        results: list[Channel3ProductOffer] = []
        raw_items = data.get("results") or data.get("products") or []
        for item in raw_items:
            # Parse price safely in minor units
            raw_price = item.get("price")
            minor_units = 0
            if isinstance(raw_price, int):
                minor_units = raw_price
            elif isinstance(raw_price, float):
                minor_units = int(round(raw_price * 100))
            elif isinstance(raw_price, str):
                try:
                    cleaned_val = raw_price.replace("$", "").replace(",", "")
                    minor_units = int(round(float(cleaned_val) * 100))
                except ValueError:
                    minor_units = 0

            currency = item.get("currency") or "USD"
            merchant = item.get("merchant") or item.get("store") or "Unknown Retailer"
            product_name = item.get("title") or item.get("name") or "Product"
            offer_url = item.get("url") or item.get("link")
            in_stock = item.get("in_stock", True)
            barcode = item.get("barcode") or item.get("upc") or item.get("ean")

            results.append(
                Channel3ProductOffer(
                    merchant_name=merchant,
                    product_name=product_name,
                    price_minor_units=minor_units,
                    currency=currency.upper(),
                    offer_url=offer_url,
                    is_in_stock=bool(in_stock),
                    barcode=str(barcode) if barcode else None,
                )
            )
        return results
