"""Pydantic v2 schemas for Skin Analysis and Longitudinal Skin Story (Phase 8)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SKIN_NON_DIAGNOSTIC_DISCLAIMER = (
    "Visual surface observations are derived from 2D photographs for cosmetic tracking only. "
    "They do not infer the underlying cause of pigmentation, do not diagnose any dermatological "
    "or medical condition, and do not substitute for an in-person clinical evaluation."
)

SKIN_VARIABILITY_DISCLOSURE = (
    "Lighting intensity and color temperature, camera lens and sensor preprocessing, viewing "
    "angle, facial expression, and cosmetics or skincare residue can significantly affect "
    "visual surface measurements across scans."
)


class CaptureConditionsInput(BaseModel):
    """Self-reported capture context recorded alongside a facial scan."""

    lighting_condition: Literal[
        "natural_daylight",
        "indoor_warm",
        "indoor_cool",
        "ring_light",
        "dim_or_uneven",
        "unknown",
    ] = Field(
        default="unknown",
        description="Ambient lighting environment during photo capture.",
    )
    camera_angle: Literal["frontal", "slight_angle", "unknown"] = Field(
        default="frontal",
        description="Camera orientation relative to face.",
    )
    cosmetics_worn: bool = Field(
        default=False,
        description="Whether makeup, tinted sunscreen, or visible residue was present.",
    )
    notes: str | None = Field(
        default=None,
        max_length=300,
        description="Optional user note on skin or room conditions.",
    )


class ScanMediaResponse(BaseModel):
    """Metadata and short-lived private view link for a scan media object."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skin_scan_id: UUID
    media_asset_id: UUID | None = None
    media_role: str
    metric_code: str | None = None
    storage_provider: str
    content_type: str
    file_size_bytes: int
    retention_policy: str
    retention_expires_at: datetime
    is_deleted: bool
    deleted_at: datetime | None = None
    signed_view_url: str | None = Field(
        default=None,
        description="Short-lived HMAC-signed private endpoint to view the image; None if deleted.",
    )
    created_at: datetime


class SkinObservationResponse(BaseModel):
    """Normalized single-metric visual observation from a skin scan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skin_scan_id: UUID
    metric_code: str
    metric_label: str
    raw_value: float
    display_value: float
    unit: str
    directionality: str
    provider_name: str
    provider_model_version: str
    interpretation_version: str
    facial_zone: str
    confidence: float | None = None
    caveat_note: str
    observed_at: datetime


class SkinScanResponse(BaseModel):
    """Full skin scan representation with provenance, status, and normalized observations."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    consent_id: UUID | None = None
    analysis_job_id: UUID | None = None
    provider: str
    provider_task_id: str | None = None
    provider_model_version: str | None = None
    status: str
    idempotency_key: str | None = None
    capture_conditions: dict[str, Any] = Field(default_factory=dict)
    overall_score: float | None = None
    skin_type_observation: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    raw_payload_retained: bool = False
    media_items: list[ScanMediaResponse] = Field(default_factory=list)
    observations: list[SkinObservationResponse] = Field(default_factory=list)
    non_diagnostic_disclaimer: str = SKIN_NON_DIAGNOSTIC_DISCLAIMER
    variability_disclosure: str = SKIN_VARIABILITY_DISCLOSURE
    created_at: datetime
    completed_at: datetime | None = None
    deleted_at: datetime | None = None


class SkinScanListResponse(BaseModel):
    """Paginated list of user skin scans."""

    items: list[SkinScanResponse]
    total: int
    limit: int
    offset: int


class SkinScanDeleteResponse(BaseModel):
    """Confirmation of scan and private media deletion."""

    scan_id: UUID
    status: str = "deleted"
    purged_media_count: int
    deleted_at: datetime
    message: str


