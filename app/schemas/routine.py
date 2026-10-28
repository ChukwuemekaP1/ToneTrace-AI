"""Pydantic schemas for Phase 10: Routines, Reminders, and Product Reactions.

Enforces:
- Routine step ordering, time-of-day slots, frequency, and product/instruction validation.
- Timezone validation using IANA timezone identifiers (`zoneinfo.ZoneInfo`) and 24h `HH:MM` times.
- Immutable routine completion snapshots separated from mutable routine definitions.
- Notification provider transparency (`is_simulated=True`, `actual_external_delivery=False`
  for the local development test adapter).
- Safety and privacy rules for product reactions: user-reported observations only,
  never clinical allergy diagnoses, with automatic urgent-care guidance escalation
  and suspension of ordinary recommendations when severe or rapidly worsening
  symptoms are reported.
"""

import re
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.shelf import (
    ReactionSeverityLiteral as ReactionSeverity,
)
from app.schemas.shelf import (
    ReactionTypeLiteral as ReactionType,
)

RoutineTimeOfDay = Literal["morning", "evening", "midday", "weekly", "custom"]
StepTimeOfDay = Literal["morning", "evening", "midday", "any"]
RoutineFrequency = Literal["daily", "every_other_day", "weekly", "custom_days"]
StepFrequency = Literal[
    "every_session",
    "daily",
    "alternate_days",
    "twice_weekly",
    "weekly",
    "as_needed",
]
CompletionStatus = Literal["completed", "partial", "skipped"]
StepCompletionStatus = Literal["completed", "skipped"]
ReminderChannel = Literal["in_app", "email", "push"]
ReminderDeliveryStatus = Literal[
    "recorded_local_not_sent",
    "delivered_external",
    "suppressed_opt_out",
    "suppressed_quiet_hours",
    "suppressed_duplicate",
    "failed",
]

_TIME_HHMM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

REACTION_EPISTEMIC_DISCLAIMER = (
    "User-reported observation only. Recording a reaction does not prove that a "
    "product or ingredient caused a symptom and is never a medical or clinical "
    "diagnosis of an allergic reaction or contact dermatitis."
)

URGENT_CARE_REACTION_GUIDANCE = (
    "URGENT CARE GUIDANCE: You reported a severe or rapidly worsening reaction. "
    "Stop using the suspected product(s) immediately, gently rinse the area with "
    "cool water if appropriate, and seek prompt evaluation from a qualified "
    "healthcare professional or urgent care clinic. If you experience facial, lip, "
    "tongue, or throat swelling, difficulty breathing, dizziness, blistering, or "
    "widespread hives, seek emergency medical services immediately. Ordinary "
    "cosmetic product recommendations are suspended for this reaction context."
)


def validate_hhmm_time(value: str, field_label: str = "time") -> str:
    """Validate 24-hour HH:MM time string."""
    cleaned = value.strip()
    if not _TIME_HHMM_RE.match(cleaned):
        raise ValueError(f"{field_label} must be in 24-hour HH:MM format (e.g. '08:00', '21:30').")
    return cleaned


def validate_iana_timezone(tz_name: str) -> str:
    """Validate that a timezone string is a valid IANA timezone identifier."""
    cleaned = tz_name.strip()
    if not cleaned:
        raise ValueError("Timezone identifier cannot be empty.")
    try:
        ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, KeyError, ValueError) as exc:
        raise ValueError(
            f"Invalid IANA timezone '{cleaned}'. Examples: 'UTC', 'America/New_York', "
            "'Europe/London', 'Africa/Lagos'."
        ) from exc
    return cleaned


# ==============================================================================
# 1. ROUTINES & ROUTINE STEPS SCHEMAS
# ==============================================================================


class RoutineStepInput(BaseModel):
    """Input payload for defining a step within a skincare routine."""

    model_config = ConfigDict(extra="forbid")

    step_order: int = Field(
        ge=1,
        le=50,
        description="1-based execution order of the step within the routine",
    )
    time_of_day: StepTimeOfDay | None = Field(
        default=None,
        description="Step time-of-day slot (defaults to parent routine time_of_day)",
    )
    user_product_id: UUID | None = Field(
        default=None,
        description="Optional reference to an item on the user's personal shelf",
    )
    product_id: UUID | None = Field(
        default=None,
        description="Optional reference to a public catalogue product",
    )
    step_label: str | None = Field(
        default=None,
        max_length=200,
        description="Optional step title (auto-resolved from product if omitted)",
    )
    custom_instruction: str | None = Field(
        default=None,
        max_length=1000,
        description="Custom application instruction or non-product step instruction",
    )
    frequency: StepFrequency = Field(
        default="every_session",
        description="Step cadence within the routine",
    )
    wait_time_seconds: int | None = Field(
        default=None,
        ge=0,
        le=7200,
        description="Optional wait duration in seconds after applying this step",
    )
    is_active: bool = Field(
        default=True,
        description="Whether this step is currently active",
    )

    @model_validator(mode="after")
    def validate_reference_or_instruction(self) -> Self:
        """Ensure at least a shelf item, catalogue product, or custom instruction is provided."""
        has_custom = bool(self.custom_instruction and self.custom_instruction.strip())
        if self.user_product_id is None and self.product_id is None and not has_custom:
            raise ValueError(
                "Each routine step must reference a user_product_id, a catalogue product_id, "
                "or provide a non-empty custom_instruction."
            )
        if self.custom_instruction is not None:
            self.custom_instruction = self.custom_instruction.strip() or None
        if self.step_label is not None:
            self.step_label = self.step_label.strip() or None
        return self


