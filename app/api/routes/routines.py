"""API routes for Phase 10: Routines, Reminders, and Product Reactions.

Implements:
- `GET /api/v1/me/routines`
- `POST /api/v1/me/routines`
- `GET /api/v1/me/routines/{routine_id}`
- `PATCH /api/v1/me/routines/{routine_id}`
- `DELETE /api/v1/me/routines/{routine_id}`
- `POST /api/v1/me/routines/{routine_id}/completions`
- `GET /api/v1/me/routines/{routine_id}/completions`
- `GET /api/v1/me/reminders`
- `PUT /api/v1/me/reminders`
- `POST /api/v1/me/reminders/dispatch`
- `POST /api/v1/me/product-reactions`
- `GET /api/v1/me/product-reactions`
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user
from app.db.models import User
from app.db.session import get_db_session
from app.providers.notification import BaseNotificationProvider, get_notification_provider
from app.schemas.common import ResponseEnvelope
from app.schemas.routine import (
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
    RoutineTimeOfDay,
    RoutineUpdateRequest,
    SafetyAwareReactionResponse,
    StandaloneReactionCreateRequest,
)
from app.schemas.shelf import (
    ReactionSeverityLiteral as ReactionSeverity,
)
from app.schemas.shelf import (
    ReactionTypeLiteral as ReactionType,
)
from app.services.routine_service import ReactionService, ReminderService, RoutineService

router = APIRouter(prefix="/me", tags=["Routines, Reminders & Reactions"])


# ==============================================================================
# 1. ROUTINES & ROUTINE COMPLETIONS ENDPOINTS
# ==============================================================================


@router.get(
    "/routines",
    response_model=ResponseEnvelope[RoutineListResponse],
    summary="List the authenticated user's skincare routines",
)
async def list_my_routines(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    time_of_day: Annotated[
        RoutineTimeOfDay | None,
        Query(description="Optional filter by routine time of day"),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(description="Optional filter by active status"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=50, description="Items per page")] = 20,
) -> ResponseEnvelope[RoutineListResponse]:
    """List user routines with ordered steps and completion counts."""
    service = RoutineService(db=db)
    result = await service.list_routines(
        user=current_user,
        time_of_day=time_of_day,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return ResponseEnvelope(data=result)


@router.post(
    "/routines",
    response_model=ResponseEnvelope[RoutineResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new skincare routine with ordered steps",
)
async def create_my_routine(
    payload: RoutineCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[RoutineResponse]:
    """Create a routine and validate ownership of any referenced shelf products."""
    service = RoutineService(db=db)
    result = await service.create_routine(user=current_user, payload=payload)
    return ResponseEnvelope(data=result)


@router.get(
    "/routines/{routine_id}",
    response_model=ResponseEnvelope[RoutineResponse],
    summary="Retrieve a specific routine owned by the user",
)
async def get_my_routine(
    routine_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[RoutineResponse]:
    """Retrieve a routine and its ordered steps, enforcing strict ownership isolation."""
    service = RoutineService(db=db)
    result = await service.get_routine(user=current_user, routine_id=routine_id)
    return ResponseEnvelope(data=result)


@router.patch(
    "/routines/{routine_id}",
    response_model=ResponseEnvelope[RoutineResponse],
    summary="Update a routine or its ordered steps without erasing completion history",
)
async def update_my_routine(
    routine_id: UUID,
    payload: RoutineUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[RoutineResponse]:
    """Update routine metadata or steps and increment routine version."""
    service = RoutineService(db=db)
    result = await service.update_routine(
        user=current_user,
        routine_id=routine_id,
        payload=payload,
    )
    return ResponseEnvelope(data=result)


@router.delete(
    "/routines/{routine_id}",
    response_model=ResponseEnvelope[dict[str, str]],
    summary="Delete a routine owned by the user",
)
async def delete_my_routine(
    routine_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[dict[str, str]]:
    """Delete a routine while preserving historical completion snapshots."""
    service = RoutineService(db=db)
    await service.delete_routine(user=current_user, routine_id=routine_id)
    return ResponseEnvelope(
        data={
            "status": "deleted",
            "routine_id": str(routine_id),
        }
    )


@router.post(
    "/routines/{routine_id}/completions",
    response_model=ResponseEnvelope[RoutineCompletionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a routine completion with timezone-aware step snapshots",
)
async def record_routine_completion(
    routine_id: UUID,
    payload: RoutineCompletionCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[RoutineCompletionResponse]:
    """Record an immutable routine completion session in the user's configured timezone."""
    service = RoutineService(db=db)
    result = await service.record_completion(
        user=current_user,
        routine_id=routine_id,
        payload=payload,
    )
    return ResponseEnvelope(data=result)


