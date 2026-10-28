"""Service layer for Phase 10: Routines, Reminders, and Product Reactions.

Implements:
- `RoutineService`: Routine CRUD, strict step ordering, ownership validation for
  referenced shelf products and public catalogue products, and timezone-aware
  immutable completion logging separated from mutable routine definitions.
- `ReminderService`: User reminder preferences, IANA timezone conversion,
  quiet-hours enforcement, opt-out enforcement, idempotent deduplication via
  `ReminderDeliveryRecord`, and graceful delivery-failure handling.
- `ReactionService`: User-reported reaction persistence with non-diagnostic
  framing and automatic urgent-care guidance escalation when severe or rapidly
  worsening symptoms are reported.
"""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppException
from app.db.models import (
    Product,
    ProductReaction,
    ReminderDeliveryRecord,
    ReminderPreference,
    Routine,
    RoutineCompletion,
    RoutineStep,
    User,
    UserProduct,
    UserProfile,
)
from app.providers.notification import (
    BaseNotificationProvider,
    NotificationDeliveryError,
    NotificationMessage,
    get_notification_provider,
)
from app.schemas.routine import (
    REACTION_EPISTEMIC_DISCLAIMER,
    URGENT_CARE_REACTION_GUIDANCE,
    CompletedStepSnapshot,
    ReactionListResponse,
    ReminderDeliveryResponse,
    ReminderDispatchRequest,
    ReminderPreferenceResponse,
    ReminderPreferenceUpdateRequest,
    RoutineCompletionCreateRequest,
    RoutineCompletionListResponse,
    RoutineCompletionResponse,
    RoutineCreateRequest,
    RoutineListResponse,
    RoutineResponse,
    RoutineStepInput,
    RoutineStepResponse,
    RoutineUpdateRequest,
    SafetyAwareReactionResponse,
    StandaloneReactionCreateRequest,
)

_URGENT_RED_FLAG_KEYWORDS: tuple[str, ...] = (
    "swelling",
    "swollen",
    "hives",
    "urticaria",
    "blister",
    "blistering",
    "breathing",
    "shortness of breath",
    "anaphylaxis",
    "throat",
    "lip swelling",
    "eye swelling",
    "oozing",
    "ulcer",
    "chemical burn",
    "severe burn",
    "rapidly worsening",
    "spreading rapidly",
    "peeling sheets",
)


def _normalize_utc(dt: datetime | None) -> datetime:
    """Return a timezone-aware UTC datetime (defaulting to current UTC time)."""
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _safe_zoneinfo(tz_name: str | None) -> tuple[str, ZoneInfo]:
    """Resolve an IANA timezone name safely, falling back to UTC if invalid."""
    candidate = (tz_name or "UTC").strip() or "UTC"
    try:
        return candidate, ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return "UTC", ZoneInfo("UTC")


def _is_within_quiet_hours(local_hhmm: str, start_hhmm: str, end_hhmm: str) -> bool:
    """Check whether `local_hhmm` ('HH:MM') falls inside `[start_hhmm, end_hhmm)`.

    Supports both overnight intervals (e.g. '22:30' to '07:00') and same-day
    intervals (e.g. '01:00' to '06:00').
    """
    if start_hhmm == end_hhmm:
        return False
    if start_hhmm < end_hhmm:
        return start_hhmm <= local_hhmm < end_hhmm
    # Overnight wrap-around across midnight
    return local_hhmm >= start_hhmm or local_hhmm < end_hhmm


def evaluate_reaction_urgent_care(
    *,
    reaction_type: str,
    severity: str,
    is_rapidly_worsening: bool,
    symptoms: list[str],
    notes: str | None,
) -> bool:
    """Determine if a user-reported reaction requires urgent-care guidance escalation."""
    if is_rapidly_worsening:
        return True
    if severity == "severe":
        return True
    if reaction_type == "allergic_suspect" and severity in ("moderate", "severe"):
        return True

    combined_text = " ".join(symptoms).lower()
    if notes:
        combined_text = f"{combined_text} {notes.lower()}"

    return any(keyword in combined_text for keyword in _URGENT_RED_FLAG_KEYWORDS)


