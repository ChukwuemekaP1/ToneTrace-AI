"""Pydantic schemas for the Product and Ingredient Catalogue.

Enforces:
- Clean commercial separation (offers and prices distinct from scientific formulas).
- Provenance and formula version history.
- Exact integer minor currency units.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BrandResponse(BaseModel):
    """Brand metadata representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    country_of_origin: str | None = None
    website: str | None = None
    description: str | None = None


class DataSourceResponse(BaseModel):
    """Data source provenance attribution."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    attribution_url: str | None = None
    license_or_terms: str | None = None


class ProductVariantResponse(BaseModel):
    """Specific commercial size or packaging SKU."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_name: str
    barcode: str | None = None
    size_or_volume: str | None = None
    sku: str | None = None


class ProductIngredientItemResponse(BaseModel):
    """Itemized ingredient in an ordered formula list."""

    position: int
    ingredient_id: UUID
    inci_name: str
    common_name: str | None = None
    function: str | None = None
    safety_rating: str = "safe"
    concentration_percentage: float | None = None
    notes: str | None = None


class ProductIngredientListResponse(BaseModel):
    """Formula version list with source provenance."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    formula_version: str
    is_current: bool
    raw_ingredient_text: str | None = None
    retrieved_at: datetime
    data_source: DataSourceResponse | None = None
    ingredients: list[ProductIngredientItemResponse] = Field(default_factory=list)


class ProductOfferResponse(BaseModel):
    """Commercial price and availability offer.

    Prices are stored in integer minor units (e.g. 1999 for $19.99).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_name: str
    offer_url: str | None = None
    price_minor_units: int
    currency: str = "USD"
    formatted_price: str
    is_in_stock: bool = True
    retrieved_at: datetime


class ProductDetailResponse(BaseModel):
    """Comprehensive product detail including formula versions and offers."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    brand: str
    brand_id: UUID | None = None
    category: str
    description: str | None = None
    ean_or_upc: str | None = None
    image_url: str | None = None
    brand_info: BrandResponse | None = None
    variants: list[ProductVariantResponse] = Field(default_factory=list)
    current_formula: ProductIngredientListResponse | None = None
    formula_history: list[ProductIngredientListResponse] = Field(default_factory=list)
    offers: list[ProductOfferResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class IngredientAliasResponse(BaseModel):
    """Synonym or trade name for a standardized ingredient."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alias_name: str
    alias_type: str


class IngredientDetailResponse(BaseModel):
    """Standardized ingredient with aliases and safety rating."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inci_name: str
    common_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    alias_records: list[IngredientAliasResponse] = Field(default_factory=list)
    function: str | None = None
    description: str | None = None
    safety_rating: str = "safe"
    created_at: datetime


class IngestProductResponse(BaseModel):
    """Response returned upon barcode ingestion."""

    product: ProductDetailResponse
    was_created: bool
    source_attribution: str


class Channel3OfferItem(BaseModel):
    """Commercial product offer returned from Channel3 API."""

    merchant_name: str
    product_name: str
    price_minor_units: int
    currency: str
    offer_url: str | None = None
    is_in_stock: bool = True
    channel3_product_id: str | None = None
    compare_at_price_minor_units: int | None = None
    condition: str | None = "new"
    max_commission_rate: float | None = None
    brand_name: str | None = None
    image_url: str | None = None


class Channel3ProductItem(BaseModel):
    """Product record returned from Channel3 universal catalog search."""

    id: str
    title: str
    description: str | None = None
    brand_name: str | None = None
    brand_id: str | None = None
    category_slug: str | None = None
    category_title: str | None = None
    image_url: str | None = None
    cleaned_image_url: str | None = None
    key_features: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    offers: list[Channel3OfferItem] = Field(default_factory=list)


class Channel3SearchResponse(BaseModel):
    """Paginated response from Channel3 v1 product search."""

    query: str
    products: list[Channel3ProductItem] = Field(default_factory=list)
    next_page_token: str | None = None
    total_returned: int = 0


class Channel3SyncOffersResponse(BaseModel):
    """Result of syncing live Channel3 merchant offers for a catalog product."""

    product_id: UUID
    product_name: str
    offers_synced: int
    offers: list[ProductOfferResponse] = Field(default_factory=list)
    retrieved_at: datetime
