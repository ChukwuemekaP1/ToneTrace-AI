"""Channel3 Universal Product Catalog and commercial offers provider adapter.

Implements the official Channel3 API v1 specification (https://api.trychannel3.com):
- POST /v1/search (lexical + semantic + agentic product search, structured filters, color palettes)
- GET /v1/products/{product_id} (free product detail & fresh offer hydration)
- POST /v1/similar ("more like this" from a known Channel3 product_id)
- POST /v1/lookup (merchant URL to canonical product resolution)
- User attribution via x-user-id header for affiliate click/conversion tracking
- Strict separation of commercial offers (integer minor currency units) from scientific evidence
"""

import logging
from dataclasses import dataclass, field
from typing import Any

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
    channel3_product_id: str | None = None
    compare_at_price_minor_units: int | None = None
    condition: str | None = "new"
    max_commission_rate: float | None = None
    brand_name: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class Channel3Product:
    """Canonical product returned by Channel3 v1 endpoints."""

    id: str
    title: str
    description: str | None = None
    brand_name: str | None = None
    brand_id: str | None = None
    category_slug: str | None = None
    category_title: str | None = None
    image_url: str | None = None
    cleaned_image_url: str | None = None
    key_features: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    structured_attributes: dict[str, list[str]] = field(default_factory=dict)
    offers: list[Channel3ProductOffer] = field(default_factory=list)


_UNSET: Any = object()


