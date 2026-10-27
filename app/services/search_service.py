"""Domain search service executing queries, aggregations, and rebuilds against Elasticsearch."""

import logging
import math
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.errors import DependencyError
from app.db.models import Ingredient, Product
from app.providers.search_provider import SearchProvider, get_search_provider
from app.schemas.search import (
    IngredientSearchHit,
    IngredientSearchQuery,
    ProductSearchHit,
    ProductSearchQuery,
    ReindexResponse,
    SearchFacetBucket,
    SearchResultsResponse,
)
from app.services.base import BaseService

logger = logging.getLogger("tonetrace.search_service")


class SearchService(BaseService):
    """Encapsulates catalog search queries, facet aggregation, and PostgreSQL-to-ES reindexing."""

    def __init__(
        self,
        db: AsyncSession,
        search_provider: SearchProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(db=db)
        self.settings = settings or get_settings()
        self.search_provider = search_provider or get_search_provider()

    def _verify_search_availability(self) -> None:
        """Verify that the search subsystem is enabled and ready to accept queries."""
        if not self.settings.ELASTICSEARCH_ENABLED:
            raise DependencyError(
                "Search service is disabled by server configuration.",
                status_code=503,
            )

        is_healthy, msg, _ = self.search_provider.check_health()
        if not is_healthy:
            raise DependencyError(
                f"Search service is currently unavailable: {msg}",
                status_code=503,
            )

    async def search_products(
        self,
        query: ProductSearchQuery,
    ) -> SearchResultsResponse[ProductSearchHit]:
        """Execute product search with text matching, filters, and ingredient avoidance."""
        self._verify_search_availability()

        bool_query: dict[str, Any] = {"must": [], "filter": [], "must_not": []}

        # 1. Free-text query
        if query.q and query.q.strip():
            bool_query["must"].append(
                {
                    "multi_match": {
                        "query": query.q.strip(),
                        "fields": [
                            "name^3",
                            "name.autocomplete^2",
                            "brand^2",
                            "brand.autocomplete",
                            "description",
                            "full_ingredient_list",
                        ],
                        "type": "best_fields",
                    }
                }
            )
        else:
            bool_query["must"].append({"match_all": {}})

        # 2. Strict filters
        if query.brand and query.brand.strip():
            bool_query["filter"].append({"term": {"brand.keyword": query.brand.strip()}})
        if query.category and query.category.strip():
            bool_query["filter"].append({"term": {"category": query.category.strip().lower()}})

        # 3. Sensitivity Avoidance (Exclusion)
        if query.exclude_ingredients:
            normalized_exclusions = [
                i.strip().lower() for i in query.exclude_ingredients if i.strip()
            ]
            if normalized_exclusions:
                bool_query["must_not"].append(
                    {"terms": {"ingredient_names": normalized_exclusions}}
                )

        # 4. Deterministic Sort Order
        sort_criteria: list[dict[str, Any]]
        if query.sort_by == "name_asc":
            sort_criteria = [{"name.keyword": "asc"}, {"id": "asc"}]
        elif query.sort_by == "name_desc":
            sort_criteria = [{"name.keyword": "desc"}, {"id": "asc"}]
        elif query.sort_by == "updated_at_desc":
            sort_criteria = [{"updated_at": "desc"}, {"id": "asc"}]
        else:
            # Default: relevance score with secondary stable sort by ID
            sort_criteria = [{"_score": "desc"}, {"id": "asc"}]

        # 5. Build full Elasticsearch request body
        from_offset = (query.page - 1) * query.page_size
        body: dict[str, Any] = {
            "query": {"bool": bool_query},
            "from": from_offset,
            "size": query.page_size,
            "sort": sort_criteria,
            "aggs": {
                "categories": {"terms": {"field": "category", "size": 20}},
                "brands": {"terms": {"field": "brand.keyword", "size": 20}},
            },
        }

        try:
            raw_response = self.search_provider.execute_search(
                self.search_provider.products_alias,
                body,
            )
        except Exception as exc:
            logger.error(f"Elasticsearch query failed: {exc}")
            raise DependencyError(
                "Failed to execute search query against search engine.",
                status_code=503,
            ) from exc

        # 6. Parse hits
        hits = raw_response.get("hits", {})
        total_hits = hits.get("total", {}).get("value", 0)

        items: list[ProductSearchHit] = []
        for hit in hits.get("hits", []):
            src = hit.get("_source", {})
            items.append(
                ProductSearchHit(
                    id=uuid.UUID(src["id"]),
                    name=src["name"],
                    brand=src["brand"],
                    category=src["category"],
                    description=src.get("description"),
                    full_ingredient_list=src.get("full_ingredient_list"),
                    ingredient_names=src.get("ingredient_names", []),
                    image_url=src.get("image_url"),
                    score=hit.get("_score"),
                )
            )

        # 7. Parse facets
        facets: dict[str, list[SearchFacetBucket]] = {}
        for agg_name, agg_data in raw_response.get("aggregations", {}).items():
            facets[agg_name] = [
                SearchFacetBucket(key=b["key"], doc_count=b["doc_count"])
                for b in agg_data.get("buckets", [])
            ]

        total_pages = math.ceil(total_hits / query.page_size) if query.page_size else 0

        return SearchResultsResponse(
            items=items,
            total=total_hits,
            page=query.page,
            page_size=query.page_size,
            total_pages=total_pages,
            facets=facets,
        )

    async def search_ingredients(
        self,
        query: IngredientSearchQuery,
    ) -> SearchResultsResponse[IngredientSearchHit]:
        """Execute ingredient search with autocomplete and function/safety filters."""
        self._verify_search_availability()

        bool_query: dict[str, Any] = {"must": [], "filter": []}

        if query.q and query.q.strip():
            bool_query["must"].append(
                {
                    "multi_match": {
                        "query": query.q.strip(),
                        "fields": [
                            "inci_name^3",
                            "inci_name.autocomplete^2",
                            "common_name^2",
                            "common_name.autocomplete",
                            "aliases",
                            "description",
                        ],
                        "type": "best_fields",
                    }
                }
            )
        else:
            bool_query["must"].append({"match_all": {}})

        if query.function and query.function.strip():
            bool_query["filter"].append({"term": {"function": query.function.strip().lower()}})
        if query.safety_rating and query.safety_rating.strip():
            bool_query["filter"].append(
                {"term": {"safety_rating": query.safety_rating.strip().lower()}}
            )

        from_offset = (query.page - 1) * query.page_size
        body: dict[str, Any] = {
            "query": {"bool": bool_query},
            "from": from_offset,
            "size": query.page_size,
            "sort": [{"_score": "desc"}, {"id": "asc"}],
            "aggs": {
                "functions": {"terms": {"field": "function", "size": 20}},
                "safety_ratings": {"terms": {"field": "safety_rating", "size": 10}},
            },
        }

        try:
            raw_response = self.search_provider.execute_search(
                self.search_provider.ingredients_alias,
                body,
            )
        except Exception as exc:
            logger.error(f"Elasticsearch ingredient search failed: {exc}")
            raise DependencyError(
                "Failed to execute ingredient search query.",
                status_code=503,
            ) from exc

        hits = raw_response.get("hits", {})
        total_hits = hits.get("total", {}).get("value", 0)

        items: list[IngredientSearchHit] = []
        for hit in hits.get("hits", []):
            src = hit.get("_source", {})
            items.append(
                IngredientSearchHit(
                    id=uuid.UUID(src["id"]),
                    inci_name=src["inci_name"],
                    common_name=src.get("common_name"),
                    aliases=src.get("aliases", []),
                    function=src.get("function"),
                    safety_rating=src.get("safety_rating", "safe"),
                    description=src.get("description"),
                    score=hit.get("_score"),
                )
            )

        facets: dict[str, list[SearchFacetBucket]] = {}
        for agg_name, agg_data in raw_response.get("aggregations", {}).items():
            facets[agg_name] = [
                SearchFacetBucket(key=b["key"], doc_count=b["doc_count"])
                for b in agg_data.get("buckets", [])
            ]

        total_pages = math.ceil(total_hits / query.page_size) if query.page_size else 0

        return SearchResultsResponse(
            items=items,
            total=total_hits,
            page=query.page,
            page_size=query.page_size,
            total_pages=total_pages,
            facets=facets,
        )

    async def reindex_all_from_db(self) -> ReindexResponse:
        """Rebuild entire Elasticsearch indices directly from authoritative PostgreSQL tables."""
        start_time = time.perf_counter()

        # 1. Ensure cluster is online and index schemas are current
        self._verify_search_availability()
        self.search_provider.ensure_indices_and_aliases()

        # 2. Reindex Ingredients
        ing_stmt = select(Ingredient)
        ingredients = list((await self.db.execute(ing_stmt)).scalars().all())

        ingredient_docs = [
            {
                "id": str(i.id),
                "inci_name": i.inci_name,
                "common_name": i.common_name,
                "aliases": i.aliases or [],
                "function": i.function,
                "safety_rating": i.safety_rating,
                "description": i.description,
                "updated_at": i.updated_at.isoformat(),
            }
            for i in ingredients
        ]

        indexed_ingredients, ing_errs = self.search_provider.bulk_index_documents(
            self.search_provider.ingredients_alias,
            ingredient_docs,
        )

        # 3. Reindex Products with joined ingredients
        prod_stmt = select(Product).options(
            selectinload(Product.product_ingredients).joinedload(
                Product.product_ingredients.property.mapper.class_.ingredient
            )
        )
        products = list((await self.db.execute(prod_stmt)).scalars().all())

        product_docs = []
        for p in products:
            ing_names: list[str] = []
            ing_ids: list[str] = []
            for pi in p.product_ingredients:
                if pi.ingredient:
                    ing_names.append(pi.ingredient.inci_name.lower())
                    ing_ids.append(str(pi.ingredient.id))

            product_docs.append(
                {
                    "id": str(p.id),
                    "name": p.name,
                    "brand": p.brand,
                    "category": p.category,
                    "description": p.description,
                    "full_ingredient_list": p.full_ingredient_list,
                    "ingredient_names": ing_names,
                    "ingredient_ids": ing_ids,
                    "ean_or_upc": p.ean_or_upc,
                    "image_url": p.image_url,
                    "updated_at": p.updated_at.isoformat(),
                }
            )

        indexed_products, prod_errs = self.search_provider.bulk_index_documents(
            self.search_provider.products_alias,
            product_docs,
        )

        # 4. Explicitly refresh indices
        self.search_provider.refresh_index(self.search_provider.products_alias)
        self.search_provider.refresh_index(self.search_provider.ingredients_alias)

        duration = time.perf_counter() - start_time
        logger.info(
            f"Full reindex completed in {duration:.2f}s: {indexed_products} products, "
            f"{indexed_ingredients} ingredients."
        )

        return ReindexResponse(
            status="completed",
            products_indexed=indexed_products,
            ingredients_indexed=indexed_ingredients,
            duration_seconds=round(duration, 2),
            details={
                "product_errors": len(prod_errs),
                "ingredient_errors": len(ing_errs),
            },
        )
