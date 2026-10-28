"""Pydantic exchange schemas for Phase 5 OCR and product label scanning."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MediaAssetResponse(BaseModel):
    """Uploaded image asset metadata (never includes raw image bytes)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    storage_provider: str
    original_filename: str | None = None
    content_type: str
    file_size_bytes: int
    image_width: int | None = None
    image_height: int | None = None
    sha256_hash: str
    retention_policy: str = "ocr_retain_30d"
    retention_expires_at: datetime | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None
    view_url: str | None = None
    created_at: datetime


class MediaAssetDeleteResponse(BaseModel):
    """Confirmation of private image asset deletion from PostgreSQL BYTEA / storage."""

    asset_id: UUID
    status: str = "deleted"
    deleted_at: datetime
    message: str


class OCRCandidateIngredientResponse(BaseModel):
    """Normalized candidate ingredient extracted from raw OCR."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    raw_text: str
    normalized_name: str
    matched_ingredient_id: UUID | None = None
    confidence: float | None = None
    is_user_corrected: bool = False
    is_confirmed: bool = False


class OCRScanResponse(BaseModel):
    """Full OCR scanning job details, raw text, and candidate list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    provider: str
    raw_text: str | None = None
    confidence_score: float | None = None
    processing_time_ms: int | None = None
    error_category: str | None = None
    error_message: str | None = None
    media_asset: MediaAssetResponse
    candidates: list[OCRCandidateIngredientResponse] = Field(default_factory=list)
    candidate_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConfirmIngredientItem(BaseModel):
    """User review item for confirming or editing candidate ingredients."""

    candidate_id: UUID | None = None
    position: int
    name: str = Field(..., min_length=1, max_length=255)
    is_confirmed: bool = True


class ConfirmScanRequest(BaseModel):
    """Request payload to review and confirm extracted formulation candidates."""

    ingredients: list[ConfirmIngredientItem] = Field(
        ..., min_length=1, description="Reviewed and corrected list of ingredients"
    )


class ConfirmScanResponse(BaseModel):
    """Result of scan confirmation workflow."""

    scan_id: UUID
    status: str
    confirmed_count: int
    candidates: list[OCRCandidateIngredientResponse]
    message: str