@router.get(
    "/routines/{routine_id}/completions",
    response_model=ResponseEnvelope[RoutineCompletionListResponse],
    summary="List historical completions for a routine",
)
async def list_routine_completions(
    routine_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=50, description="Items per page")] = 20,
) -> ResponseEnvelope[RoutineCompletionListResponse]:
    """Retrieve immutable completion logs for a routine owned by the user."""
    service = RoutineService(db=db)
    result = await service.list_completions(
        user=current_user,
        routine_id=routine_id,
        page=page,
        page_size=page_size,
    )
    return ResponseEnvelope(data=result)


# ==============================================================================
# 2. REMINDERS & NOTIFICATION DISPATCH ENDPOINTS
# ==============================================================================


@router.get(
    "/reminders",
    response_model=ResponseEnvelope[ReminderPreferenceResponse],
    summary="Get the user's reminder preferences and timezone configuration",
)
async def get_my_reminders(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    notification_provider: Annotated[
        BaseNotificationProvider,
        Depends(get_notification_provider),
    ],
) -> ResponseEnvelope[ReminderPreferenceResponse]:
    """Retrieve user reminder preferences, quiet hours, and active notification adapter."""
    service = ReminderService(db=db, notification_provider=notification_provider)
    result = await service.get_preferences(user=current_user)
    return ResponseEnvelope(data=result)


@router.put(
    "/reminders",
    response_model=ResponseEnvelope[ReminderPreferenceResponse],
    summary="Update the user's reminder preferences, opt-outs, quiet hours, and timezone",
)
async def update_my_reminders(
    payload: ReminderPreferenceUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    notification_provider: Annotated[
        BaseNotificationProvider,
        Depends(get_notification_provider),
    ],
) -> ResponseEnvelope[ReminderPreferenceResponse]:
    """Update reminder schedule, quiet hours, opt-out state, and timezone override."""
    service = ReminderService(db=db, notification_provider=notification_provider)
    result = await service.update_preferences(user=current_user, payload=payload)
    return ResponseEnvelope(data=result)


@router.post(
    "/reminders/dispatch",
    response_model=ResponseEnvelope[ReminderDeliveryResponse],
    summary="Evaluate and dispatch a routine reminder with idempotency and quiet-hour checks",
)
async def dispatch_my_reminder(
    payload: ReminderDispatchRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    notification_provider: Annotated[
        BaseNotificationProvider,
        Depends(get_notification_provider),
    ],
) -> ResponseEnvelope[ReminderDeliveryResponse]:
    """Evaluate opt-outs, quiet hours, timezone, and idempotency keys before dispatching."""
    service = ReminderService(db=db, notification_provider=notification_provider)
    result = await service.dispatch_reminder(user=current_user, payload=payload)
    return ResponseEnvelope(data=result)


# ==============================================================================
# 3. PRODUCT REACTIONS ENDPOINTS (SAFETY & ESCALATION AWARE)
# ==============================================================================


@router.post(
    "/product-reactions",
    response_model=ResponseEnvelope[SafetyAwareReactionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a user-reported product reaction with urgent-care safety evaluation",
)
async def create_my_product_reaction(
    payload: StandaloneReactionCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[SafetyAwareReactionResponse]:
    """Record a user-reported reaction observation and surface urgent-care guidance if severe."""
    service = ReactionService(db=db)
    result = await service.create_reaction(user=current_user, payload=payload)
    return ResponseEnvelope(data=result)


@router.get(
    "/product-reactions",
    response_model=ResponseEnvelope[ReactionListResponse],
    summary="List the user's reported product reactions",
)
async def list_my_product_reactions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    reaction_type: Annotated[
        ReactionType | None,
        Query(description="Optional filter by reaction type"),
    ] = None,
    severity: Annotated[
        ReactionSeverity | None,
        Query(description="Optional filter by reaction severity"),
    ] = None,
    user_product_id: Annotated[
        UUID | None,
        Query(description="Optional filter by shelf item ID"),
    ] = None,
    product_id: Annotated[
        UUID | None,
        Query(description="Optional filter by catalogue product ID"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=50, description="Items per page")] = 20,
) -> ResponseEnvelope[ReactionListResponse]:
    """Retrieve paginated user-reported product reactions with non-diagnostic disclaimers."""
    service = ReactionService(db=db)
    result = await service.list_reactions(
        user=current_user,
        reaction_type=reaction_type,
        severity=severity,
        user_product_id=user_product_id,
        product_id=product_id,
        page=page,
        page_size=page_size,
    )
    return ResponseEnvelope(data=result)