class Channel3Adapter(BaseProvider):
    """Adapter for Channel3 universal product catalog and commercial offers API."""

    def __init__(
        self,
        api_key: str | None = _UNSET,
        base_url: str | None = None,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        if api_key is _UNSET:
            self._api_key = (
                settings.CHANNEL3_API_KEY.get_secret_value() if settings.CHANNEL3_API_KEY else None
            )
        else:
            self._api_key = api_key
        raw_base = (base_url or settings.CHANNEL3_BASE_URL).rstrip("/")
        # Normalize base URL so both https://api.trychannel3.com and .../v1 work seamlessly
        if raw_base.endswith("/v1"):
            self._v1_base = raw_base
        else:
            self._v1_base = f"{raw_base}/v1"
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "channel3"

    @property
    def is_configured(self) -> bool:
        """True if a non-empty API key is configured."""
        return bool(self._api_key and self._api_key.strip())

    def _build_headers(self, user_id: str | None = None) -> dict[str, str]:
        """Construct Channel3 authentication and optional user-attribution headers."""
        headers: dict[str, str] = {
            "x-api-key": self._api_key or "",
            "Content-Type": "application/json",
        }
        if user_id:
            # Sanitize user_id per Channel3 spec: max 128 chars, alphanumeric and . _ @ -
            clean_uid = "".join(c for c in str(user_id) if c.isalnum() or c in "._@-")[:128]
            if clean_uid:
                headers["x-user-id"] = clean_uid
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute an authenticated HTTP request against Channel3 v1 API."""
        if not self.is_configured:
            raise Channel3NotConfiguredError(
                "Channel3 is not configured. Supply CHANNEL3_API_KEY in environment."
            )

        url = f"{self._v1_base}/{path.lstrip('/')}"
        headers = self._build_headers(user_id=user_id)

        try:
            if self._client is not None:
                if method.upper() == "GET":
                    response = await self._client.get(url, headers=headers, params=params)
                else:
                    response = await self._client.post(url, headers=headers, json=json_body)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=headers, params=params)
                    else:
                        response = await client.post(url, headers=headers, json=json_body)

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

            return response.json()

        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            logger.error("Channel3 connection error: %s", net_err)
            raise Channel3UnavailableError(
                f"Channel3 request timed out or network error: {net_err}"
            ) from net_err

    async def check_health(self) -> tuple[bool, str | None]:
        """Check provider status without exposing credentials."""
        if not self.is_configured:
            return False, "Channel3 API key is not configured."

        try:
            await self._request("POST", "/search", json_body={"query": "cleanser", "limit": 1})
            return True, "Channel3 API reachable and authenticated."
        except Channel3AuthenticationError:
            return False, "Channel3 API key rejected (unauthorized)."
        except Channel3RateLimitError:
            return False, "Channel3 API rate limit exceeded."
        except Exception as exc:
            logger.warning("Channel3 health check failed: %s", exc)
            return False, f"Channel3 unreachable: {exc}"

    async def search_products(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        page_token: str | None = None,
        user_id: str | None = None,
    ) -> tuple[list[Channel3Product], str | None]:
        """Search Channel3 universal catalog via POST /v1/search.

        Returns tuple of (products, next_page_token).
        """
        body: dict[str, Any] = {
            "query": query.strip(),
            "limit": max(1, min(limit, 30)),
        }
        if filters:
            body["filters"] = filters
        if config:
            body["config"] = config
        if page_token:
            body["page_token"] = page_token

        data = await self._request("POST", "/search", json_body=body, user_id=user_id)
        raw_items = data.get("products") or data.get("results") or []
        products = [self._parse_product(item) for item in raw_items]
        return products, data.get("next_page_token")

    async def get_product_details(
        self,
        product_id: str,
        selected_options: dict[str, str] | None = None,
        country: str | None = None,
        currency: str | None = None,
        user_id: str | None = None,
    ) -> Channel3Product:
        """Fetch full canonical product and fresh offers via GET /v1/products/{product_id}.

        Per Channel3 spec, this call is free and refreshes short-lived affiliate offer URLs.
        """
        params: dict[str, Any] = {}
        if country:
            params["country"] = country
        if currency:
            params["currency"] = currency
        if selected_options:
            for dim_name, label in selected_options.items():
                params[f"option_{dim_name}"] = label

        data = await self._request(
            "GET",
            f"/products/{product_id}",
            params=params or None,
            user_id=user_id,
        )
        return self._parse_product(data)

    async def find_similar(
        self,
        product_id: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> list[Channel3Product]:
        """Find similar products via POST /v1/similar given a Channel3 product_id."""
        body: dict[str, Any] = {
            "product_id": product_id,
            "limit": max(1, min(limit, 30)),
        }
        if filters:
            body["filters"] = filters
        if config:
            body["config"] = config

        data = await self._request("POST", "/similar", json_body=body, user_id=user_id)
        raw_items = data.get("products") or []
        return [self._parse_product(item) for item in raw_items]

    async def lookup_url(
        self,
        url: str,
        max_staleness_hours: int = 3,
        user_id: str | None = None,
    ) -> Channel3Product:
        """Resolve a merchant product URL to a canonical Channel3 Product via POST /v1/lookup."""
        body = {"url": url, "max_staleness_hours": max_staleness_hours}
        data = await self._request("POST", "/lookup", json_body=body, user_id=user_id)
        product_data = data.get("product") or data
        return self._parse_product(product_data)

    async def search_offers(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> list[Channel3ProductOffer]:
        """Query Channel3 and return flattened commercial product offers."""
        body: dict[str, Any] = {
            "query": query.strip(),
            "limit": max(1, min(limit, 30)),
        }
        if filters:
            body["filters"] = filters

        data = await self._request("POST", "/search", json_body=body, user_id=user_id)
        return self._parse_search_results(data)

    def _parse_product(self, item: dict[str, Any]) -> Channel3Product:
        """Parse a Channel3 Product JSON object into Channel3Product."""
        prod_id = str(item.get("id") or "")
        title = item.get("title") or item.get("name") or "Product"
        description = item.get("description")

        brands = item.get("brands") or []
        brand_name: str | None = item.get("brand_name") or item.get("brand")
        brand_id: str | None = item.get("brand_id")
        if brands and isinstance(brands, list) and isinstance(brands[0], dict):
            brand_name = brands[0].get("name") or brand_name
            brand_id = brands[0].get("id") or brand_id

        cat = item.get("category")
        cat_slug = cat.get("slug") if isinstance(cat, dict) else item.get("category_slug")
        cat_title = cat.get("title") if isinstance(cat, dict) else item.get("category_title")

        images = item.get("images") or []
        image_url: str | None = item.get("image_url")
        cleaned_image_url: str | None = item.get("cleaned_image_url")
        if images and isinstance(images, list) and isinstance(images[0], dict):
            main_imgs = [
                img for img in images if isinstance(img, dict) and img.get("is_main_image")
            ]
            chosen = main_imgs[0] if main_imgs else images[0]
            image_url = chosen.get("url") or image_url
            cleaned_image_url = chosen.get("cleaned_url") or cleaned_image_url

        offers = self._extract_offers_from_item(
            item,
            default_product_name=title,
            channel3_product_id=prod_id or None,
            brand_name=brand_name,
            image_url=cleaned_image_url or image_url,
        )

        return Channel3Product(
            id=prod_id,
            title=title,
            description=description,
            brand_name=brand_name,
            brand_id=brand_id,
            category_slug=cat_slug,
            category_title=cat_title,
            image_url=image_url,
            cleaned_image_url=cleaned_image_url,
            key_features=item.get("key_features") or [],
            materials=item.get("materials") or [],
            structured_attributes=item.get("structured_attributes") or {},
            offers=offers,
        )

    def _parse_search_results(self, data: dict[str, Any]) -> list[Channel3ProductOffer]:
        """Conservatively parse offers from Channel3 response (v1 nested offers & flat fixtures)."""
        results: list[Channel3ProductOffer] = []
        raw_items = data.get("products") or data.get("results") or []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            product_name = item.get("title") or item.get("name") or "Product"
            prod_id = str(item.get("id")) if item.get("id") else None
            brands = item.get("brands") or []
            brand_name = (
                brands[0].get("name")
                if brands and isinstance(brands[0], dict)
                else item.get("brand")
            )
            images = item.get("images") or []
            img_url = (
                images[0].get("url")
                if images and isinstance(images[0], dict)
                else item.get("image_url")
            )
            results.extend(
                self._extract_offers_from_item(
                    item,
                    default_product_name=product_name,
                    channel3_product_id=prod_id,
                    brand_name=brand_name,
                    image_url=img_url,
                )
            )
        return results

    def _extract_offers_from_item(
        self,
        item: dict[str, Any],
        default_product_name: str,
        channel3_product_id: str | None = None,
        brand_name: str | None = None,
        image_url: str | None = None,
    ) -> list[Channel3ProductOffer]:
        """Extract offers from either nested Channel3 v1 `offers` array or flat offer dict."""
        extracted: list[Channel3ProductOffer] = []
        nested_offers = item.get("offers")

        if isinstance(nested_offers, list) and nested_offers:
            for offer in nested_offers:
                if not isinstance(offer, dict):
                    continue
                price_obj = offer.get("price")
                minor_units = 0
                compare_minor: int | None = None
                currency = "USD"

                if isinstance(price_obj, dict):
                    raw_val = price_obj.get("price")
                    if isinstance(raw_val, (int, float)):
                        minor_units = int(round(float(raw_val) * 100))
                    comp_val = price_obj.get("compare_at_price")
                    if isinstance(comp_val, (int, float)):
                        compare_minor = int(round(float(comp_val) * 100))
                    currency = str(price_obj.get("currency") or "USD").upper()
                elif isinstance(price_obj, (int, float)):
                    minor_units = int(round(float(price_obj) * 100))

                avail = str(offer.get("availability") or "InStock")
                is_in_stock = avail.lower() != "outofstock"
                domain = offer.get("domain") or offer.get("merchant") or "Unknown Retailer"
                offer_url = offer.get("url")
                condition = offer.get("condition")
                comm_rate = offer.get("max_commission_rate")

                extracted.append(
                    Channel3ProductOffer(
                        merchant_name=str(domain),
                        product_name=default_product_name,
                        price_minor_units=minor_units,
                        currency=currency,
                        offer_url=offer_url,
                        is_in_stock=is_in_stock,
                        barcode=str(item.get("barcode")) if item.get("barcode") else None,
                        channel3_product_id=channel3_product_id,
                        compare_at_price_minor_units=compare_minor,
                        condition=str(condition) if condition else None,
                        max_commission_rate=float(comm_rate) if comm_rate is not None else None,
                        brand_name=brand_name,
                        image_url=image_url,
                    )
                )
            return extracted

        # Fallback for flat offer structure in legacy/test fixtures
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

        currency = str(item.get("currency") or "USD").upper()
        merchant = (
            item.get("merchant") or item.get("domain") or item.get("store") or "Unknown Retailer"
        )
        offer_url = item.get("url") or item.get("link")
        in_stock = item.get("in_stock", True)
        barcode = item.get("barcode") or item.get("upc") or item.get("ean")

        extracted.append(
            Channel3ProductOffer(
                merchant_name=str(merchant),
                product_name=default_product_name,
                price_minor_units=minor_units,
                currency=currency,
                offer_url=offer_url,
                is_in_stock=bool(in_stock),
                barcode=str(barcode) if barcode else None,
                channel3_product_id=channel3_product_id,
                brand_name=brand_name,
                image_url=image_url,
            )
        )
        return extracted
