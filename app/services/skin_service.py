"""Skin Analysis and Longitudinal Skin Story domain service (Phase 8).

Enforces:
- Mandatory explicit user consent ('skin_data_processing' or 'facial_scan_processing')
  before accepting or processing any facial scan image.
- Private object storage for all scan photos with short-lived HMAC signed URLs,
  retention expiration metadata, and user-initiated deletion workflows.
- Scan and AnalysisJob creation in PostgreSQL prior to external provider calls.
- Idempotency deduplication and retry recovery without duplicate scan records.
- Strict separation of normalized observations from restricted raw provider responses.
- Longitudinal Skin Story comparability checks (matching metric_code, unit,
  provider_name, provider_model_version, and interpretation_version) and
  non-diagnostic framing that never infers pigmentation causation or clinical improvement.
"""

import hashlib
import io
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.db.models import (
    AnalysisJob,
    MediaAsset,
    ScanMedia,
    SkinJournalEntry,
    SkinObservation,
    SkinScan,
    User,
    UserConsent,
)
from app.providers.skin_analysis import (
    NORMALIZED_METRICS,
    BaseSkinAnalysisProvider,
    SkinAnalysisError,
    SkinAnalysisTaskResult,
    get_skin_analysis_provider,
)
from app.providers.storage import BaseStorageProvider, get_storage_provider
from app.schemas.skin import (
    SKIN_NON_DIAGNOSTIC_DISCLAIMER,
    SKIN_VARIABILITY_DISCLOSURE,
    CaptureConditionsInput,
    CreateSkinJournalEntryRequest,
    ScanMediaResponse,
    SkinJournalEntryResponse,
    SkinJournalListResponse,
    SkinMetricTimeline,
    SkinObservationResponse,
    SkinScanDeleteResponse,
    SkinScanListResponse,
    SkinScanResponse,
    SkinStoryPoint,
    SkinStoryResponse,
)

logger = logging.getLogger(__name__)

ACCEPTED_SKIN_CONSENT_PURPOSES = ("skin_data_processing", "facial_scan_processing")
STABLE_DELTA_THRESHOLD = 1.0