class RoutineService:
    """Service managing user skincare routines, ordered steps, and completion history."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _get_effective_user_timezone(self, user_id: UUID) -> str:
        """Resolve effective IANA timezone from ReminderPreference or UserProfile."""
        pref_stmt = select(ReminderPreference.timezone_override).where(
            ReminderPreference.user_id == user_id
        )
        tz_override = (await self._db.execute(pref_stmt)).scalar_one_or_none()
        if tz_override:
            tz_name, _ = _safe_zoneinfo(tz_override)
            return tz_name

        prof_stmt = select(UserProfile.timezone).where(UserProfile.user_id == user_id)
        prof_tz = (await self._db.execute(prof_stmt)).scalar_one_or_none()
        tz_name, _ = _safe_zoneinfo(prof_tz)
        return tz_name

    async def _validate_and_build_steps(
        self,
        *,
        user_id: UUID,
        routine_id: UUID,
        default_time_of_day: str,
        steps_input: list[RoutineStepInput],
    ) -> list[RoutineStep]:
        """Validate step order uniqueness and ownership of referenced products."""
        seen_orders: set[int] = set()
        for step_in in steps_input:
            if step_in.step_order in seen_orders:
                raise AppException(
                    status_code=422,
                    code="DUPLICATE_ROUTINE_STEP_ORDER",
                    message=(
                        f"Duplicate step_order {step_in.step_order} in routine steps. "
                        "Each step must have a distinct 1-based step_order."
                    ),
                )
            seen_orders.add(step_in.step_order)

        ordered_inputs = sorted(steps_input, key=lambda s: s.step_order)
        built_steps: list[RoutineStep] = []

        for step_in in ordered_inputs:
            resolved_label = step_in.step_label
            linked_product_id = step_in.product_id

            if step_in.user_product_id is not None:
                up_stmt = (
                    select(UserProduct)
                    .where(
                        UserProduct.id == step_in.user_product_id,
                        UserProduct.user_id == user_id,
                    )
                    .options(selectinload(UserProduct.product))
                )
                user_product = (await self._db.execute(up_stmt)).scalar_one_or_none()
                if user_product is None:
                    raise AppException(
                        status_code=404,
                        code="SHELF_ITEM_NOT_FOUND",
                        message=(
                            f"Referenced shelf item '{step_in.user_product_id}' was not found "
                            "on your shelf."
                        ),
                    )
                if not resolved_label:
                    if user_product.product is not None:
                        resolved_label = user_product.product.name
                    elif user_product.custom_name:
                        resolved_label = user_product.custom_name
                if linked_product_id is None and user_product.product_id is not None:
                    linked_product_id = user_product.product_id

            if step_in.product_id is not None:
                prod_stmt = select(Product).where(Product.id == step_in.product_id)
                catalogue_product = (await self._db.execute(prod_stmt)).scalar_one_or_none()
                if catalogue_product is None:
                    raise AppException(
                        status_code=404,
                        code="CATALOGUE_PRODUCT_NOT_FOUND",
                        message=(
                            f"Referenced catalogue product '{step_in.product_id}' was not found."
                        ),
                    )
                if not resolved_label:
                    resolved_label = catalogue_product.name

            if not resolved_label:
                resolved_label = (step_in.custom_instruction or f"Step {step_in.step_order}")[:200]

            step_tod = step_in.time_of_day
            if step_tod is None:
                step_tod = (
                    default_time_of_day  # type: ignore[assignment]
                    if default_time_of_day in ("morning", "evening", "midday")
                    else "any"
                )

            built_steps.append(
                RoutineStep(
                    routine_id=routine_id,
                    step_order=step_in.step_order,
                    time_of_day=step_tod,
                    user_product_id=step_in.user_product_id,
                    product_id=linked_product_id,
                    step_label=resolved_label,
                    custom_instruction=step_in.custom_instruction,
                    frequency=step_in.frequency,
                    wait_time_seconds=step_in.wait_time_seconds,
                    is_active=step_in.is_active,
                )
            )

        return built_steps

    async def _serialize_routine(
        self,
        routine: Routine,
        user_timezone: str,
    ) -> RoutineResponse:
        """Convert a Routine ORM entity into a RoutineResponse."""
        count_stmt = (
            select(func.count())
            .select_from(RoutineCompletion)
            .where(
                RoutineCompletion.user_id == routine.user_id,
                RoutineCompletion.routine_id == routine.id,
            )
        )
        total_completions = int((await self._db.execute(count_stmt)).scalar_one() or 0)
        sorted_steps = sorted(routine.steps, key=lambda s: s.step_order)
        return RoutineResponse(
            id=routine.id,
            user_id=routine.user_id,
            name=routine.name,
            description=routine.description,
            time_of_day=routine.time_of_day,
            frequency=routine.frequency,
            days_of_week=list(routine.days_of_week or []),
            preferred_local_time=routine.preferred_local_time,
            user_timezone=user_timezone,
            is_active=routine.is_active,
            version=routine.version,
            steps=[RoutineStepResponse.model_validate(s) for s in sorted_steps],
            total_completions=total_completions,
            created_at=routine.created_at,
            updated_at=routine.updated_at,
        )

    async def list_routines(
        self,
        *,
        user: User,
        time_of_day: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> RoutineListResponse:
        """Return paginated routines owned by the authenticated user."""
        filters = [Routine.user_id == user.id]
        if time_of_day is not None:
            filters.append(Routine.time_of_day == time_of_day)
        if is_active is not None:
            filters.append(Routine.is_active == is_active)

        count_stmt = select(func.count()).select_from(Routine).where(*filters)
        total = int((await self._db.execute(count_stmt)).scalar_one() or 0)

        stmt = (
            select(Routine)
            .where(*filters)
            .options(selectinload(Routine.steps))
            .order_by(Routine.created_at.desc(), Routine.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        routines = list((await self._db.execute(stmt)).scalars().all())
        user_tz = await self._get_effective_user_timezone(user.id)

        items = [await self._serialize_routine(r, user_tz) for r in routines]
        return RoutineListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def create_routine(
        self,
        *,
        user: User,
        payload: RoutineCreateRequest,
    ) -> RoutineResponse:
        """Create a new skincare routine with validated ordered steps."""
        routine = Routine(
            user_id=user.id,
            name=payload.name,
            description=payload.description,
            time_of_day=payload.time_of_day,
            frequency=payload.frequency,
            days_of_week=payload.days_of_week,
            preferred_local_time=payload.preferred_local_time,
            is_active=payload.is_active,
            version=1,
        )
        self._db.add(routine)
        await self._db.flush()

        built_steps = await self._validate_and_build_steps(
            user_id=user.id,
            routine_id=routine.id,
            default_time_of_day=routine.time_of_day,
            steps_input=payload.steps,
        )
        for step in built_steps:
            self._db.add(step)

        await self._db.commit()

        loaded = await self._get_owned_routine_model(user.id, routine.id)
        user_tz = await self._get_effective_user_timezone(user.id)
        return await self._serialize_routine(loaded, user_tz)

    async def _get_owned_routine_model(self, user_id: UUID, routine_id: UUID) -> Routine:
        """Fetch a routine owned by `user_id` with steps loaded, or raise 404."""
        stmt = (
            select(Routine)
            .where(Routine.id == routine_id, Routine.user_id == user_id)
            .options(selectinload(Routine.steps))
        )
        routine = (await self._db.execute(stmt)).scalar_one_or_none()
        if routine is None:
            raise AppException(
                status_code=404,
                code="ROUTINE_NOT_FOUND",
                message="Routine not found.",
            )
        return routine

    async def get_routine(self, *, user: User, routine_id: UUID) -> RoutineResponse:
        """Retrieve a single routine owned by the authenticated user."""
        routine = await self._get_owned_routine_model(user.id, routine_id)
        user_tz = await self._get_effective_user_timezone(user.id)
        return await self._serialize_routine(routine, user_tz)

    async def update_routine(
        self,
        *,
        user: User,
        routine_id: UUID,
        payload: RoutineUpdateRequest,
    ) -> RoutineResponse:
        """Update routine attributes and/or steps while preserving completion history."""
        routine = await self._get_owned_routine_model(user.id, routine_id)
        changed = False

        if payload.name is not None and payload.name != routine.name:
            routine.name = payload.name
            changed = True
        if "description" in payload.model_fields_set:
            routine.description = payload.description
            changed = True
        if payload.time_of_day is not None and payload.time_of_day != routine.time_of_day:
            routine.time_of_day = payload.time_of_day
            changed = True
        if payload.frequency is not None and payload.frequency != routine.frequency:
            routine.frequency = payload.frequency
            changed = True
        if payload.days_of_week is not None and payload.days_of_week != routine.days_of_week:
            routine.days_of_week = payload.days_of_week
            changed = True
        if "preferred_local_time" in payload.model_fields_set:
            routine.preferred_local_time = payload.preferred_local_time
            changed = True
        if payload.is_active is not None and payload.is_active != routine.is_active:
            routine.is_active = payload.is_active
            changed = True

        if payload.steps is not None:
            new_steps = await self._validate_and_build_steps(
                user_id=user.id,
                routine_id=routine.id,
                default_time_of_day=routine.time_of_day,
                steps_input=payload.steps,
            )
            routine.steps.clear()
            await self._db.flush()
            for step in new_steps:
                routine.steps.append(step)
            changed = True

        if changed:
            routine.version += 1

        await self._db.commit()
        loaded = await self._get_owned_routine_model(user.id, routine.id)
        user_tz = await self._get_effective_user_timezone(user.id)
        return await self._serialize_routine(loaded, user_tz)

    async def delete_routine(self, *, user: User, routine_id: UUID) -> None:
        """Delete a routine owned by the user (historical completions retain snapshots)."""
        routine = await self._get_owned_routine_model(user.id, routine_id)
        await self._db.delete(routine)
        await self._db.commit()

    async def record_completion(
        self,
        *,
        user: User,
        routine_id: UUID,
        payload: RoutineCompletionCreateRequest,
    ) -> RoutineCompletionResponse:
        """Record an immutable completion log with localized date/time in user's timezone."""
        routine = await self._get_owned_routine_model(user.id, routine_id)

        if payload.idempotency_key:
            existing_stmt = select(RoutineCompletion).where(
                RoutineCompletion.user_id == user.id,
                RoutineCompletion.routine_id == routine.id,
                RoutineCompletion.idempotency_key == payload.idempotency_key,
            )
            existing = (await self._db.execute(existing_stmt)).scalar_one_or_none()
            if existing is not None:
                return self._serialize_completion(existing)

        completed_utc = _normalize_utc(payload.completed_at)
        user_tz_name = await self._get_effective_user_timezone(user.id)
        _, tz_obj = _safe_zoneinfo(user_tz_name)
        local_dt = completed_utc.astimezone(tz_obj)
        local_date = local_dt.strftime("%Y-%m-%d")
        local_time = local_dt.strftime("%H:%M:%S")

        step_overrides = {item.step_order: item for item in (payload.step_results or [])}
        sorted_steps = sorted(routine.steps, key=lambda s: s.step_order)
        step_snapshots: list[dict[str, object]] = []
        for step in sorted_steps:
            if not step.is_active and step.step_order not in step_overrides:
                continue
            override = step_overrides.get(step.step_order)
            step_status = (
                override.status
                if override is not None
                else ("skipped" if payload.status == "skipped" else "completed")
            )
            step_snapshots.append(
                CompletedStepSnapshot(
                    step_order=step.step_order,
                    step_label=step.step_label,
                    user_product_id=(str(step.user_product_id) if step.user_product_id else None),
                    product_id=str(step.product_id) if step.product_id else None,
                    custom_instruction=step.custom_instruction,
                    status=step_status,
                    notes=override.notes if override else None,
                ).model_dump()
            )

        completion = RoutineCompletion(
            user_id=user.id,
            routine_id=routine.id,
            routine_name_snapshot=routine.name,
            routine_version_snapshot=routine.version,
            time_of_day_snapshot=routine.time_of_day,
            status=payload.status,
            completed_at=completed_utc,
            user_timezone=user_tz_name,
            local_date=local_date,
            local_time=local_time,
            completed_steps_snapshot=step_snapshots,
            notes=payload.notes,
            idempotency_key=payload.idempotency_key,
        )
        self._db.add(completion)
        await self._db.commit()
        await self._db.refresh(completion)
        return self._serialize_completion(completion)

    async def list_completions(
        self,
        *,
        user: User,
        routine_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> RoutineCompletionListResponse:
        """List historical completions for a routine owned by the user."""
        _ = await self._get_owned_routine_model(user.id, routine_id)

        filters = [
            RoutineCompletion.user_id == user.id,
            RoutineCompletion.routine_id == routine_id,
        ]
        count_stmt = select(func.count()).select_from(RoutineCompletion).where(*filters)
        total = int((await self._db.execute(count_stmt)).scalar_one() or 0)

        stmt = (
            select(RoutineCompletion)
            .where(*filters)
            .order_by(RoutineCompletion.completed_at.desc(), RoutineCompletion.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self._db.execute(stmt)).scalars().all())
        return RoutineCompletionListResponse(
            items=[self._serialize_completion(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _serialize_completion(record: RoutineCompletion) -> RoutineCompletionResponse:
        snapshots = [
            CompletedStepSnapshot.model_validate(s) for s in (record.completed_steps_snapshot or [])
        ]
        return RoutineCompletionResponse(
            id=record.id,
            user_id=record.user_id,
            routine_id=record.routine_id,
            routine_name_snapshot=record.routine_name_snapshot,
            routine_version_snapshot=record.routine_version_snapshot,
            time_of_day_snapshot=record.time_of_day_snapshot,
            status=record.status,
            completed_at=record.completed_at,
            user_timezone=record.user_timezone,
            local_date=record.local_date,
            local_time=record.local_time,
            completed_steps_snapshot=snapshots,
            notes=record.notes,
            idempotency_key=record.idempotency_key,
            created_at=record.created_at,
        )


class ReminderService:
    """Service managing user reminder preferences and idempotent reminder dispatch."""

    def __init__(
        self,
        db: AsyncSession,
        notification_provider: BaseNotificationProvider | None = None,
    ) -> None:
        self._db = db
        self._provider = notification_provider or get_notification_provider()

    async def _get_or_create_preferences(self, user_id: UUID) -> ReminderPreference:
        stmt = select(ReminderPreference).where(ReminderPreference.user_id == user_id)
        prefs = (await self._db.execute(stmt)).scalar_one_or_none()
        if prefs is None:
            prefs = ReminderPreference(
                user_id=user_id,
                reminders_enabled=True,
                preferred_channels=["in_app"],
                morning_reminder_enabled=True,
                morning_reminder_time="08:00",
                evening_reminder_enabled=True,
                evening_reminder_time="21:00",
                quiet_hours_enabled=True,
                quiet_hours_start="22:30",
                quiet_hours_end="07:00",
                timezone_override=None,
                opted_out_at=None,
            )
            self._db.add(prefs)
            await self._db.commit()
            await self._db.refresh(prefs)
        return prefs

    async def _resolve_effective_timezone(
        self,
        user_id: UUID,
        prefs: ReminderPreference,
    ) -> str:
        if prefs.timezone_override:
            tz_name, _ = _safe_zoneinfo(prefs.timezone_override)
            return tz_name
        prof_stmt = select(UserProfile.timezone).where(UserProfile.user_id == user_id)
        prof_tz = (await self._db.execute(prof_stmt)).scalar_one_or_none()
        tz_name, _ = _safe_zoneinfo(prof_tz)
        return tz_name

    async def _serialize_preferences(
        self,
        prefs: ReminderPreference,
    ) -> ReminderPreferenceResponse:
        effective_tz = await self._resolve_effective_timezone(prefs.user_id, prefs)
        return ReminderPreferenceResponse(
            id=prefs.id,
            user_id=prefs.user_id,
            reminders_enabled=prefs.reminders_enabled,
            preferred_channels=list(prefs.preferred_channels or ["in_app"]),
            morning_reminder_enabled=prefs.morning_reminder_enabled,
            morning_reminder_time=prefs.morning_reminder_time,
            evening_reminder_enabled=prefs.evening_reminder_enabled,
            evening_reminder_time=prefs.evening_reminder_time,
            quiet_hours_enabled=prefs.quiet_hours_enabled,
            quiet_hours_start=prefs.quiet_hours_start,
            quiet_hours_end=prefs.quiet_hours_end,
            timezone_override=prefs.timezone_override,
            effective_timezone=effective_tz,
            opted_out_at=prefs.opted_out_at,
            active_notification_provider=self._provider.name,
            is_simulated_delivery=self._provider.is_simulated_delivery,
            created_at=prefs.created_at,
            updated_at=prefs.updated_at,
        )

    async def get_preferences(self, *, user: User) -> ReminderPreferenceResponse:
        """Retrieve the user's current reminder preferences."""
        prefs = await self._get_or_create_preferences(user.id)
        return await self._serialize_preferences(prefs)

    async def update_preferences(
        self,
        *,
        user: User,
        payload: ReminderPreferenceUpdateRequest,
    ) -> ReminderPreferenceResponse:
        """Update the user's reminder preferences and record opt-out timestamps."""
        prefs = await self._get_or_create_preferences(user.id)

        if not payload.reminders_enabled and prefs.reminders_enabled:
            prefs.opted_out_at = datetime.now(UTC)
        elif payload.reminders_enabled:
            prefs.opted_out_at = None

        prefs.reminders_enabled = payload.reminders_enabled
        prefs.preferred_channels = list(payload.preferred_channels)
        prefs.morning_reminder_enabled = payload.morning_reminder_enabled
        prefs.morning_reminder_time = payload.morning_reminder_time
        prefs.evening_reminder_enabled = payload.evening_reminder_enabled
        prefs.evening_reminder_time = payload.evening_reminder_time
        prefs.quiet_hours_enabled = payload.quiet_hours_enabled
        prefs.quiet_hours_start = payload.quiet_hours_start
        prefs.quiet_hours_end = payload.quiet_hours_end
        prefs.timezone_override = payload.timezone_override

        await self._db.commit()
        await self._db.refresh(prefs)
        return await self._serialize_preferences(prefs)

    async def dispatch_reminder(
        self,
        *,
        user: User,
        payload: ReminderDispatchRequest,
    ) -> ReminderDeliveryResponse:
        """Evaluate opt-outs, quiet hours, timezone, and idempotency before dispatching."""
        routine: Routine | None = None
        if payload.routine_id is not None:
            r_stmt = select(Routine).where(
                Routine.id == payload.routine_id,
                Routine.user_id == user.id,
            )
            routine = (await self._db.execute(r_stmt)).scalar_one_or_none()
            if routine is None:
                raise AppException(
                    status_code=404,
                    code="ROUTINE_NOT_FOUND",
                    message="Referenced routine was not found.",
                )

        prefs = await self._get_or_create_preferences(user.id)
        effective_tz = await self._resolve_effective_timezone(user.id, prefs)
        _, tz_obj = _safe_zoneinfo(effective_tz)

        scheduled_utc = _normalize_utc(payload.scheduled_for_utc)
        local_dt = scheduled_utc.astimezone(tz_obj)
        local_dt_str = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        local_hhmm = local_dt.strftime("%H:%M")
        local_date_str = local_dt.strftime("%Y-%m-%d")

        idem_key = (
            payload.idempotency_key.strip()
            if payload.idempotency_key and payload.idempotency_key.strip()
            else (
                f"rem:{user.id}:{payload.routine_id or 'general'}:"
                f"{payload.channel}:{local_date_str}:{payload.slot}"
            )
        )

        # 1. Check idempotency / deduplication record first
        existing_stmt = select(ReminderDeliveryRecord).where(
            ReminderDeliveryRecord.user_id == user.id,
            ReminderDeliveryRecord.idempotency_key == idem_key,
        )
        existing = (await self._db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return self._serialize_delivery(
                existing,
                override_status="suppressed_duplicate",
                duplicate_prevented=True,
            )

        routine_title = routine.name if routine is not None else f"{payload.slot.title()} Routine"
        title = f"ToneTrace Routine Reminder: {routine_title}"
        body = (
            f"Time for your {routine_title} ({local_hhmm} {effective_tz}). "
            "Log your completion or skip steps anytime in ToneTrace."
        )
        payload_summary = {
            "title": title,
            "body": body,
            "slot": payload.slot,
            "routine_name": routine_title,
        }

        # 2. Check master opt-out, slot opt-out, and channel opt-out
        opt_out_reason: str | None = None
        if not prefs.reminders_enabled:
            opt_out_reason = (
                "User has opted out of all routine reminders (reminders_enabled=False)."
            )
        elif payload.slot == "morning" and not prefs.morning_reminder_enabled:
            opt_out_reason = "User has disabled morning routine reminders."
        elif payload.slot == "evening" and not prefs.evening_reminder_enabled:
            opt_out_reason = "User has disabled evening routine reminders."
        elif payload.channel not in (prefs.preferred_channels or ["in_app"]):
            opt_out_reason = f"Channel '{payload.channel}' is not enabled in preferred_channels."

        if opt_out_reason is not None:
            record = ReminderDeliveryRecord(
                user_id=user.id,
                routine_id=payload.routine_id,
                idempotency_key=idem_key,
                channel=payload.channel,
                provider=self._provider.name,
                is_simulated=self._provider.is_simulated_delivery,
                actual_external_delivery=False,
                status="suppressed_opt_out",
                scheduled_for_utc=scheduled_utc,
                user_timezone=effective_tz,
                user_local_time=local_dt_str,
                failure_reason=opt_out_reason,
                payload_summary=payload_summary,
            )
            self._db.add(record)
            await self._db.commit()
            await self._db.refresh(record)
            return self._serialize_delivery(record)

        # 3. Check quiet hours in the user's local timezone
        if prefs.quiet_hours_enabled and _is_within_quiet_hours(
            local_hhmm,
            prefs.quiet_hours_start,
            prefs.quiet_hours_end,
        ):
            quiet_reason = (
                f"Local time {local_hhmm} ({effective_tz}) falls within user's configured "
                f"quiet hours ({prefs.quiet_hours_start} - {prefs.quiet_hours_end})."
            )
            record = ReminderDeliveryRecord(
                user_id=user.id,
                routine_id=payload.routine_id,
                idempotency_key=idem_key,
                channel=payload.channel,
                provider=self._provider.name,
                is_simulated=self._provider.is_simulated_delivery,
                actual_external_delivery=False,
                status="suppressed_quiet_hours",
                scheduled_for_utc=scheduled_utc,
                user_timezone=effective_tz,
                user_local_time=local_dt_str,
                failure_reason=quiet_reason,
                payload_summary=payload_summary,
            )
            self._db.add(record)
            await self._db.commit()
            await self._db.refresh(record)
            return self._serialize_delivery(record)

        # 4. Dispatch via NotificationProvider and handle delivery failures gracefully
        message = NotificationMessage(
            idempotency_key=idem_key,
            user_id=user.id,
            channel=payload.channel,
            title=title,
            body=body,
            scheduled_for_utc=scheduled_utc,
            user_timezone=effective_tz,
            user_local_time=local_dt_str,
            routine_id=payload.routine_id,
            metadata=payload_summary,
        )
        try:
            receipt = await self._provider.send_notification(message)
            record = ReminderDeliveryRecord(
                user_id=user.id,
                routine_id=payload.routine_id,
                idempotency_key=idem_key,
                channel=payload.channel,
                provider=receipt.provider,
                is_simulated=receipt.is_simulated,
                actual_external_delivery=receipt.actual_external_delivery,
                status=receipt.delivery_status,
                scheduled_for_utc=scheduled_utc,
                user_timezone=effective_tz,
                user_local_time=local_dt_str,
                failure_reason=receipt.error_message,
                payload_summary={
                    **payload_summary,
                    "provider_message_id": receipt.provider_message_id,
                    "delivery_disclosure": receipt.delivery_disclosure,
                },
            )
        except NotificationDeliveryError as exc:
            record = ReminderDeliveryRecord(
                user_id=user.id,
                routine_id=payload.routine_id,
                idempotency_key=idem_key,
                channel=payload.channel,
                provider=self._provider.name,
                is_simulated=self._provider.is_simulated_delivery,
                actual_external_delivery=False,
                status="failed",
                scheduled_for_utc=scheduled_utc,
                user_timezone=effective_tz,
                user_local_time=local_dt_str,
                failure_reason=str(exc),
                payload_summary=payload_summary,
            )

        self._db.add(record)
        await self._db.commit()
        await self._db.refresh(record)
        return self._serialize_delivery(record)

    @staticmethod
    def _serialize_delivery(
        record: ReminderDeliveryRecord,
        *,
        override_status: str | None = None,
        duplicate_prevented: bool = False,
    ) -> ReminderDeliveryResponse:
        status_val = override_status or record.status
        if record.is_simulated and not record.actual_external_delivery:
            disclosure = (
                "SIMULATED LOCAL RECORDING ONLY: Notification was recorded by the local "
                "test adapter and was NOT sent via an external email or push provider."
            )
        elif record.actual_external_delivery:
            disclosure = "Delivered via verified external notification provider."
        else:
            disclosure = "Notification was not transmitted externally."

        return ReminderDeliveryResponse(
            id=record.id,
            user_id=record.user_id,
            routine_id=record.routine_id,
            idempotency_key=record.idempotency_key,
            channel=record.channel,
            provider=record.provider,
            is_simulated=record.is_simulated,
            actual_external_delivery=record.actual_external_delivery,
            delivery_mode_disclosure=disclosure,
            status=status_val,  # type: ignore[arg-type]
            duplicate_prevented=duplicate_prevented,
            scheduled_for_utc=record.scheduled_for_utc,
            user_timezone=record.user_timezone,
            user_local_time=record.user_local_time,
            failure_reason=record.failure_reason,
            payload_summary=dict(record.payload_summary or {}),
            created_at=record.created_at,
        )


class ReactionService:
    """Service for recording and querying user-reported product reactions with safety guidance."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_reaction(
        self,
        *,
        user: User,
        payload: StandaloneReactionCreateRequest,
    ) -> SafetyAwareReactionResponse:
        """Record a user-reported product reaction with non-diagnostic urgent-care evaluation."""
        user_product: UserProduct | None = None
        catalogue_product: Product | None = None
        linked_product_id = payload.product_id
        display_name: str | None = None

        if payload.user_product_id is not None:
            up_stmt = (
                select(UserProduct)
                .where(
                    UserProduct.id == payload.user_product_id,
                    UserProduct.user_id == user.id,
                )
                .options(selectinload(UserProduct.product))
            )
            user_product = (await self._db.execute(up_stmt)).scalar_one_or_none()
            if user_product is None:
                raise AppException(
                    status_code=404,
                    code="SHELF_ITEM_NOT_FOUND",
                    message="Referenced shelf item was not found on your shelf.",
                )
            if linked_product_id is None and user_product.product_id is not None:
                linked_product_id = user_product.product_id
            if user_product.product is not None:
                display_name = user_product.product.name
            elif user_product.custom_name:
                display_name = user_product.custom_name

        if linked_product_id is not None:
            prod_stmt = select(Product).where(Product.id == linked_product_id)
            catalogue_product = (await self._db.execute(prod_stmt)).scalar_one_or_none()
            if catalogue_product is None and payload.product_id is not None:
                raise AppException(
                    status_code=404,
                    code="CATALOGUE_PRODUCT_NOT_FOUND",
                    message="Referenced public catalogue product was not found.",
                )
            if catalogue_product is not None and not display_name:
                display_name = catalogue_product.name

        if payload.routine_id is not None:
            r_stmt = select(Routine).where(
                Routine.id == payload.routine_id,
                Routine.user_id == user.id,
            )
            routine = (await self._db.execute(r_stmt)).scalar_one_or_none()
            if routine is None:
                raise AppException(
                    status_code=404,
                    code="ROUTINE_NOT_FOUND",
                    message="Referenced routine was not found.",
                )

        requires_urgent_care = evaluate_reaction_urgent_care(
            reaction_type=payload.reaction_type,
            severity=payload.severity,
            is_rapidly_worsening=payload.is_rapidly_worsening,
            symptoms=payload.symptoms,
            notes=payload.notes,
        )

        observed_utc = _normalize_utc(payload.observed_at)
        reaction = ProductReaction(
            user_id=user.id,
            user_product_id=payload.user_product_id,
            product_id=linked_product_id,
            routine_id=payload.routine_id,
            reaction_type=payload.reaction_type,
            severity=payload.severity,
            symptoms=payload.symptoms,
            is_rapidly_worsening=payload.is_rapidly_worsening,
            urgent_care_escalation_shown=requires_urgent_care,
            suspected_ingredient_names=payload.suspected_ingredient_names,
            notes=payload.notes,
            observed_at=observed_utc,
        )
        self._db.add(reaction)
        await self._db.commit()
        await self._db.refresh(reaction)

        return self._serialize_reaction(reaction, product_display_name=display_name)

    async def list_reactions(
        self,
        *,
        user: User,
        reaction_type: str | None = None,
        severity: str | None = None,
        user_product_id: UUID | None = None,
        product_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ReactionListResponse:
        """List user-reported product reactions in reverse chronological order."""
        filters = [ProductReaction.user_id == user.id]
        if reaction_type is not None:
            filters.append(ProductReaction.reaction_type == reaction_type)
        if severity is not None:
            filters.append(ProductReaction.severity == severity)
        if user_product_id is not None:
            filters.append(ProductReaction.user_product_id == user_product_id)
        if product_id is not None:
            filters.append(ProductReaction.product_id == product_id)

        count_stmt = select(func.count()).select_from(ProductReaction).where(*filters)
        total = int((await self._db.execute(count_stmt)).scalar_one() or 0)

        stmt = (
            select(ProductReaction)
            .where(*filters)
            .options(
                selectinload(ProductReaction.user_product),
                selectinload(ProductReaction.product),
            )
            .order_by(ProductReaction.observed_at.desc(), ProductReaction.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self._db.execute(stmt)).scalars().all())

        items: list[SafetyAwareReactionResponse] = []
        for row in rows:
            disp_name: str | None = None
            if row.product is not None:
                disp_name = row.product.name
            elif row.user_product is not None and row.user_product.custom_name:
                disp_name = row.user_product.custom_name
            items.append(self._serialize_reaction(row, product_display_name=disp_name))

        return ReactionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            epistemic_disclaimer=REACTION_EPISTEMIC_DISCLAIMER,
        )

    @staticmethod
    def _serialize_reaction(
        reaction: ProductReaction,
        *,
        product_display_name: str | None = None,
    ) -> SafetyAwareReactionResponse:
        requires_urgent = bool(
            reaction.urgent_care_escalation_shown
            or evaluate_reaction_urgent_care(
                reaction_type=reaction.reaction_type,
                severity=reaction.severity,
                is_rapidly_worsening=reaction.is_rapidly_worsening,
                symptoms=list(reaction.symptoms or []),
                notes=reaction.notes,
            )
        )
        return SafetyAwareReactionResponse(
            id=reaction.id,
            user_id=reaction.user_id,
            user_product_id=reaction.user_product_id,
            product_id=reaction.product_id,
            routine_id=reaction.routine_id,
            product_display_name=product_display_name,
            reaction_type=reaction.reaction_type,
            severity=reaction.severity,
            symptoms=list(reaction.symptoms or []),
            is_rapidly_worsening=reaction.is_rapidly_worsening,
            suspected_ingredient_names=list(reaction.suspected_ingredient_names or []),
            notes=reaction.notes,
            observed_at=reaction.observed_at,
            created_at=reaction.created_at,
            epistemic_disclaimer=REACTION_EPISTEMIC_DISCLAIMER,
            is_causal_proof=False,
            is_medical_diagnosis=False,
            requires_urgent_care_guidance=requires_urgent,
            urgent_care_guidance=URGENT_CARE_REACTION_GUIDANCE if requires_urgent else None,
            ordinary_recommendations_suspended=requires_urgent,
        )
