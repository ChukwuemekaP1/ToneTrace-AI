"""API routes for My Shelf and Product Discovery (Phase 9).

Provides:
- GET /api/v1/me/shelf
- POST /api/v1/me/shelf
- GET /api/v1/me/shelf/{item_id}
- PATCH /api/v1/me/shelf/{item_id}
- DELETE /api/v1/me/shelf/{item_id}
- GET /api/v1/discovery/products
- GET /api/v1/discovery/products/{product_id}
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.ai import get_llm_explanation_provider
from app.core.config import Settings, get_settings
from app.core.security import get_current_active_user
from app.db.models import User
from app.db.session import get_db_session
from app.providers.gemini import LLMExplanationProvider
from app.providers.search_provider import SearchProvider, get_search_provider
from app.schemas.common import ResponseEnvelope
from app.schemas.shelf import (
    DiscoveryProductDetailResponse,
    DiscoveryProductListResponse,
    ShelfItemCreateRequest,
    ShelfItemResponse,
    ShelfItemUpdateRequest,
    ShelfListResponse,
    ShelfStatusLiteral,
)
from app.services.shelf_service import DiscoveryService, ShelfService

router = APIRouter(tags=["My Shelf & Product Discovery"])


@router.get(
    "/me/shelf",
    response_model=ResponseEnvelope[ShelfListResponse],
    summary="List authenticated user's personal product shelf",
)
async def list_my_shelf(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status_filter: Annotated[
        ShelfStatusLiteral | None,
        Query(alias="status", description="Optional filter by shelf status"),
    ] = None,
    category: Annotated[
        str | None,
        Query(description="Optional filter by product category"),
    ] = None,
    is_custom: Annotated[
        bool | None,
        Query(description="Optional filter for custom vs catalogue-linked items"),
    ] = None,
    sort_by: Annotated[
        Literal["created_at_desc", "name_asc", "opened_at_desc"],
        Query(description="Deterministic sort order"),
    ] = "created_at_desc",
) -> ResponseEnvelope[ShelfListResponse]:
    """List user-owned shelf items with sensitivity checks and reaction logs."""
    service = ShelfService(db)
    result = await service.list_shelf_items(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        category_filter=category,
        is_custom_filter=is_custom,
        sort_by=sort_by,
    )
    return ResponseEnvelope(data=result)


@router.post(
    "/me/shelf",
    response_model=ResponseEnvelope[ShelfItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a catalogue-linked or custom product to My Shelf",
)
async def add_to_my_shelf(
    payload: ShelfItemCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ShelfItemResponse]:
    """Add a product to the authenticated user's private shelf."""
    service = ShelfService(db)
    item = await service.add_shelf_item(user=current_user, payload=payload)
    return ResponseEnvelope(data=item)


@router.get(
    "/me/shelf/{item_id}",
    response_model=ResponseEnvelope[ShelfItemResponse],
    summary="Get a single item from My Shelf",
)
async def get_my_shelf_item(
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ShelfItemResponse]:
    """Retrieve details, sensitivity alerts, and reactions for a user-owned shelf item."""
    service = ShelfService(db)
    item = await service.get_shelf_item(user_id=current_user.id, item_id=item_id)
    return ResponseEnvelope(data=item)


@router.patch(
    "/me/shelf/{item_id}",
    response_model=ResponseEnvelope[ShelfItemResponse],
    summary="Update a shelf item or record a product reaction",
)
async def update_my_shelf_item(
    item_id: UUID,
    payload: ShelfItemUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ShelfItemResponse]:
    """Update status, opened date, private notes, custom fields, or append a reaction."""
    service = ShelfService(db)
    item = await service.update_shelf_item(
        user_id=current_user.id,
        item_id=item_id,
        payload=payload,
    )
    return ResponseEnvelope(data=item)


@router.delete(
    "/me/shelf/{item_id}",
    response_model=ResponseEnvelope[dict[str, str]],
    summary="Remove an item from My Shelf",
)
async def delete_my_shelf_item(
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[dict[str, str]]:
    """Delete a user-owned shelf item and its associated reaction records."""
    service = ShelfService(db)
    result = await service.delete_shelf_item(user_id=current_user.id, item_id=item_id)
    return ResponseEnvelope(data=result)


@router.get(
    "/discovery/products",
    response_model=ResponseEnvelope[DiscoveryProductListResponse],
    summary="Discover products with explainable, source-backed suitability rules",
)
async def discover_products(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    search_provider: Annotated[SearchProvider, Depends(get_search_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    q: Annotated[
        str | None,
        Query(
            max_length=150, description="Optional search query across names, brands, ingredients"
        ),
    ] = None,
    category: Annotated[
        str | None,
        Query(max_length=100, description="Optional filter by skincare category"),
    ] = None,
    brand: Annotated[
        str | None,
        Query(max_length=150, description="Optional filter by brand name"),
    ] = None,
    goal: Annotated[
        str | None,
        Query(
            max_length=100,
            description=(
                "Optional target skincare goal (e.g. hyperpigmentation, hydration, redness)"
            ),
        ),
    ] = None,
    exclude_user_sensitivities: Annotated[
        bool,
        Query(description="Automatically exclude products matching user sensitivities/reactions"),
    ] = True,
    exclude_ingredients: Annotated[
        list[str] | None,
        Query(description="Additional ingredient names to exclude"),
    ] = None,
    require_complete_ingredients: Annotated[
        bool,
        Query(description="If true, exclude products with missing or incomplete ingredient lists"),
    ] = False,
    sort_by: Annotated[
        Literal["suitability_desc", "relevance", "name_asc", "name_desc", "updated_at_desc"],
        Query(description="Deterministic sort order"),
    ] = "suitability_desc",
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=50, description="Items per page")] = 20,
) -> ResponseEnvelope[DiscoveryProductListResponse]:
    """Search and evaluate catalogue products using Elasticsearch, PostgreSQL, and rules."""
    service = DiscoveryService(
        db=db,
        search_provider=search_provider,
        settings=settings,
    )
    result = await service.discover_products(
        user=current_user,
        q=q,
        category=category,
        brand=brand,
        goal=goal,
        exclude_user_sensitivities=exclude_user_sensitivities,
        exclude_ingredients=exclude_ingredients,
        require_complete_ingredients=require_complete_ingredients,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    return ResponseEnvelope(data=result)


@router.get(
    "/discovery/products/{product_id}",
    response_model=ResponseEnvelope[DiscoveryProductDetailResponse],
    summary="Retrieve product discovery detail, rule trace, and optional grounded AI explanation",
)
async def get_discovery_product_detail(
    product_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    search_provider: Annotated[SearchProvider, Depends(get_search_provider)],
    llm_provider: Annotated[LLMExplanationProvider, Depends(get_llm_explanation_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    goal: Annotated[
        str | None,
        Query(max_length=100, description="Optional target skincare goal for rule evaluation"),
    ] = None,
    include_ai_explanation: Annotated[
        bool,
        Query(
            description=(
                "If true, include a Gemini explanation grounded strictly in retrieved "
                "product, ingredient, and evidence source IDs"
            )
        ),
    ] = False,
) -> ResponseEnvelope[DiscoveryProductDetailResponse]:
    """Retrieve canonical PostgreSQL product details, rules, and optional AI explanation."""
    service = DiscoveryService(
        db=db,
        search_provider=search_provider,
        llm_provider=llm_provider,
        settings=settings,
    )
    result = await service.get_discovery_product_detail(
        user=current_user,
        product_id=product_id,
        goal=goal,
        include_ai_explanation=include_ai_explanation,
    )
    return ResponseEnvelope(data=result)
