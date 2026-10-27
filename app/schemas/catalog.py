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