class SkinService:
    """Domain service orchestrating facial skin scans, observations, deletion, and Skin Story."""

    def __init__(
        self,
        db: AsyncSession,
        storage_provider: BaseStorageProvider | None = None,
        skin_provider: BaseSkinAnalysisProvider | None = None,
    ) -> None:
        self._db = db
        self._storage = storage_provider or get_storage_provider()
        self._provider = skin_provider or get_skin_analysis_provider()

    async def verify_skin_scan_consent(self, user_id: UUID) -> UserConsent:
        """Confirm that the user has an active, unrevoked consent for skin scan processing."""
        stmt = (
            select(UserConsent)
            .where(
                UserConsent.user_id == user_id,
                UserConsent.purpose.in_(ACCEPTED_SKIN_CONSENT_PURPOSES),
                UserConsent.is_granted.is_(True),
                UserConsent.revoked_at.is_(None),
            )
            .order_by(UserConsent.updated_at.desc())
        )
        res = await self._db.execute(stmt)
        consent = res.scalars().first()
        if consent is None:
            raise PermissionDeniedError(
                "Explicit user consent for 'skin_data_processing' is required before "
                "uploading or analyzing a facial skin scan."
            )
        return consent

    async def _validate_and_store_photo(
        self,
        user: User,
        file_bytes: bytes,
        original_filename: str | None,
    ) -> MediaAsset:
        """Validate image bytes, format, and dimensions, then store in private object storage."""
        settings = get_settings()
        if not file_bytes:
            raise ValidationError("Uploaded scan image file is empty.")

        max_bytes = settings.UPLOAD_MAX_FILE_SIZE_BYTES
        if len(file_bytes) > max_bytes:
            raise ValidationError(
                f"Scan image exceeds maximum allowed size ({max_bytes // (1024 * 1024)} MB)."
            )

        try:
            img_check = Image.open(io.BytesIO(file_bytes))
            img_check.verify()
            image_format = img_check.format.lower() if img_check.format else ""
        except Exception as exc:
            raise ValidationError(f"Invalid or corrupted image file: {exc}") from exc

        try:
            img_dim = Image.open(io.BytesIO(file_bytes))
            width, height = img_dim.size
        except Exception as exc:
            raise ValidationError(f"Unable to read image dimensions: {exc}") from exc

        format_mime_map = {
            "jpeg": "image/jpeg",
            "jpg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        verified_mime = format_mime_map.get(image_format)
        allowed_types = settings.UPLOAD_ALLOWED_MIME_TYPES
        if not verified_mime or verified_mime not in allowed_types:
            raise ValidationError(
                f"Unsupported image format '{image_format}'. Allowed formats: {allowed_types}"
            )

        max_dim = settings.UPLOAD_MAX_IMAGE_DIMENSION
        if width > max_dim or height > max_dim:
            raise ValidationError(
                f"Image dimensions ({width}x{height}) exceed maximum limit ({max_dim}px)."
            )
        if width < 32 or height < 32:
            raise ValidationError(
                f"Image dimensions ({width}x{height}) are too small for facial skin analysis."
            )

        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        ext = (
            "jpg"
            if verified_mime == "image/jpeg"
            else ("png" if verified_mime == "image/png" else "webp")
        )
        storage_key = f"skin_scans/{user.id}/{uuid.uuid4().hex}.{ext}"

        await self._storage.store_object(storage_key, file_bytes, verified_mime)

        now = datetime.now(UTC)
        retention_days = max(1, settings.SKIN_ANALYSIS_RETENTION_DAYS)

        asset = MediaAsset(
            user_id=user.id,
            storage_provider=self._storage.name,
            storage_key=storage_key,
            original_filename=original_filename[:250] if original_filename else "scan.jpg",
            content_type=verified_mime,
            file_size_bytes=len(file_bytes),
            image_width=width,
            image_height=height,
            sha256_hash=sha256_hash,
            image_bytes=file_bytes if self._storage.name == "postgres" else None,
            retention_policy=f"user_controlled_{retention_days}d",
            retention_expires_at=now + timedelta(days=retention_days),
            is_deleted=False,
        )
        self._db.add(asset)
        await self._db.flush()
        return asset

    async def _apply_provider_result(
        self,
        scan: SkinScan,
        job: AnalysisJob | None,
        result: SkinAnalysisTaskResult,
    ) -> None:
        """Record provider status and normalized observations on SkinScan and AnalysisJob."""
        now = datetime.now(UTC)
        scan.provider_task_id = result.provider_task_id or scan.provider_task_id
        scan.provider_model_version = result.provider_model_version
        scan.raw_payload_retained = False

        if job is not None:
            job.provider_task_id = scan.provider_task_id

        if result.status == "processing":
            scan.status = "processing"
            scan.error_category = None
            scan.error_message = None
            if job is not None:
                job.status = "processing"
                job.error_category = None
                job.error_message = None
            return

        if result.status == "failed":
            scan.status = "failed"
            scan.error_category = result.error_category or "upstream_error"
            scan.error_message = result.error_message or "Skin analysis provider task failed."
            scan.completed_at = now
            if job is not None:
                job.status = "failed"
                job.error_category = scan.error_category
                job.error_message = scan.error_message
                job.completed_at = now
            return

        # Status == 'succeeded'
        scan.status = "succeeded"
        scan.overall_score = result.overall_score
        scan.skin_type_observation = result.skin_type_observation
        scan.error_category = None
        scan.error_message = None
        scan.completed_at = now
        if job is not None:
            job.status = "succeeded"
            job.error_category = None
            job.error_message = None
            job.completed_at = now

        # Clear any stale observations if this was a retry/poll
        await self._db.execute(
            delete(SkinObservation).where(SkinObservation.skin_scan_id == scan.id)
        )

        for obs in result.observations:
            db_obs = SkinObservation(
                skin_scan_id=scan.id,
                user_id=scan.user_id,
                metric_code=obs.metric_code,
                metric_label=obs.metric_label,
                raw_value=obs.raw_value,
                display_value=obs.display_value,
                unit=obs.unit,
                directionality=obs.directionality,
                provider_name=result.provider_name,
                provider_model_version=result.provider_model_version,
                interpretation_version=result.interpretation_version,
                facial_zone=obs.facial_zone,
                confidence=obs.confidence,
                caveat_note=obs.caveat_note,
                observed_at=now,
            )
            self._db.add(db_obs)

    async def create_and_process_scan(
        self,
        user: User,
        file_bytes: bytes,
        original_filename: str | None = None,
        idempotency_key: str | None = None,
        capture_conditions: CaptureConditionsInput | None = None,
        requested_metrics: list[str] | None = None,
    ) -> SkinScanResponse:
        """Execute the full Phase 8 skin scan submission workflow:

        1. Confirm applicable consent.
        2. Check idempotency / retry recovery.
        3. Validate image and store privately.
        4. Create SkinScan, AnalysisJob, and ScanMedia before external call.
        5. Submit image to configured provider adapter.
        6. Persist status and normalized observations without retaining restricted raw payloads.
        """
        # 1. Confirm explicit user consent
        consent = await self.verify_skin_scan_consent(user.id)

        if requested_metrics:
            invalid = [m for m in requested_metrics if m not in NORMALIZED_METRICS]
            if invalid:
                raise ValidationError(
                    f"Unsupported requested_metrics {invalid}. "
                    f"Supported: {sorted(NORMALIZED_METRICS.keys())}"
                )

        clean_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None

        # 2. Idempotency check & retry recovery without duplicate scan records
        existing_scan: SkinScan | None = None
        if clean_key:
            stmt = (
                select(SkinScan)
                .where(
                    SkinScan.user_id == user.id,
                    SkinScan.idempotency_key == clean_key,
                )
                .options(
                    selectinload(SkinScan.media_items),
                    selectinload(SkinScan.observations),
                    selectinload(SkinScan.analysis_job),
                )
            )
            res = await self._db.execute(stmt)
            existing_scan = res.scalar_one_or_none()
            if existing_scan is not None:
                if existing_scan.status == "deleted":
                    raise ValidationError(
                        "Cannot reuse idempotency_key of a previously deleted scan."
                    )
                if existing_scan.status in ("succeeded", "processing"):
                    return self._map_scan_to_response(existing_scan)

        settings = get_settings()
        retention_days = max(1, settings.SKIN_ANALYSIS_RETENTION_DAYS)
        now = datetime.now(UTC)

        if existing_scan is not None and existing_scan.status == "failed":
            # Recover failed scan in-place without creating duplicate scan records
            scan = existing_scan
            job = existing_scan.analysis_job
            if job is not None:
                if job.attempt_count >= job.max_attempts:
                    raise ValidationError(
                        f"Scan '{scan.id}' has reached maximum retry attempts ({job.max_attempts})."
                    )
                job.attempt_count += 1
                job.status = "processing"
            scan.status = "processing"
            scan.provider = self._provider.name
            scan.provider_model_version = self._provider.provider_model_version
            scan.consent_id = consent.id
            await self._db.flush()
            content_type = scan.media_items[0].content_type if scan.media_items else "image/jpeg"
        else:
            # 3. Validate image and persist to private object storage
            media_asset = await self._validate_and_store_photo(
                user=user,
                file_bytes=file_bytes,
                original_filename=original_filename,
            )
            content_type = media_asset.content_type

            # 4. Create AnalysisJob, SkinScan, and ScanMedia before external processing
            job = AnalysisJob(
                user_id=user.id,
                job_type="skin_analysis",
                provider=self._provider.name,
                status="pending",
                idempotency_key=clean_key,
                attempt_count=1,
                max_attempts=3,
                submitted_at=now,
            )
            self._db.add(job)
            await self._db.flush()

            conditions_dict: dict[str, Any] = (
                capture_conditions.model_dump()
                if capture_conditions is not None
                else CaptureConditionsInput().model_dump()
            )

            scan = SkinScan(
                user_id=user.id,
                consent_id=consent.id,
                analysis_job_id=job.id,
                provider=self._provider.name,
                provider_model_version=self._provider.provider_model_version,
                status="pending",
                idempotency_key=clean_key,
                capture_conditions=conditions_dict,
                raw_payload_retained=False,
            )
            self._db.add(scan)
            await self._db.flush()

            scan_media = ScanMedia(
                skin_scan_id=scan.id,
                media_asset_id=media_asset.id,
                user_id=user.id,
                media_role="source_photo",
                storage_provider=media_asset.storage_provider,
                storage_key=media_asset.storage_key,
                content_type=media_asset.content_type,
                file_size_bytes=media_asset.file_size_bytes,
                retention_policy=f"user_controlled_{retention_days}d",
                retention_expires_at=now + timedelta(days=retention_days),
                is_deleted=False,
            )
            self._db.add(scan_media)
            await self._db.flush()

        # 5. Submit image to provider adapter (never fabricate success on error)
        try:
            provider_result = await self._provider.submit_scan(
                file_bytes=file_bytes,
                filename=original_filename or "scan.jpg",
                content_type=content_type,
                requested_metrics=requested_metrics,
            )
            await self._apply_provider_result(scan, job, provider_result)
        except SkinAnalysisError as exc:
            logger.warning(
                "Skin analysis provider error [category=%s]: %s",
                exc.category,
                exc.message,
            )
            failed_result = SkinAnalysisTaskResult(
                provider_name=self._provider.name,
                provider_task_id=scan.provider_task_id,
                provider_model_version=self._provider.provider_model_version,
                interpretation_version=self._provider.interpretation_version,
                status="failed",
                error_category=exc.category,
                error_message=exc.message,
            )
            await self._apply_provider_result(scan, job, failed_result)

        await self._db.commit()
        return await self.get_scan(scan.id, user.id)

    async def poll_scan(self, scan_id: UUID, user_id: UUID) -> SkinScanResponse:
        """Poll an asynchronous skin scan that is currently in 'processing' status."""
        stmt = (
            select(SkinScan)
            .where(
                SkinScan.id == scan_id,
                SkinScan.user_id == user_id,
                SkinScan.status != "deleted",
            )
            .options(
                selectinload(SkinScan.media_items),
                selectinload(SkinScan.observations),
                selectinload(SkinScan.analysis_job),
            )
        )
        res = await self._db.execute(stmt)
        scan = res.scalar_one_or_none()
        if scan is None:
            raise NotFoundError(f"Skin scan '{scan_id}' not found.")

        if scan.status != "processing" or not scan.provider_task_id:
            return self._map_scan_to_response(scan)

        job = scan.analysis_job
        try:
            poll_result = await self._provider.poll_task(scan.provider_task_id)
            await self._apply_provider_result(scan, job, poll_result)
        except SkinAnalysisError as exc:
            logger.warning(
                "Skin scan polling error [scan_id=%s, category=%s]: %s",
                scan.id,
                exc.category,
                exc.message,
            )
            failed_result = SkinAnalysisTaskResult(
                provider_name=scan.provider,
                provider_task_id=scan.provider_task_id,
                provider_model_version=scan.provider_model_version
                or self._provider.provider_model_version,
                interpretation_version=self._provider.interpretation_version,
                status="failed",
                error_category=exc.category,
                error_message=exc.message,
            )
            await self._apply_provider_result(scan, job, failed_result)

        await self._db.commit()
        return await self.get_scan(scan.id, user_id)

    async def get_scan(self, scan_id: UUID, user_id: UUID) -> SkinScanResponse:
        """Retrieve a single skin scan with strict user ownership enforcement."""
        stmt = (
            select(SkinScan)
            .where(
                SkinScan.id == scan_id,
                SkinScan.user_id == user_id,
                SkinScan.status != "deleted",
            )
            .options(
                selectinload(SkinScan.media_items),
                selectinload(SkinScan.observations),
            )
            .execution_options(populate_existing=True)
        )
        res = await self._db.execute(stmt)
        scan = res.scalar_one_or_none()
        if scan is None:
            raise NotFoundError(f"Skin scan '{scan_id}' not found.")

        return self._map_scan_to_response(scan)

    async def list_scans(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        status_filter: str | None = None,
    ) -> SkinScanListResponse:
        """List a user's skin scans (excluding deleted scans) in reverse chronological order."""
        base_filter = [
            SkinScan.user_id == user_id,
            SkinScan.status != "deleted",
        ]
        if status_filter:
            base_filter.append(SkinScan.status == status_filter)

        count_stmt = select(func.count(SkinScan.id)).where(*base_filter)
        total = int((await self._db.execute(count_stmt)).scalar_one() or 0)

        stmt = (
            select(SkinScan)
            .where(*base_filter)
            .options(
                selectinload(SkinScan.media_items),
                selectinload(SkinScan.observations),
            )
            .order_by(SkinScan.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self._db.execute(stmt)
        scans = list(res.scalars().all())

        return SkinScanListResponse(
            items=[self._map_scan_to_response(s) for s in scans],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def delete_scan(self, scan_id: UUID, user_id: UUID) -> SkinScanDeleteResponse:
        """Purge private scan media from PostgreSQL BYTEA / storage and delete scan observations."""
        stmt = (
            select(SkinScan)
            .where(
                SkinScan.id == scan_id,
                SkinScan.user_id == user_id,
                SkinScan.status != "deleted",
            )
            .options(
                selectinload(SkinScan.media_items).selectinload(ScanMedia.media_asset),
                selectinload(SkinScan.observations),
            )
        )
        res = await self._db.execute(stmt)
        scan = res.scalar_one_or_none()
        if scan is None:
            raise NotFoundError(f"Skin scan '{scan_id}' not found.")

        now = datetime.now(UTC)
        purged_count = 0
        for media in scan.media_items:
            if not media.is_deleted:
                await self._storage.delete_object(media.storage_key)
                media.is_deleted = True
                media.deleted_at = now
                if media.media_asset is not None:
                    media.media_asset.image_bytes = None
                    media.media_asset.is_deleted = True
                    media.media_asset.deleted_at = now
                purged_count += 1

        await self._db.execute(
            delete(SkinObservation).where(SkinObservation.skin_scan_id == scan.id)
        )
        scan.status = "deleted"
        scan.deleted_at = now

        await self._db.commit()
        return SkinScanDeleteResponse(
            scan_id=scan.id,
            status="deleted",
            purged_media_count=purged_count,
            deleted_at=now,
            message=("Skin scan observations and private object storage photos have been deleted."),
        )

    async def create_journal_entry(
        self,
        user: User,
        payload: CreateSkinJournalEntryRequest,
    ) -> SkinJournalEntryResponse:
        """Create a user-authored longitudinal skin story journal entry."""
        if payload.skin_scan_id is not None:
            scan_stmt = select(SkinScan.id).where(
                SkinScan.id == payload.skin_scan_id,
                SkinScan.user_id == user.id,
                SkinScan.status != "deleted",
            )
            linked_scan_id = (await self._db.execute(scan_stmt)).scalar_one_or_none()
            if linked_scan_id is None:
                raise NotFoundError(
                    f"Linked skin scan '{payload.skin_scan_id}' not found for current user."
                )

        recorded_at = payload.recorded_at or datetime.now(UTC)
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=UTC)

        entry = SkinJournalEntry(
            user_id=user.id,
            skin_scan_id=payload.skin_scan_id,
            recorded_at=recorded_at,
            perceived_skin_state=payload.perceived_skin_state.strip(),
            self_reported_observations=[
                s.strip() for s in payload.self_reported_observations if s.strip()
            ],
            routine_notes=payload.routine_notes,
            products_used=[p.strip() for p in payload.products_used if p.strip()],
            environmental_or_lifestyle_factors=payload.environmental_or_lifestyle_factors,
            notes=payload.notes,
        )
        self._db.add(entry)
        await self._db.commit()
        await self._db.refresh(entry)
        return SkinJournalEntryResponse.model_validate(entry)

    async def list_journal_entries(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> SkinJournalListResponse:
        """List a user's skin story journal entries in reverse chronological order."""
        count_stmt = select(func.count(SkinJournalEntry.id)).where(
            SkinJournalEntry.user_id == user_id
        )
        total = int((await self._db.execute(count_stmt)).scalar_one() or 0)

        stmt = (
            select(SkinJournalEntry)
            .where(SkinJournalEntry.user_id == user_id)
            .order_by(SkinJournalEntry.recorded_at.desc(), SkinJournalEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self._db.execute(stmt)
        entries = list(res.scalars().all())
        return SkinJournalListResponse(
            items=[SkinJournalEntryResponse.model_validate(e) for e in entries],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_skin_story(
        self,
        user_id: UUID,
        metric_filter: str | None = None,
        journal_limit: int = 10,
    ) -> SkinStoryResponse:
        """Build a longitudinal Skin Story for the authenticated user.

        Skin Story Rules:
        - Compare only compatible metrics, units, and provider/model versions, or
          explicitly disclose incompatibility.
        - Distinguish observed visual metric changes from clinical improvement.
        - Never infer the cause of pigmentation or diagnose a skin condition from a photo.
        - Explain that lighting, camera, angle, cosmetics, and other conditions may
          affect measurements.
        - Never fabricate missing historical observations.
        """
        scans_stmt = (
            select(SkinScan)
            .where(
                SkinScan.user_id == user_id,
                SkinScan.status == "succeeded",
            )
            .options(selectinload(SkinScan.observations))
            .order_by(SkinScan.created_at.asc())
        )
        scans_res = await self._db.execute(scans_stmt)
        succeeded_scans = list(scans_res.scalars().all())

        scan_conditions_map: dict[UUID, dict[str, Any]] = {
            s.id: (s.capture_conditions or {}) for s in succeeded_scans
        }

        grouped_obs: dict[str, list[SkinObservation]] = defaultdict(list)
        for scan in succeeded_scans:
            for obs in scan.observations:
                if metric_filter and obs.metric_code != metric_filter:
                    continue
                grouped_obs[obs.metric_code].append(obs)

        timelines: list[SkinMetricTimeline] = []
        for metric_code in sorted(grouped_obs.keys()):
            obs_list = sorted(grouped_obs[metric_code], key=lambda o: o.observed_at)
            if not obs_list:
                continue

            baseline = obs_list[0]
            points: list[SkinStoryPoint] = []
            comparable_points: list[SkinStoryPoint] = []
            warnings: list[str] = []

            for obs in obs_list:
                mismatches: list[str] = []
                if obs.unit != baseline.unit:
                    mismatches.append(f"unit '{obs.unit}' != baseline '{baseline.unit}'")
                if obs.provider_name != baseline.provider_name:
                    mismatches.append(
                        f"provider '{obs.provider_name}' != baseline '{baseline.provider_name}'"
                    )
                if obs.provider_model_version != baseline.provider_model_version:
                    mismatches.append(
                        f"model version '{obs.provider_model_version}' != "
                        f"baseline '{baseline.provider_model_version}'"
                    )
                if obs.interpretation_version != baseline.interpretation_version:
                    mismatches.append(
                        f"interpretation version '{obs.interpretation_version}' != "
                        f"baseline '{baseline.interpretation_version}'"
                    )

                is_comparable = len(mismatches) == 0
                incompatibility_reason = (
                    f"Not directly comparable to baseline ({'; '.join(mismatches)})."
                    if mismatches
                    else None
                )
                if incompatibility_reason and incompatibility_reason not in warnings:
                    warnings.append(incompatibility_reason)

                point = SkinStoryPoint(
                    observation_id=obs.id,
                    scan_id=obs.skin_scan_id,
                    observed_at=obs.observed_at,
                    raw_value=obs.raw_value,
                    display_value=obs.display_value,
                    unit=obs.unit,
                    directionality=obs.directionality,
                    provider_name=obs.provider_name,
                    provider_model_version=obs.provider_model_version,
                    interpretation_version=obs.interpretation_version,
                    capture_conditions=scan_conditions_map.get(obs.skin_scan_id, {}),
                    is_comparable_to_baseline=is_comparable,
                    incompatibility_reason=incompatibility_reason,
                )
                points.append(point)
                if is_comparable:
                    comparable_points.append(point)

            if len(comparable_points) >= 2:
                first_val = comparable_points[0].display_value
                latest_val = comparable_points[-1].display_value
                delta = round(latest_val - first_val, 2)
                if delta > STABLE_DELTA_THRESHOLD:
                    classification = "visual_metric_increase"
                elif delta < -STABLE_DELTA_THRESHOLD:
                    classification = "visual_metric_decrease"
                else:
                    classification = "visual_metric_stable"

                interpretation = (
                    f"Observed visual metric delta of {delta:+.1f} ({baseline.unit}) across "
                    f"{len(comparable_points)} compatible scans using "
                    f"{baseline.provider_name}/{baseline.provider_model_version}. "
                    "This reflects a change in camera-captured surface appearance only and "
                    "must not be interpreted as verified clinical improvement or medical change; "
                    "differences in ambient lighting, angle, or cosmetics may explain the shift."
                )
            else:
                delta = None
                classification = "insufficient_comparable_data"
                if warnings:
                    interpretation = (
                        "Direct numerical comparison is unavailable because historical scans "
                        "for this metric were captured across incompatible provider or model "
                        "versions. At least two compatible scans with matching provider, model "
                        "version, and unit are required to compute a longitudinal visual delta."
                    )
                else:
                    interpretation = (
                        "Only a single baseline observation is available for this metric. "
                        "At least two compatible scans over time are required to observe a "
                        "longitudinal visual metric delta."
                    )

            timelines.append(
                SkinMetricTimeline(
                    metric_code=metric_code,
                    metric_label=baseline.metric_label,
                    unit=baseline.unit,
                    directionality=baseline.directionality,
                    baseline_provider=baseline.provider_name,
                    baseline_model_version=baseline.provider_model_version,
                    baseline_interpretation_version=baseline.interpretation_version,
                    points=points,
                    comparable_point_count=len(comparable_points),
                    net_observed_delta=delta,
                    observation_classification=classification,  # type: ignore[arg-type]
                    non_clinical_interpretation=interpretation,
                    compatibility_warnings=warnings,
                )
            )

        journal_resp = await self.list_journal_entries(
            user_id=user_id,
            limit=journal_limit,
            offset=0,
        )

        return SkinStoryResponse(
            user_id=user_id,
            generated_at=datetime.now(UTC),
            total_succeeded_scans=len(succeeded_scans),
            metric_timelines=timelines,
            recent_journal_entries=journal_resp.items,
            capture_variability_notice=SKIN_VARIABILITY_DISCLOSURE,
            non_diagnostic_disclaimer=SKIN_NON_DIAGNOSTIC_DISCLAIMER,
        )

    def _map_scan_to_response(self, scan: SkinScan) -> SkinScanResponse:
        """Map a SkinScan SQLAlchemy instance to a SkinScanResponse."""
        media_responses: list[ScanMediaResponse] = []
        for m in scan.media_items:
            signed_url = (
                None
                if m.is_deleted
                else self._storage.generate_signed_url(m.storage_key, expires_in_seconds=600)
            )
            media_responses.append(
                ScanMediaResponse(
                    id=m.id,
                    skin_scan_id=m.skin_scan_id,
                    media_asset_id=m.media_asset_id,
                    media_role=m.media_role,
                    metric_code=m.metric_code,
                    storage_provider=m.storage_provider,
                    content_type=m.content_type,
                    file_size_bytes=m.file_size_bytes,
                    retention_policy=m.retention_policy,
                    retention_expires_at=m.retention_expires_at,
                    is_deleted=m.is_deleted,
                    deleted_at=m.deleted_at,
                    signed_view_url=signed_url,
                    created_at=m.created_at,
                )
            )

        obs_responses = [
            SkinObservationResponse(
                id=o.id,
                skin_scan_id=o.skin_scan_id,
                metric_code=o.metric_code,
                metric_label=o.metric_label,
                raw_value=o.raw_value,
                display_value=o.display_value,
                unit=o.unit,
                directionality=o.directionality,
                provider_name=o.provider_name,
                provider_model_version=o.provider_model_version,
                interpretation_version=o.interpretation_version,
                facial_zone=o.facial_zone,
                confidence=o.confidence,
                caveat_note=o.caveat_note,
                observed_at=o.observed_at,
            )
            for o in scan.observations
        ]

        return SkinScanResponse(
            id=scan.id,
            user_id=scan.user_id,
            consent_id=scan.consent_id,
            analysis_job_id=scan.analysis_job_id,
            provider=scan.provider,
            provider_task_id=scan.provider_task_id,
            provider_model_version=scan.provider_model_version,
            status=scan.status,
            idempotency_key=scan.idempotency_key,
            capture_conditions=scan.capture_conditions or {},
            overall_score=scan.overall_score,
            skin_type_observation=scan.skin_type_observation,
            error_category=scan.error_category,
            error_message=scan.error_message,
            raw_payload_retained=scan.raw_payload_retained,
            media_items=media_responses,
            observations=obs_responses,
            non_diagnostic_disclaimer=SKIN_NON_DIAGNOSTIC_DISCLAIMER,
            variability_disclosure=SKIN_VARIABILITY_DISCLOSURE,
            created_at=scan.created_at,
            completed_at=scan.completed_at,
            deleted_at=scan.deleted_at,
        )