class CreateSkinJournalEntryRequest(BaseModel):
    """Request payload for creating a user skin story journal entry."""

    skin_scan_id: UUID | None = Field(
        default=None,
        description="Optional UUID of a user-owned SkinScan to link with this entry.",
    )
    recorded_at: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp of observation (defaults to current UTC time).",
    )
    perceived_skin_state: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="User's overall perceived skin state (e.g. calm, balanced, dry, irritated).",
    )
    self_reported_observations: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="User-observed surface attributes (e.g. 'cheek redness', 'post-blemish mark').",
    )
    routine_notes: str | None = Field(
        default=None,
        max_length=1500,
        description="Notes on current skincare routine or recent changes.",
    )
    products_used: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Names or identifiers of products used.",
    )
    environmental_or_lifestyle_factors: dict[str, Any] = Field(
        default_factory=dict,
        description="Contextual factors such as lighting, climate, UV exposure, or sleep.",
    )
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Additional personal reflection.",
    )

    @field_validator("perceived_skin_state")
    @classmethod
    def normalize_state(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("perceived_skin_state cannot be blank.")
        return cleaned


class SkinJournalEntryResponse(BaseModel):
    """Response model for a user skin story journal entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    skin_scan_id: UUID | None = None
    recorded_at: datetime
    perceived_skin_state: str
    self_reported_observations: list[str]
    routine_notes: str | None = None
    products_used: list[str]
    environmental_or_lifestyle_factors: dict[str, Any]
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class SkinJournalListResponse(BaseModel):
    """Paginated list of user skin story journal entries."""

    items: list[SkinJournalEntryResponse]
    total: int
    limit: int
    offset: int


class SkinStoryPoint(BaseModel):
    """Single historical data point in a metric's longitudinal timeline."""

    observation_id: UUID
    scan_id: UUID
    observed_at: datetime
    raw_value: float
    display_value: float
    unit: str
    directionality: str
    provider_name: str
    provider_model_version: str
    interpretation_version: str
    capture_conditions: dict[str, Any] = Field(default_factory=dict)
    is_comparable_to_baseline: bool = Field(
        ...,
        description=(
            "True only if unit, provider_name, provider_model_version, and "
            "interpretation_version match the timeline baseline."
        ),
    )
    incompatibility_reason: str | None = Field(
        default=None,
        description="Explicit explanation if this point cannot be directly compared to baseline.",
    )


class SkinMetricTimeline(BaseModel):
    """Longitudinal history and compatibility-checked delta for a single normalized metric."""

    metric_code: str
    metric_label: str
    unit: str
    directionality: str
    baseline_provider: str
    baseline_model_version: str
    baseline_interpretation_version: str
    points: list[SkinStoryPoint]
    comparable_point_count: int
    net_observed_delta: float | None = Field(
        default=None,
        description=(
            "Numeric difference (latest_display_value - earliest_comparable_display_value). "
            "Explicitly None if fewer than 2 comparable observations exist."
        ),
    )
    observation_classification: Literal[
        "visual_metric_increase",
        "visual_metric_decrease",
        "visual_metric_stable",
        "insufficient_comparable_data",
    ] = Field(
        ...,
        description=(
            "Strictly descriptive visual metric change category; never framed as "
            "clinical improvement or medical regression."
        ),
    )
    non_clinical_interpretation: str = Field(
        ...,
        description=(
            "Clear explanation distinguishing observed visual score shifts from "
            "clinical improvement and noting capture condition sensitivity."
        ),
    )
    compatibility_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings when historical scans used different providers, models, or units.",
    )


class SkinStoryResponse(BaseModel):
    """Longitudinal Skin Story combining compatible visual observations and user journal history."""

    user_id: UUID
    generated_at: datetime
    total_succeeded_scans: int
    metric_timelines: list[SkinMetricTimeline]
    recent_journal_entries: list[SkinJournalEntryResponse]
    capture_variability_notice: str = SKIN_VARIABILITY_DISCLOSURE
    non_diagnostic_disclaimer: str = SKIN_NON_DIAGNOSTIC_DISCLAIMER
    pigmentation_and_causation_guardrail: str = (
        "ToneTrace AI reports only surface-level visual appearance metrics and user-authored "
        "journal reflections. It never infers the biological or medical cause of pigmentation "
        "(such as melasma, post-inflammatory hyperpigmentation, solar lentigines, or dermatoses) "
        "and never fabricates missing historical observations."
    )