class RoutineCreateRequest(BaseModel):
    """Request payload for creating a new skincare routine."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=150,
        description="Routine title (e.g. Morning Barrier & SPF Routine)",
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional description or notes for the routine",
    )
    time_of_day: RoutineTimeOfDay = Field(
        default="morning",
        description="Primary time-of-day slot for the routine",
    )
    frequency: RoutineFrequency = Field(
        default="daily",
        description="Execution cadence for the routine",
    )
    days_of_week: list[int] = Field(
        default_factory=list,
        max_length=7,
        description="Optional ISO weekday numbers (0=Mon..6=Sun) when frequency='custom_days'",
    )
    preferred_local_time: str | None = Field(
        default=None,
        description="Optional preferred 24h local time (HH:MM) in user's configured timezone",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the routine is active",
    )
    steps: list[RoutineStepInput] = Field(
        default_factory=list,
        max_length=30,
        description="Ordered list of routine steps",
    )

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Routine name cannot be blank.")
        return cleaned

    @field_validator("days_of_week")
    @classmethod
    def validate_weekdays(cls, v: list[int]) -> list[int]:
        for day in v:
            if day < 0 or day > 6:
                raise ValueError("days_of_week values must be between 0 (Monday) and 6 (Sunday).")
        return sorted(set(v))

    @field_validator("preferred_local_time")
    @classmethod
    def validate_preferred_time(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_hhmm_time(v, "preferred_local_time")


class RoutineUpdateRequest(BaseModel):
    """Request payload for updating a skincare routine and/or replacing its steps."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    time_of_day: RoutineTimeOfDay | None = None
    frequency: RoutineFrequency | None = None
    days_of_week: list[int] | None = Field(default=None, max_length=7)
    preferred_local_time: str | None = None
    is_active: bool | None = None
    steps: list[RoutineStepInput] | None = Field(
        default=None,
        max_length=30,
        description="If provided, updates the routine steps and increments routine version",
    )

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Routine name cannot be blank.")
        return cleaned

    @field_validator("days_of_week")
    @classmethod
    def validate_optional_weekdays(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        for day in v:
            if day < 0 or day > 6:
                raise ValueError("days_of_week values must be between 0 (Monday) and 6 (Sunday).")
        return sorted(set(v))

    @field_validator("preferred_local_time")
    @classmethod
    def validate_optional_preferred_time(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_hhmm_time(v, "preferred_local_time")


class RoutineStepResponse(BaseModel):
    """Serialized step within a user's routine."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    routine_id: UUID
    step_order: int
    time_of_day: str
    user_product_id: UUID | None = None
    product_id: UUID | None = None
    step_label: str
    custom_instruction: str | None = None
    frequency: str
    wait_time_seconds: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoutineResponse(BaseModel):
    """Serialized routine with ordered steps and user timezone context."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None = None
    time_of_day: str
    frequency: str
    days_of_week: list[int]
    preferred_local_time: str | None = None
    user_timezone: str = "UTC"
    is_active: bool
    version: int
    steps: list[RoutineStepResponse] = Field(default_factory=list)
    total_completions: int = 0
    created_at: datetime
    updated_at: datetime


class RoutineListResponse(BaseModel):
    """Paginated list of user routines."""

    items: list[RoutineResponse]
    total: int
    page: int
    page_size: int


# ==============================================================================
# 2. ROUTINE COMPLETIONS SCHEMAS
# ==============================================================================


class CompletedStepInput(BaseModel):
    """Per-step execution status when recording a routine completion."""

    model_config = ConfigDict(extra="forbid")

    step_order: int = Field(ge=1, le=50, description="Step order number in the routine")
    status: StepCompletionStatus = Field(
        default="completed",
        description="Whether this specific step was completed or skipped",
    )
    notes: str | None = Field(default=None, max_length=500)


class RoutineCompletionCreateRequest(BaseModel):
    """Request payload for logging a routine completion session."""

    model_config = ConfigDict(extra="forbid")

    status: CompletionStatus = Field(
        default="completed",
        description="Overall session status: completed, partial, skipped",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Optional UTC or timezone-aware completion timestamp (defaults to now)",
    )
    step_results: list[CompletedStepInput] | None = Field(
        default=None,
        max_length=50,
        description="Optional per-step status overrides; defaults to all active steps completed",
    )
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional user reflection for this completion session",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=120,
        description="Optional client idempotency key to prevent duplicate completion records",
    )


class CompletedStepSnapshot(BaseModel):
    """Immutable snapshot of a routine step recorded inside a RoutineCompletion."""

    step_order: int
    step_label: str
    user_product_id: str | None = None
    product_id: str | None = None
    custom_instruction: str | None = None
    status: StepCompletionStatus = "completed"
    notes: str | None = None


class RoutineCompletionResponse(BaseModel):
    """Serialized routine completion record with localized date/time and step snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    routine_id: UUID | None = None
    routine_name_snapshot: str
    routine_version_snapshot: int
    time_of_day_snapshot: str
    status: str
    completed_at: datetime
    user_timezone: str
    local_date: str
    local_time: str
    completed_steps_snapshot: list[CompletedStepSnapshot] = Field(default_factory=list)
    notes: str | None = None
    idempotency_key: str | None = None
    created_at: datetime


class RoutineCompletionListResponse(BaseModel):
    """Paginated list of routine completion records."""

    items: list[RoutineCompletionResponse]
    total: int
    page: int
    page_size: int


# ==============================================================================
# 3. REMINDERS & NOTIFICATION DISPATCH SCHEMAS
# ==============================================================================


class ReminderPreferenceUpdateRequest(BaseModel):
    """Request payload for `PUT /api/v1/me/reminders`."""

    model_config = ConfigDict(extra="forbid")

    reminders_enabled: bool = Field(
        default=True,
        description="Master opt-in/opt-out switch; when False, all reminders are suppressed",
    )
    preferred_channels: list[ReminderChannel] = Field(
        default_factory=lambda: ["in_app"],
        max_length=3,
        description="Preferred notification channels",
    )
    morning_reminder_enabled: bool = Field(default=True)
    morning_reminder_time: str = Field(
        default="08:00",
        description="24h local time (HH:MM) for morning reminders",
    )
    evening_reminder_enabled: bool = Field(default=True)
    evening_reminder_time: str = Field(
        default="21:00",
        description="24h local time (HH:MM) for evening reminders",
    )
    quiet_hours_enabled: bool = Field(
        default=True,
        description="Suppress reminder delivery during local quiet hours",
    )
    quiet_hours_start: str = Field(
        default="22:30",
        description="24h local start time (HH:MM) for quiet hours",
    )
    quiet_hours_end: str = Field(
        default="07:00",
        description="24h local end time (HH:MM) for quiet hours",
    )
    timezone_override: str | None = Field(
        default=None,
        max_length=50,
        description="Optional IANA timezone override (falls back to UserProfile.timezone)",
    )

    @field_validator("morning_reminder_time")
    @classmethod
    def validate_morning_time(cls, v: str) -> str:
        return validate_hhmm_time(v, "morning_reminder_time")

    @field_validator("evening_reminder_time")
    @classmethod
    def validate_evening_time(cls, v: str) -> str:
        return validate_hhmm_time(v, "evening_reminder_time")

    @field_validator("quiet_hours_start")
    @classmethod
    def validate_quiet_start(cls, v: str) -> str:
        return validate_hhmm_time(v, "quiet_hours_start")

    @field_validator("quiet_hours_end")
    @classmethod
    def validate_quiet_end(cls, v: str) -> str:
        return validate_hhmm_time(v, "quiet_hours_end")

    @field_validator("timezone_override")
    @classmethod
    def validate_tz_override(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_iana_timezone(v)

    @field_validator("preferred_channels")
    @classmethod
    def deduplicate_channels(cls, v: list[ReminderChannel]) -> list[ReminderChannel]:
        seen: list[ReminderChannel] = []
        for ch in v:
            if ch not in seen:
                seen.append(ch)
        return seen or ["in_app"]


class ReminderPreferenceResponse(BaseModel):
    """Serialized user reminder preferences with effective timezone and provider info."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    reminders_enabled: bool
    preferred_channels: list[str]
    morning_reminder_enabled: bool
    morning_reminder_time: str
    evening_reminder_enabled: bool
    evening_reminder_time: str
    quiet_hours_enabled: bool
    quiet_hours_start: str
    quiet_hours_end: str
    timezone_override: str | None = None
    effective_timezone: str = "UTC"
    opted_out_at: datetime | None = None
    active_notification_provider: str = "local_test_recorder"
    is_simulated_delivery: bool = True
    created_at: datetime
    updated_at: datetime


class ReminderDispatchRequest(BaseModel):
    """Request payload for evaluating and dispatching a routine reminder."""

    model_config = ConfigDict(extra="forbid")

    routine_id: UUID | None = Field(
        default=None,
        description="Optional routine to remind the user about",
    )
    slot: Literal["morning", "evening", "custom"] = Field(
        default="morning",
        description="Reminder slot being evaluated",
    )
    channel: ReminderChannel = Field(
        default="in_app",
        description="Target notification channel",
    )
    scheduled_for_utc: datetime | None = Field(
        default=None,
        description="Reference UTC timestamp for timezone and quiet-hour evaluation",
    )
    idempotency_key: str | None = Field(
        default=None,
        max_length=150,
        description="Optional explicit deduplication key; auto-computed if omitted",
    )


class ReminderDeliveryResponse(BaseModel):
    """Result of a reminder dispatch evaluation, clearly distinguishing local recording."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    routine_id: UUID | None = None
    idempotency_key: str
    channel: str
    provider: str
    is_simulated: bool
    actual_external_delivery: bool
    delivery_mode_disclosure: str
    status: ReminderDeliveryStatus
    duplicate_prevented: bool = False
    scheduled_for_utc: datetime
    user_timezone: str
    user_local_time: str
    failure_reason: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ==============================================================================
# 4. PRODUCT REACTIONS SCHEMAS (SAFETY-AWARE)
# ==============================================================================


class StandaloneReactionCreateRequest(BaseModel):
    """Request payload for `POST /api/v1/me/product-reactions`."""

    model_config = ConfigDict(extra="forbid")

    user_product_id: UUID | None = Field(
        default=None,
        description="Optional shelf item ID (must belong to the authenticated user)",
    )
    product_id: UUID | None = Field(
        default=None,
        description="Optional public catalogue product ID",
    )
    routine_id: UUID | None = Field(
        default=None,
        description="Optional routine ID during which the reaction was observed",
    )
    reaction_type: ReactionType = Field(
        description=(
            "Reaction category: well_tolerated, irritation, redness, breakout, "
            "dryness, stinging, allergic_suspect, no_visible_change"
        ),
    )
    severity: ReactionSeverity = Field(
        default="none",
        description="Perceived severity: none, mild, moderate, severe",
    )
    symptoms: list[str] = Field(
        default_factory=list,
        max_length=25,
        description="Reported symptoms (e.g. redness, burning, swelling, hives, blistering)",
    )
    is_rapidly_worsening: bool = Field(
        default=False,
        description="True if the user reports that the reaction is rapidly worsening or spreading",
    )
    suspected_ingredient_names: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Optional user-suspected ingredient names",
    )
    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Private user notes describing the reaction context",
    )
    observed_at: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when reaction was observed (defaults to now)",
    )

    @model_validator(mode="after")
    def validate_target_reference(self) -> Self:
        """Require at least a shelf item or public catalogue product reference."""
        if self.user_product_id is None and self.product_id is None:
            raise ValueError(
                "At least one of 'user_product_id' or 'product_id' must be provided "
                "when recording a product reaction."
            )
        self.symptoms = [s.strip() for s in self.symptoms if s and s.strip()]
        self.suspected_ingredient_names = [
            s.strip() for s in self.suspected_ingredient_names if s and s.strip()
        ]
        return self


class SafetyAwareReactionResponse(BaseModel):
    """Serialized product reaction with non-diagnostic disclaimer and urgent-care guidance."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    user_product_id: UUID | None = None
    product_id: UUID | None = None
    routine_id: UUID | None = None
    product_display_name: str | None = None
    reaction_type: str
    severity: str
    symptoms: list[str] = Field(default_factory=list)
    is_rapidly_worsening: bool = False
    suspected_ingredient_names: list[str] = Field(default_factory=list)
    notes: str | None = None
    observed_at: datetime
    created_at: datetime
    epistemic_disclaimer: str = REACTION_EPISTEMIC_DISCLAIMER
    is_causal_proof: bool = False
    is_medical_diagnosis: bool = False
    requires_urgent_care_guidance: bool = False
    urgent_care_guidance: str | None = None
    ordinary_recommendations_suspended: bool = False


class ReactionListResponse(BaseModel):
    """Paginated list of user-reported product reactions."""

    items: list[SafetyAwareReactionResponse]
    total: int
    page: int
    page_size: int
    epistemic_disclaimer: str = REACTION_EPISTEMIC_DISCLAIMER
