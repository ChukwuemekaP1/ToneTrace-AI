"""Schemas for product and ingredient search queries, hits, and facets."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProductSearchHit(BaseModel):
    """Single product search result item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand: str
    category: str
    description: str | None = None
    full_ingredient_list: str | None = None
    ingredient_names: list[str] = Field(default_factory=list)
    image_url: str | None = None
    score: float | None = None


class IngredientSearchHit(BaseModel):
    """Single cosmetic ingredient search result item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    inci_name: str
    common_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    function: str | None = None
    safety_rating: str = "safe"
    description: str | None = None
    score: float | None = None


class SearchFacetBucket(BaseModel):
    """Single aggregation term and document count."""

    key: str
    doc_count: int


class SearchResultsResponse[T](BaseModel):
    """Paginated search response envelope with faceting metadata."""

    items: list[T] = Field(default_factory=list)
    total: int = Field(ge=0, description="Total matching documents")
    page: int = Field(ge=1, description="Current page index")
    page_size: int = Field(ge=1, le=100, description="Items per page")
    total_pages: int = Field(ge=0, description="Total number of pages")
    facets: dict[str, list[SearchFacetBucket]] = Field(default_factory=dict)


class ProductSearchQuery(BaseModel):
    """Filter and pagination criteria for cosmetic product search."""

    q: str | None = Field(default=None, max_length=200, description="Free text search term")
    brand: str | None = Field(default=None, max_length=150, description="Filter by brand name")
    category: str | None = Field(
        default=None, max_length=100, description="Filter by product category"
    )
    exclude_ingredients: list[str] = Field(
        default_factory=list,
        description="Filter out products containing these ingredient names (for sensitivities)",
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = Field(
        default="relevance",
        pattern="^(relevance|name_asc|name_desc|updated_at_desc)$",
        description="Deterministic sort order",
    )


class IngredientSearchQuery(BaseModel):
    """Filter and pagination criteria for ingredient search."""

    q: str | None = Field(default=None, max_length=200, description="Free text search term")
    function: str | None = Field(default=None, max_length=150, description="Filter by function")
    safety_rating: str | None = Field(
        default=None, max_length=50, description="Filter by safety classification"
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ReindexResponse(BaseModel):
    """Diagnostic response summary for catalog reindexing."""

    status: str = "completed"
    products_indexed: int
    ingredients_indexed: int
    duration_seconds: float
    details: dict[str, Any] = Field(default_factory=dict)
