"""OCR and product label scanning domain service.

Enforces:
- Strict user-scoped isolation on all assets and scans.
- Private object storage with short-lived HMAC signed URLs.
- Untrusted text handling: Raw OCR text is strictly isolated and sanitized.
- Conservative candidate segmentation and catalog matching against canonical ingredients.
- Candidate review and confirmation workflows.
"""

import hashlib
import io
import logging
import re
import uuid
from uuid import UUID

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.db.models import (
    Ingredient,
    IngredientAlias,
    MediaAsset,
    OCRCandidateIngredient,
    OCRJob,
    User,
)
from app.providers.ocr import (
    BaseOCRAdapter,
    OCRError,
    OCRExtractionError,
    OCRRateLimitError,
    OCRUnavailableError,
    get_ocr_adapter,
)
from app.providers.storage import BaseStorageProvider, get_storage_provider
from app.schemas.ocr import (
    ConfirmIngredientItem,
    ConfirmScanResponse,
    MediaAssetResponse,
    OCRCandidateIngredientResponse,
    OCRScanResponse,
)

logger = logging.getLogger(__name__)


def sanitize_candidate_text(text: str) -> str:
    """Clean common cosmetic packaging filler, bullets, and percentages."""
    cleaned = re.sub(r"^\s*[\d\.\-\*\•\+]\s*", "", text)
    cleaned = re.sub(r"\s*\(\s*\d+(\.\d+)?%\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+\d+(\.\d+)?%", "", cleaned)
    return cleaned.strip(" ,;.:*-•")


