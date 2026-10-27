"""Product and Ingredient Catalog API routes.

Provides endpoints for:
- Product and variant retrieval by UUID and barcode
- Itemized ingredient lists for specific or current formula versions
- Standardized ingredient details with aliases
- Authenticated, rate-limited upstream product ingestion from Open Beauty Facts
- Historical formula reformulation tracking
- Commercial offer recording
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user, rate_limit_ingest
from app.db.session import get_db_session
from app.schemas.catalog import (
    IngestProductResponse,
    IngredientDetailResponse,
    ProductDetailResponse,
    ProductIngredientItemResponse,
    ProductIngredientListResponse,
    ProductOfferResponse,
)
from app.schemas.common import ResponseEnvelope
from app.services.catalog_service import CatalogService

router = APIRouter(tags=["Product & Ingredient Catalogue"])


class AddReformulationRequest(BaseModel):
    """Payload to record a newly reformulated version of a product."""

    formula_version: str = Field(
        ..., description="Unique version label (e.g. '2024-reformulation')"
    )
    raw_ingredient_text: str | None = Field(None, description="Updated packaging declaration")
    ingredient_names: list[str] = Field(..., description="Ordered list of ingredient names")
    data_source_code: str = Field("manual", description="Source code")


class AddOfferRequest(BaseModel):
    """Payload to record a commercial price offer."""

    merchant_name: str = Field(..., description="Merchant name (e.g. Sephora, Ulta)")
    price_minor_units: int = Field(
        ..., ge=0, description="Price in integer minor units (e.g. 1999 for $19.99)"
    )
    currency: str = Field("USD", min_length=3, max_length=3, description="ISO currency code")
    offer_url: str | None = Field(None, description="Direct product purchase link")
    is_in_stock: bool = Field(True, description="Stock availability")
    variant_id: UUID | None = Field(None, description="Variant association if SKU specific")


@router.get(
    "/products/{product_id}",
    response_model=ResponseEnvelope[ProductDetailResponse],
    summary="Get product detail by UUID",
)
async def get_product(
    product_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ProductDetailResponse]:
    """Retrieve product detail with brand metadata, variants, formula, and offers."""
    service = CatalogService(db)
    product = await service.get_product(product_id)
    return ResponseEnvelope(data=product)


@router.get(
    "/products/barcode/{barcode}",
    response_model=ResponseEnvelope[ProductDetailResponse],
    summary="Get product detail by barcode",
)
async def get_product_by_barcode(
    barcode: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ProductDetailResponse]:
    """Look up a product by EAN/UPC barcode."""
    service = CatalogService(db)
    product = await service.get_product_by_barcode(barcode)
    return ResponseEnvelope(data=product)


@router.get(
    "/products/{product_id}/ingredients",
    response_model=ResponseEnvelope[list[ProductIngredientItemResponse]],
    summary="Get ordered ingredient list for a product",
)
async def get_product_ingredients(
    product_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    formula_version: Annotated[
        str | None, Query(description="Specific formula version to inspect (defaults to current)")
    ] = None,
) -> ResponseEnvelope[list[ProductIngredientItemResponse]]:
    """Retrieve ordered, provenance-aware ingredients for a product formula."""
    service = CatalogService(db)
    ingredients = await service.get_product_ingredients(product_id, formula_version=formula_version)
    return ResponseEnvelope(data=ingredients)


@router.get(
    "/ingredients/{ingredient_id}",
    response_model=ResponseEnvelope[IngredientDetailResponse],
    summary="Get standardized ingredient details",
)
async def get_ingredient(
    ingredient_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[IngredientDetailResponse]:
    """Retrieve standardized INCI cosmetic ingredient definition, aliases, and safety rating."""
    service = CatalogService(db)
    ingredient = await service.get_ingredient(ingredient_id)
    return ResponseEnvelope(data=ingredient)


@router.post(
    "/products/ingest/barcode/{barcode}",
    response_model=ResponseEnvelope[IngestProductResponse],
    status_code=status.HTTP_200_OK,
    summary="Ingest product by barcode from Open Beauty Facts",
    dependencies=[Depends(rate_limit_ingest), Depends(get_current_active_user)],
)
async def ingest_product_from_barcode(
    barcode: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[IngestProductResponse]:
    """Authenticated endpoint to ingest a product by barcode from Open Beauty Facts.

    If already present in PostgreSQL, returns the existing record idempotently.
    Enqueues SearchOutbox synchronization events upon creation.
    """
    service = CatalogService(db)
    result = await service.ingest_from_barcode(barcode)
    return ResponseEnvelope(data=result)


@router.post(
    "/products/{product_id}/reformulate",
    response_model=ResponseEnvelope[ProductIngredientListResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record product reformulation (preserving historical formulas)",
    dependencies=[Depends(get_current_active_user)],
)
async def add_reformulation(
    product_id: UUID,
    payload: AddReformulationRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ProductIngredientListResponse]:
    """Record a formulation revision while preserving historical formula versions."""
    service = CatalogService(db)
    result = await service.add_formula_reformulation(
        product_id=product_id,
        formula_version=payload.formula_version,
        raw_ingredient_text=payload.raw_ingredient_text,
        ingredient_names=payload.ingredient_names,
        data_source_code=payload.data_source_code,
    )
    return ResponseEnvelope(data=result)


@router.post(
    "/products/{product_id}/offers",
    response_model=ResponseEnvelope[ProductOfferResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record commercial price offer",
    dependencies=[Depends(get_current_active_user)],
)
async def add_offer(
    product_id: UUID,
    payload: AddOfferRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ProductOfferResponse]:
    """Authenticated endpoint to record a commercial merchant price and availability offer."""
    service = CatalogService(db)
    result = await service.record_product_offer(
        product_id=product_id,
        merchant_name=payload.merchant_name,
        price_minor_units=payload.price_minor_units,
        currency=payload.currency,
        offer_url=payload.offer_url,
        is_in_stock=payload.is_in_stock,
        variant_id=payload.variant_id,
    )
    return ResponseEnvelope(data=result)
