"""Search endpoints for cosmetic products, ingredients, and index synchronization."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user
from app.db.models import User
from app.db.session import get_db_session
from app.schemas.common import ResponseEnvelope
from app.schemas.search import (
    IngredientSearchHit,
    IngredientSearchQuery,
    ProductSearchHit,
    ProductSearchQuery,
    ReindexResponse,
    SearchResultsResponse,
)
from app.services.search_outbox_service import SearchOutboxService
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["Catalog Search"])


@router.get(
    "/products",
    response_model=ResponseEnvelope[SearchResultsResponse[ProductSearchHit]],
    status_code=status.HTTP_200_OK,
    summary="Search cosmetic products with text matching and sensitivity exclusion",
)
async def search_products(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    q: Annotated[str | None, Query(max_length=200, description="Search term")] = None,
    brand: Annotated[str | None, Query(max_length=150, description="Filter by brand")] = None,
    category: Annotated[str | None, Query(max_length=100, description="Filter by category")] = None,
    exclude_ingredients: Annotated[
        list[str] | None,
        Query(description="List of ingredients to exclude (e.g. user sensitivities)"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    sort_by: Annotated[
        str,
        Query(
            pattern="^(relevance|name_asc|name_desc|updated_at_desc)$",
            description="Sorting order",
        ),
    ] = "relevance",
) -> ResponseEnvelope[SearchResultsResponse[ProductSearchHit]]:
    """Execute product search against Elasticsearch."""
    query = ProductSearchQuery(
        q=q,
        brand=brand,
        category=category,
        exclude_ingredients=exclude_ingredients or [],
        page=page,
        page_size=page_size,
        sort_by=sort_by,
    )
    service = SearchService(db=db)
    results = await service.search_products(query)
    return ResponseEnvelope(data=results)


@router.get(
    "/ingredients",
    response_model=ResponseEnvelope[SearchResultsResponse[IngredientSearchHit]],
    status_code=status.HTTP_200_OK,
    summary="Search cosmetic ingredients with autocomplete, function, and safety rating filters",
)
async def search_ingredients(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    q: Annotated[str | None, Query(max_length=200, description="Search term")] = None,
    function: Annotated[str | None, Query(max_length=150, description="Filter by function")] = None,
    safety_rating: Annotated[
        str | None, Query(max_length=50, description="Filter by safety classification")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
) -> ResponseEnvelope[SearchResultsResponse[IngredientSearchHit]]:
    """Execute ingredient search against Elasticsearch."""
    query = IngredientSearchQuery(
        q=q,
        function=function,
        safety_rating=safety_rating,
        page=page,
        page_size=page_size,
    )
    service = SearchService(db=db)
    results = await service.search_ingredients(query)
    return ResponseEnvelope(data=results)


@router.post(
    "/reindex",
    response_model=ResponseEnvelope[ReindexResponse],
    status_code=status.HTTP_200_OK,
    summary="Rebuild entire Elasticsearch index directly from authoritative PostgreSQL tables",
)
async def trigger_full_reindex(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[ReindexResponse]:
    """Diagnostic endpoint to perform a full reindexing from PostgreSQL."""
    service = SearchService(db=db)
    result = await service.reindex_all_from_db()
    return ResponseEnvelope(data=result)


@router.post(
    "/sync-outbox",
    response_model=ResponseEnvelope[dict[str, int]],
    status_code=status.HTTP_200_OK,
    summary="Process pending transactional outbox events to Elasticsearch",
)
async def process_outbox(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    batch_size: Annotated[int, Query(ge=1, le=500, description="Batch size")] = 50,
) -> ResponseEnvelope[dict[str, int]]:
    """Manually drain pending transactional outbox sync events to Elasticsearch."""
    outbox_service = SearchOutboxService(db=db)
    summary = await outbox_service.process_outbox_batch(batch_size=batch_size)
    return ResponseEnvelope(data=summary)
