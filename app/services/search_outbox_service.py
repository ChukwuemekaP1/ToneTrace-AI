"""Transactional Outbox service ensuring sync between PostgreSQL and Elasticsearch."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SearchOutbox
from app.providers.search_provider import SearchProvider, get_search_provider
from app.services.base import BaseService

logger = logging.getLogger("tonetrace.search_outbox")


class SearchOutboxService(BaseService):
    """Manages transactional outbox events and dispatches bounded batches to Elasticsearch."""

    def __init__(
        self,
        db: AsyncSession,
        search_provider: SearchProvider | None = None,
    ) -> None:
        super().__init__(db=db)
        self.search_provider = search_provider or get_search_provider()

    @staticmethod
    def enqueue_sync_event(
        db: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> SearchOutbox:
        """Enqueue an outbox event within the active PostgreSQL transaction.

        Guarantees that the event is only committed if the database transaction succeeds.
        """
        event = SearchOutbox(
            entity_type=entity_type.lower(),
            entity_id=entity_id,
            action=action.lower(),
            payload=payload or {},
            status="pending",
            retry_count=0,
            max_retries=5,
        )
        db.add(event)
        return event

    async def process_outbox_batch(self, batch_size: int = 50) -> dict[str, int]:
        """Read pending outbox events, execute bounded bulk operations, and update event status.

        Provides document-level partial failure tracking and exponential backoff retry counts.
        """
        # Fetch pending or retryable events ordered by creation time
        stmt = (
            select(SearchOutbox)
            .where(
                SearchOutbox.status.in_(["pending", "failed"]),
                SearchOutbox.retry_count < SearchOutbox.max_retries,
            )
            .order_by(SearchOutbox.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        events = list((await self.db.execute(stmt)).scalars().all())

        if not events:
            return {"processed": 0, "succeeded": 0, "failed": 0}

        # Mark events as processing
        for event in events:
            event.status = "processing"
        await self.db.flush()

        succeeded_ids: set[uuid.UUID] = set()
        failed_errors: dict[uuid.UUID, str] = {}

        # Separate by entity type and action
        product_indices: list[dict[str, Any]] = []
        product_deletes: list[str] = []
        ingredient_indices: list[dict[str, Any]] = []
        ingredient_deletes: list[str] = []

        event_map: dict[str, SearchOutbox] = {str(e.entity_id): e for e in events}

        for event in events:
            str_id = str(event.entity_id)
            if event.entity_type == "product":
                if event.action == "index":
                    payload = dict(event.payload)
                    payload["id"] = str_id
                    product_indices.append(payload)
                else:
                    product_deletes.append(str_id)
            elif event.entity_type == "ingredient":
                if event.action == "index":
                    payload = dict(event.payload)
                    payload["id"] = str_id
                    ingredient_indices.append(payload)
                else:
                    ingredient_deletes.append(str_id)

        try:
            # 1. Product index batch
            if product_indices:
                _, errs = self.search_provider.bulk_index_documents(
                    self.search_provider.products_alias,
                    product_indices,
                )
                self._record_bulk_results(
                    product_indices, errs, event_map, succeeded_ids, failed_errors
                )

            # 2. Product delete batch
            if product_deletes:
                _, errs = self.search_provider.bulk_delete_documents(
                    self.search_provider.products_alias,
                    product_deletes,
                )
                self._record_delete_results(
                    product_deletes, errs, event_map, succeeded_ids, failed_errors
                )

            # 3. Ingredient index batch
            if ingredient_indices:
                _, errs = self.search_provider.bulk_index_documents(
                    self.search_provider.ingredients_alias,
                    ingredient_indices,
                )
                self._record_bulk_results(
                    ingredient_indices, errs, event_map, succeeded_ids, failed_errors
                )

            # 4. Ingredient delete batch
            if ingredient_deletes:
                _, errs = self.search_provider.bulk_delete_documents(
                    self.search_provider.ingredients_alias,
                    ingredient_deletes,
                )
                self._record_delete_results(
                    ingredient_deletes, errs, event_map, succeeded_ids, failed_errors
                )

        except Exception as exc:
            logger.exception(f"Unhandled error during Elasticsearch bulk outbox sync: {exc}")
            # Mark all uncompleted events as failed for retry
            for event in events:
                if event.id not in succeeded_ids:
                    event.retry_count += 1
                    event.status = "failed" if event.retry_count >= event.max_retries else "pending"
                    event.error_message = f"Batch transport error: {type(exc).__name__}"
            await self.db.commit()
            return {"processed": len(events), "succeeded": 0, "failed": len(events)}

        # Update event statuses in PostgreSQL
        now = datetime.now(UTC)
        for event in events:
            if event.id in succeeded_ids:
                event.status = "completed"
                event.processed_at = now
                event.error_message = None
            else:
                event.retry_count += 1
                event.error_message = failed_errors.get(
                    event.id, "Bulk operation reported failure."
                )
                event.status = "failed" if event.retry_count >= event.max_retries else "pending"

        await self.db.commit()
        return {
            "processed": len(events),
            "succeeded": len(succeeded_ids),
            "failed": len(events) - len(succeeded_ids),
        }

    def _record_bulk_results(
        self,
        docs: list[dict[str, Any]],
        errors: list[dict[str, Any]],
        event_map: dict[str, SearchOutbox],
        succeeded_ids: set[uuid.UUID],
        failed_errors: dict[uuid.UUID, str],
    ) -> None:
        """Extract individual success/failure IDs from Elasticsearch bulk response."""
        error_doc_ids: dict[str, str] = {}
        for err in errors:
            action = next(iter(err.values()))
            doc_id = action.get("_id")
            error_reason = str(action.get("error", "Unknown error"))
            if doc_id:
                error_doc_ids[doc_id] = error_reason

        for doc in docs:
            doc_id = str(doc["id"])
            event = event_map.get(doc_id)
            if not event:
                continue

            if doc_id in error_doc_ids:
                failed_errors[event.id] = error_doc_ids[doc_id]
            else:
                succeeded_ids.add(event.id)

    def _record_delete_results(
        self,
        doc_ids: list[str],
        errors: list[dict[str, Any]],
        event_map: dict[str, SearchOutbox],
        succeeded_ids: set[uuid.UUID],
        failed_errors: dict[uuid.UUID, str],
    ) -> None:
        """Extract delete success/failure IDs."""
        error_doc_ids: dict[str, str] = {}
        for err in errors:
            action = next(iter(err.values()))
            doc_id = action.get("_id")
            if doc_id:
                error_doc_ids[doc_id] = str(action.get("error", "Unknown delete error"))

        for doc_id in doc_ids:
            event = event_map.get(doc_id)
            if not event:
                continue

            if doc_id in error_doc_ids:
                failed_errors[event.id] = error_doc_ids[doc_id]
            else:
                succeeded_ids.add(event.id)