class OCRService:
    """Domain service orchestrating image upload, OCR extraction, and formulation review."""

    def __init__(
        self,
        db: AsyncSession,
        storage_provider: BaseStorageProvider | None = None,
        ocr_adapter: BaseOCRAdapter | None = None,
    ) -> None:
        self._db = db
        self._storage = storage_provider or get_storage_provider()
        self._ocr = ocr_adapter or get_ocr_adapter()

    async def validate_and_store_image(
        self,
        user: User,
        file_bytes: bytes,
        original_filename: str | None,
        _declared_content_type: str | None = None,
    ) -> MediaAsset:
        """Validate image content, dimensions, and persist to private storage."""
        settings = get_settings()

        # 1. Size constraint
        if len(file_bytes) == 0:
            raise ValidationError("Uploaded file is empty.")
        max_bytes = settings.UPLOAD_MAX_FILE_SIZE_BYTES
        if len(file_bytes) > max_bytes:
            raise ValidationError(
                f"File size exceeds maximum permitted limit ({max_bytes // (1024 * 1024)} MB)."
            )

        # 2. Decode and inspect image via Pillow
        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.verify()
            image_format = image.format.lower() if image.format else ""
        except Exception as exc:
            raise ValidationError(f"Invalid or corrupted image file: {exc}") from exc

        # Re-open after verify() to read dimensions
        try:
            image = Image.open(io.BytesIO(file_bytes))
            width, height = image.size
        except Exception:
            width, height = None, None

        format_mime_map = {
            "jpeg": "image/jpeg",
            "jpg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        verified_mime = format_mime_map.get(image_format)
        allowed_types = settings.UPLOAD_ALLOWED_MIME_TYPES
        if not verified_mime or verified_mime not in allowed_types:
            raise ValidationError(f"Unsupported format '{image_format}'. Allowed: {allowed_types}")

        max_dim = settings.UPLOAD_MAX_IMAGE_DIMENSION
        if width and height and (width > max_dim or height > max_dim):
            raise ValidationError(
                f"Image dimensions ({width}x{height}) exceed maximum allowed ({max_dim}px)."
            )

        # 3. Compute SHA256
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()

        # 4. Generate random unguessable storage key
        ext = (
            "jpg"
            if verified_mime == "image/jpeg"
            else ("png" if verified_mime == "image/png" else "webp")
        )
        storage_key = f"media/{user.id}/{uuid.uuid4().hex}.{ext}"

        # 5. Persist bytes to private storage
        await self._storage.store_object(storage_key, file_bytes, verified_mime)

        asset = MediaAsset(
            user_id=user.id,
            storage_provider=self._storage.name,
            storage_key=storage_key,
            original_filename=original_filename[:250] if original_filename else None,
            content_type=verified_mime,
            file_size_bytes=len(file_bytes),
            image_width=width,
            image_height=height,
            sha256_hash=sha256_hash,
        )
        self._db.add(asset)
        await self._db.flush()
        return asset

    async def create_and_process_scan(
        self,
        user: User,
        media_asset: MediaAsset,
        image_bytes: bytes,
        idempotency_key: str | None = None,
    ) -> OCRScanResponse:
        """Run OCR extraction on stored media asset and segment candidate ingredients."""
        # Check idempotency
        if idempotency_key:
            stmt = (
                select(OCRJob)
                .where(
                    OCRJob.user_id == user.id,
                    OCRJob.idempotency_key == idempotency_key,
                )
                .options(
                    selectinload(OCRJob.media_asset),
                    selectinload(OCRJob.candidate_ingredients),
                )
            )
            res = await self._db.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing is not None:
                return self._map_to_scan_response(existing)

        job = OCRJob(
            user_id=user.id,
            media_asset_id=media_asset.id,
            status="processing",
            provider=self._ocr.name,
            idempotency_key=idempotency_key,
        )
        self._db.add(job)
        await self._db.flush()

        try:
            ocr_result = await self._ocr.extract_text(image_bytes, media_asset.content_type)
            job.status = "succeeded"
            job.raw_text = ocr_result.raw_text
            job.confidence_score = ocr_result.confidence_score
            job.processing_time_ms = ocr_result.processing_time_ms

            # Segment candidate ingredients
            await self._segment_and_link_candidates(job, ocr_result.raw_text)

        except OCRRateLimitError as rle:
            logger.warning("OCR scan rate limit hit: %s", rle)
            job.status = "failed"
            job.error_category = "rate_limited"
            job.error_message = str(rle)
        except OCRUnavailableError as oue:
            logger.error("OCR provider unavailable: %s", oue)
            job.status = "failed"
            job.error_category = "upstream_unavailable"
            job.error_message = str(oue)
        except OCRExtractionError as oee:
            logger.warning("OCR extraction failure: %s", oee)
            job.status = "failed"
            job.error_category = "unreadable_image"
            job.error_message = str(oee)
        except OCRError as oe:
            logger.error("OCR general failure: %s", oe)
            job.status = "failed"
            job.error_category = "ocr_error"
            job.error_message = str(oe)

        await self._db.commit()
        return await self.get_scan(job.id, user.id)

    async def get_scan(self, scan_id: UUID, user_id: UUID) -> OCRScanResponse:
        """Fetch OCR scan by ID with strict user ownership validation."""
        stmt = (
            select(OCRJob)
            .where(OCRJob.id == scan_id, OCRJob.user_id == user_id)
            .options(
                selectinload(OCRJob.media_asset),
                selectinload(OCRJob.candidate_ingredients),
            )
            .execution_options(populate_existing=True)
        )
        res = await self._db.execute(stmt)
        job = res.scalar_one_or_none()
        if job is None:
            raise NotFoundError(f"OCR Scan with ID '{scan_id}' was not found.")

        return self._map_to_scan_response(job)

    async def confirm_scan(
        self,
        scan_id: UUID,
        user_id: UUID,
        confirmed_items: list[ConfirmIngredientItem],
    ) -> ConfirmScanResponse:
        """Apply user-reviewed corrections and mark candidate formulation as confirmed."""
        stmt = (
            select(OCRJob)
            .where(OCRJob.id == scan_id, OCRJob.user_id == user_id)
            .options(selectinload(OCRJob.candidate_ingredients))
        )
        res = await self._db.execute(stmt)
        job = res.scalar_one_or_none()
        if job is None:
            raise NotFoundError(f"OCR Scan with ID '{scan_id}' was not found.")

        existing_candidates_map = {c.id: c for c in job.candidate_ingredients}

        confirmed_list: list[OCRCandidateIngredient] = []

        for item in confirmed_items:
            clean_name = item.name.strip()
            if not clean_name:
                continue

            if item.candidate_id and item.candidate_id in existing_candidates_map:
                cand = existing_candidates_map[item.candidate_id]
                if cand.normalized_name != clean_name:
                    cand.is_user_corrected = True
                    cand.normalized_name = clean_name
                cand.position = item.position
                cand.is_confirmed = item.is_confirmed
                confirmed_list.append(cand)
            else:
                # User manually added new ingredient
                new_cand = OCRCandidateIngredient(
                    ocr_job_id=job.id,
                    position=item.position,
                    raw_text=clean_name,
                    normalized_name=clean_name,
                    is_user_corrected=True,
                    is_confirmed=item.is_confirmed,
                )
                self._db.add(new_cand)
                confirmed_list.append(new_cand)

        await self._db.commit()

        # Reload updated scan
        updated = await self.get_scan(job.id, user_id)
        return ConfirmScanResponse(
            scan_id=job.id,
            status="confirmed",
            confirmed_count=len(confirmed_list),
            candidates=updated.candidates,
            message="Candidate ingredient list confirmed successfully.",
        )

    async def _segment_and_link_candidates(self, job: OCRJob, raw_text: str | None) -> None:
        """Parse raw untrusted OCR text into candidate ingredients and match to catalog."""
        if not raw_text:
            return

        # Strip initial packaging headers
        text = raw_text
        header_pattern = (
            r"(?i)\b(ingredients|ingrédients|active ingredients|"
            r"inactive ingredients|composition|contents)\b\s*[:\-\.]?"
        )
        text = re.sub(header_pattern, "", text)

        # Split on commas, semicolons, bullets, and line breaks
        segments = re.split(r"[,;\n\r•\*]+", text)

        position = 1
        for segment in segments:
            cleaned = sanitize_candidate_text(segment)
            if not cleaned or len(cleaned) < 2:
                continue

            # Strip non-alphanumeric noise
            if not any(c.isalpha() for c in cleaned):
                continue

            # Check if matches canonical catalog ingredient
            matched_id: UUID | None = None
            ing_stmt = select(Ingredient.id).where(
                (func.lower(Ingredient.inci_name) == cleaned.lower())
                | (func.lower(Ingredient.common_name) == cleaned.lower())
            )
            ing_res = await self._db.execute(ing_stmt)
            matched_id = ing_res.scalar_one_or_none()

            if matched_id is None:
                # Check alias table
                alias_stmt = select(IngredientAlias.ingredient_id).where(
                    func.lower(IngredientAlias.alias_name) == cleaned.lower()
                )
                alias_res = await self._db.execute(alias_stmt)
                matched_id = alias_res.scalar_one_or_none()

            cand = OCRCandidateIngredient(
                ocr_job_id=job.id,
                position=position,
                raw_text=segment.strip(),
                normalized_name=cleaned.title(),
                matched_ingredient_id=matched_id,
                confidence=0.85 if matched_id else 0.70,
                is_user_corrected=False,
                is_confirmed=False,
            )
            self._db.add(cand)
            position += 1

    def _map_to_scan_response(self, job: OCRJob) -> OCRScanResponse:
        """Map OCRJob model to Pydantic OCRScanResponse."""
        asset = job.media_asset
        view_url = (
            self._storage.generate_signed_url(asset.storage_key, expires_in_seconds=600)
            if asset
            else None
        )

        asset_resp = MediaAssetResponse(
            id=asset.id,
            storage_provider=asset.storage_provider,
            original_filename=asset.original_filename,
            content_type=asset.content_type,
            file_size_bytes=asset.file_size_bytes,
            image_width=asset.image_width,
            image_height=asset.image_height,
            sha256_hash=asset.sha256_hash,
            view_url=view_url,
            created_at=asset.created_at,
        )

        candidates = [
            OCRCandidateIngredientResponse(
                id=c.id,
                position=c.position,
                raw_text=c.raw_text,
                normalized_name=c.normalized_name,
                matched_ingredient_id=c.matched_ingredient_id,
                confidence=c.confidence,
                is_user_corrected=c.is_user_corrected,
                is_confirmed=c.is_confirmed,
            )
            for c in job.candidate_ingredients
        ]

        return OCRScanResponse(
            id=job.id,
            status=job.status,
            provider=job.provider,
            raw_text=job.raw_text,
            confidence_score=job.confidence_score,
            processing_time_ms=job.processing_time_ms,
            error_category=job.error_category,
            error_message=job.error_message,
            media_asset=asset_resp,
            candidates=candidates,
            candidate_count=len(candidates),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
