"""Open Beauty Facts API provider adapter.

Provides asynchronous, rate-limit aware product and ingredient retrieval
grounded strictly in Open Beauty Facts v2 endpoints.

Attribution: Open Database License (ODbL) v1.0.
Official Documentation: https://openbeautyfacts.org/data
"""

import logging
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class OpenBeautyFactsError(Exception):
    """Base exception for Open Beauty Facts operations."""

    pass


class OpenBeautyFactsRateLimitError(OpenBeautyFactsError):
    """Raised when upstream returns HTTP 429 (Too Many Requests)."""

    pass


class OpenBeautyFactsUnavailableError(OpenBeautyFactsError):
    """Raised when upstream is unreachable, times out, or returns HTTP 5xx."""

    pass


@dataclass(frozen=True)
class ParsedIngredient:
    """Parsed ingredient declaration from packaging."""

    name: str
    position: int
    percent_estimate: float | None = None


@dataclass(frozen=True)
class OpenBeautyFactsProduct:
    """Structured product formulation retrieved from Open Beauty Facts."""

    barcode: str
    name: str
    brand: str
    category: str
    description: str | None = None
    raw_ingredients_text: str | None = None
    image_url: str | None = None
    ingredients: list[ParsedIngredient] = field(default_factory=list)
    attribution: str = "Data from Open Beauty Facts (ODbL 1.0) https://world.openbeautyfacts.org"
    license: str = "ODbL 1.0"


class OpenBeautyFactsAdapter(BaseProvider):
    """Official Open Beauty Facts v2 API client."""

    def __init__(
        self,
        base_url: str | None = None,
        user_agent: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.OPEN_BEAUTY_FACTS_BASE_URL).rstrip("/")
        self._user_agent = user_agent or settings.OPEN_BEAUTY_FACTS_USER_AGENT
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "open_beauty_facts"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            headers={"User-Agent": self._user_agent},
            timeout=self._timeout_seconds,
        )

    async def check_health(self) -> tuple[bool, str | None]:
        """Verify Open Beauty Facts API connectivity."""
        try:
            # Probe using a known standard public barcode (e.g. Nivea Creme or simple test)
            url = f"{self._base_url}/api/v2/product/4005808112852.json"
            if self._client is not None:
                resp = await self._client.get(url, headers={"User-Agent": self._user_agent})
            else:
                async with httpx.AsyncClient(
                    headers={"User-Agent": self._user_agent},
                    timeout=self._timeout_seconds,
                ) as client:
                    resp = await client.get(url)

            if resp.status_code in (200, 404):
                return True, "Open Beauty Facts API reachable and responding."
            if resp.status_code == 429:
                return False, "Open Beauty Facts API rate limit exceeded."
            return False, f"Open Beauty Facts API returned HTTP {resp.status_code}."
        except Exception as exc:
            logger.warning("Open Beauty Facts health check failed: %s", exc)
            return False, f"Open Beauty Facts unreachable: {exc}"

    async def fetch_product_by_barcode(self, barcode: str) -> OpenBeautyFactsProduct | None:
        """Fetch and parse product by EAN/UPC barcode.

        Returns None if product is not found in Open Beauty Facts.
        Raises OpenBeautyFactsRateLimitError on 429.
        Raises OpenBeautyFactsUnavailableError on 5xx or network errors.
        """
        cleaned_barcode = barcode.strip()
        if not cleaned_barcode or not cleaned_barcode.isdigit():
            raise ValueError(f"Invalid barcode format: {barcode}")

        url = f"{self._base_url}/api/v2/product/{cleaned_barcode}.json"

        try:
            if self._client is not None:
                response = await self._client.get(url, headers={"User-Agent": self._user_agent})
            else:
                async with httpx.AsyncClient(
                    headers={"User-Agent": self._user_agent},
                    timeout=self._timeout_seconds,
                ) as client:
                    response = await client.get(url)

            if response.status_code == 404:
                return None

            if response.status_code == 429:
                logger.warning(
                    "Open Beauty Facts rate limit (429) hit for barcode %s", cleaned_barcode
                )
                raise OpenBeautyFactsRateLimitError(
                    "Open Beauty Facts API rate limit exceeded. Please back off."
                )

            if response.status_code >= 500:
                logger.error(
                    "Open Beauty Facts server error %s for barcode %s",
                    response.status_code,
                    cleaned_barcode,
                )
                raise OpenBeautyFactsUnavailableError(
                    f"Open Beauty Facts server error: HTTP {response.status_code}"
                )

            if response.status_code != 200:
                logger.warning(
                    "Open Beauty Facts unexpected status %s for barcode %s",
                    response.status_code,
                    cleaned_barcode,
                )
                return None

            payload = response.json()
            # OBF returns status=0 if barcode not found in database
            if payload.get("status") == 0:
                return None

            product_raw = payload.get("product") or {}
            return self._parse_obf_product(cleaned_barcode, product_raw)

        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            logger.error("Open Beauty Facts network error: %s", net_err)
            raise OpenBeautyFactsUnavailableError(
                f"Open Beauty Facts connection failed: {net_err}"
            ) from net_err

    def _parse_obf_product(self, barcode: str, data: dict) -> OpenBeautyFactsProduct:
        """Extract schema fields conservatively without fabrication."""
        name = (
            data.get("product_name")
            or data.get("product_name_en")
            or data.get("generic_name")
            or "Unknown Product"
        )
        brand = data.get("brands") or data.get("brand_owner") or "Unknown Brand"
        # Take the primary brand if comma-separated
        if "," in brand:
            brand = brand.split(",")[0].strip()

        categories = data.get("categories") or "skincare"
        primary_category = categories.split(",")[0].strip() if "," in categories else categories

        raw_ingredients_text = (
            data.get("ingredients_text")
            or data.get("ingredients_text_en")
            or data.get("ingredients_text_with_allergens")
        )

        image_url = (
            data.get("image_url") or data.get("image_front_url") or data.get("image_small_url")
        )

        parsed_ingredients: list[ParsedIngredient] = []
        raw_list = data.get("ingredients") or []
        for idx, item in enumerate(raw_list, start=1):
            ing_text = item.get("text") or item.get("id", "").replace("en:", "")
            if ing_text:
                percent = item.get("percent_estimate")
                try:
                    percent_val = float(percent) if percent is not None else None
                except (ValueError, TypeError):
                    percent_val = None

                parsed_ingredients.append(
                    ParsedIngredient(
                        name=ing_text.strip(),
                        position=idx,
                        percent_estimate=percent_val,
                    )
                )

        return OpenBeautyFactsProduct(
            barcode=barcode,
            name=name.strip(),
            brand=brand.strip(),
            category=primary_category.strip(),
            raw_ingredients_text=raw_ingredients_text.strip() if raw_ingredients_text else None,
            image_url=image_url.strip() if image_url else None,
            ingredients=parsed_ingredients,
        )
