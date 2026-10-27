"""Elasticsearch provider managing cluster connections, mappings, lifecycle, and bulk indexing."""

import logging
import time
from typing import Any

from elasticsearch import ApiError, Elasticsearch, TransportError
from elasticsearch.helpers import bulk

from app.core.config import Settings, get_settings
from app.core.errors import DependencyError

logger = logging.getLogger("tonetrace.search_provider")


class SearchProvider:
    """Manages the Elasticsearch client, index lifecycle, mappings, and search execution."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: Elasticsearch | None = None

    @property
    def client(self) -> Elasticsearch:
        """Lazy-loaded singleton Elasticsearch client instance."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> Elasticsearch:
        """Construct the official Elasticsearch Python client with TLS and auth parameters."""
        if not self.settings.ELASTICSEARCH_URL:
            raise DependencyError("Elasticsearch URL is not configured.")

        client_kwargs: dict[str, Any] = {
            "hosts": [self.settings.ELASTICSEARCH_URL],
            "request_timeout": self.settings.ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS,
            "verify_certs": self.settings.ELASTICSEARCH_VERIFY_CERTS,
        }

        # Priority 1: API Key authentication
        if (
            self.settings.ELASTICSEARCH_API_KEY
            and self.settings.ELASTICSEARCH_API_KEY.get_secret_value().strip()
        ):
            client_kwargs["api_key"] = (
                self.settings.ELASTICSEARCH_API_KEY.get_secret_value().strip()
            )
        # Priority 2: Basic HTTP authentication
        elif self.settings.ELASTICSEARCH_USERNAME and self.settings.ELASTICSEARCH_PASSWORD:
            client_kwargs["basic_auth"] = (
                self.settings.ELASTICSEARCH_USERNAME,
                self.settings.ELASTICSEARCH_PASSWORD.get_secret_value(),
            )

        return Elasticsearch(**client_kwargs)

    def close(self) -> None:
        """Close the underlying Elasticsearch client transport cleanly."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def check_health(self) -> tuple[bool, str, float | None]:
        """Perform a cluster health check and return connectivity status and latency.

        Returns:
            (is_healthy, summary_message, latency_ms)
        """
        if not self.settings.ELASTICSEARCH_ENABLED:
            return False, "Elasticsearch is disabled in configuration.", None

        if not self.settings.ELASTICSEARCH_URL:
            return False, "Elasticsearch URL is unconfigured.", None

        start_time = time.perf_counter()
        try:
            info = self.client.info()
            health = self.client.cluster.health()
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            cluster_name = info.get("cluster_name", "unknown")
            version = info.get("version", {}).get("number", "unknown")
            cluster_status = health.get("status", "unknown")

            msg = f"Connected to {cluster_name} v{version} (status: {cluster_status})"
            return True, msg, round(duration_ms, 2)
        except (ApiError, TransportError, Exception) as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning(f"Elasticsearch health check failed: {exc}")
            return False, f"Connection failure: {type(exc).__name__}", round(duration_ms, 2)

    # --------------------------------------------------------------------------
    # Index Names & Aliases
    # --------------------------------------------------------------------------

    @property
    def products_index_name(self) -> str:
        """Versioned physical index name for cosmetic products."""
        return f"{self.settings.ELASTICSEARCH_INDEX_PREFIX}products_v1"

    @property
    def products_alias(self) -> str:
        """Stable read/write alias for products."""
        return f"{self.settings.ELASTICSEARCH_INDEX_PREFIX}products_current"

    @property
    def ingredients_index_name(self) -> str:
        """Versioned physical index name for cosmetic ingredients."""
        return f"{self.settings.ELASTICSEARCH_INDEX_PREFIX}ingredients_v1"

    @property
    def ingredients_alias(self) -> str:
        """Stable read/write alias for ingredients."""
        return f"{self.settings.ELASTICSEARCH_INDEX_PREFIX}ingredients_current"

    # --------------------------------------------------------------------------
    # Mappings & Analysis Schemas
    # --------------------------------------------------------------------------

    def get_analysis_settings(self) -> dict[str, Any]:
        """Custom analyzers for skincare terminology and edge-ngram autocomplete."""
        return {
            "analysis": {
                "filter": {
                    "skincare_ngram_filter": {
                        "type": "edge_ngram",
                        "min_gram": 2,
                        "max_gram": 15,
                    }
                },
                "analyzer": {
                    "skincare_text_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    },
                    "skincare_autocomplete_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "asciifolding",
                            "skincare_ngram_filter",
                        ],
                    },
                    "skincare_autocomplete_search": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    },
                },
            }
        }

    def get_products_mapping(self) -> dict[str, Any]:
        """Schema mapping for the products index."""
        return {
            "properties": {
                "id": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 256},
                        "autocomplete": {
                            "type": "text",
                            "analyzer": "skincare_autocomplete_analyzer",
                            "search_analyzer": "skincare_autocomplete_search",
                        },
                    },
                },
                "brand": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 150},
                        "autocomplete": {
                            "type": "text",
                            "analyzer": "skincare_autocomplete_analyzer",
                            "search_analyzer": "skincare_autocomplete_search",
                        },
                    },
                },
                "category": {"type": "keyword"},
                "description": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                },
                "full_ingredient_list": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                },
                "ingredient_names": {"type": "keyword"},
                "ingredient_ids": {"type": "keyword"},
                "ean_or_upc": {"type": "keyword"},
                "image_url": {"type": "keyword", "index": False},
                "updated_at": {"type": "date"},
            }
        }

    def get_ingredients_mapping(self) -> dict[str, Any]:
        """Schema mapping for the ingredients index."""
        return {
            "properties": {
                "id": {"type": "keyword"},
                "inci_name": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 200},
                        "autocomplete": {
                            "type": "text",
                            "analyzer": "skincare_autocomplete_analyzer",
                            "search_analyzer": "skincare_autocomplete_search",
                        },
                    },
                },
                "common_name": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 200},
                        "autocomplete": {
                            "type": "text",
                            "analyzer": "skincare_autocomplete_analyzer",
                            "search_analyzer": "skincare_autocomplete_search",
                        },
                    },
                },
                "aliases": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "function": {"type": "keyword"},
                "safety_rating": {"type": "keyword"},
                "description": {
                    "type": "text",
                    "analyzer": "skincare_text_analyzer",
                },
                "updated_at": {"type": "date"},
            }
        }

    # --------------------------------------------------------------------------
    # Lifecycle: Creation, Alias Management & Deletion
    # --------------------------------------------------------------------------

    def ensure_indices_and_aliases(self) -> dict[str, str]:
        """Idempotently create versioned indices and bind stable aliases."""
        results: dict[str, str] = {}

        # 1. Products index
        if not self.client.indices.exists(index=self.products_index_name):
            body = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                    **self.get_analysis_settings(),
                },
                "mappings": self.get_products_mapping(),
            }
            self.client.indices.create(index=self.products_index_name, body=body)
            self.client.indices.put_alias(index=self.products_index_name, name=self.products_alias)
            results["products"] = (
                f"Created {self.products_index_name} with alias {self.products_alias}"
            )
        else:
            if not self.client.indices.exists_alias(name=self.products_alias):
                self.client.indices.put_alias(
                    index=self.products_index_name, name=self.products_alias
                )
            results["products"] = f"Index {self.products_index_name} already exists."

        # 2. Ingredients index
        if not self.client.indices.exists(index=self.ingredients_index_name):
            body = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                    **self.get_analysis_settings(),
                },
                "mappings": self.get_ingredients_mapping(),
            }
            self.client.indices.create(index=self.ingredients_index_name, body=body)
            self.client.indices.put_alias(
                index=self.ingredients_index_name, name=self.ingredients_alias
            )
            results["ingredients"] = (
                f"Created {self.ingredients_index_name} with alias {self.ingredients_alias}"
            )
        else:
            if not self.client.indices.exists_alias(name=self.ingredients_alias):
                self.client.indices.put_alias(
                    index=self.ingredients_index_name, name=self.ingredients_alias
                )
            results["ingredients"] = f"Index {self.ingredients_index_name} already exists."

        return results

    def delete_indices(self) -> None:
        """Delete all ToneTrace indices and aliases (used for clean teardown/tests)."""
        for index_name in [self.products_index_name, self.ingredients_index_name]:
            if self.client.indices.exists(index=index_name):
                self.client.indices.delete(index=index_name)
                logger.info(f"Deleted index {index_name}")

    # --------------------------------------------------------------------------
    # Document Operations & Bounded Bulk Indexing
    # --------------------------------------------------------------------------

    def index_document(self, index_or_alias: str, doc_id: str, document: dict[str, Any]) -> None:
        """Idempotently index or update a single document by stable ID."""
        self.client.index(
            index=index_or_alias,
            id=doc_id,
            document=document,
            refresh=False,
        )

    def delete_document(self, index_or_alias: str, doc_id: str) -> bool:
        """Delete a document by ID. Idempotent: returns True if deleted, False if not found."""
        try:
            resp = self.client.delete(index=index_or_alias, id=doc_id, refresh=False)
            return resp.get("result") in ("deleted", "not_found")
        except ApiError as exc:
            if exc.status_code == 404:
                return False
            raise

    def bulk_index_documents(
        self,
        index_or_alias: str,
        documents: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Bulk index documents in bounded batches with partial-failure tracking.

        Each item in `documents` must contain an 'id' key.

        Returns:
            (success_count, list_of_errors)
        """
        if not documents:
            return 0, []

        total_success = 0
        all_errors: list[dict[str, Any]] = []

        # Process in bounded chunks
        for i in range(0, len(documents), batch_size):
            chunk = documents[i : i + batch_size]
            actions = [
                {
                    "_op_type": "index",
                    "_index": index_or_alias,
                    "_id": str(doc["id"]),
                    "_source": doc,
                }
                for doc in chunk
            ]

            success, errors = bulk(
                self.client,
                actions,
                stats_only=False,
                raise_on_error=False,
                raise_on_exception=False,
            )
            total_success += success
            if errors:
                all_errors.extend(errors)

        return total_success, all_errors

    def bulk_delete_documents(
        self,
        index_or_alias: str,
        doc_ids: list[str],
        batch_size: int = 100,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Bulk delete documents in bounded batches."""
        if not doc_ids:
            return 0, []

        total_success = 0
        all_errors: list[dict[str, Any]] = []

        for i in range(0, len(doc_ids), batch_size):
            chunk = doc_ids[i : i + batch_size]
            actions = [
                {
                    "_op_type": "delete",
                    "_index": index_or_alias,
                    "_id": str(_id),
                }
                for _id in chunk
            ]

            success, errors = bulk(
                self.client,
                actions,
                stats_only=False,
                raise_on_error=False,
                raise_on_exception=False,
            )
            total_success += success
            if errors:
                all_errors.extend(errors)

        return total_success, all_errors

    def execute_search(self, index_or_alias: str, query_body: dict[str, Any]) -> dict[str, Any]:
        """Execute a search query against the specified alias."""
        return dict(self.client.search(index=index_or_alias, body=query_body))

    def refresh_index(self, index_or_alias: str) -> None:
        """Explicitly refresh index to make changes immediately visible (for tests/reindex)."""
        self.client.indices.refresh(index=index_or_alias)


# Singleton provider accessor
_search_provider_instance: SearchProvider | None = None


def get_search_provider() -> SearchProvider:
    """Retrieve the shared SearchProvider instance."""
    global _search_provider_instance
    if _search_provider_instance is None:
        _search_provider_instance = SearchProvider()
    return _search_provider_instance
