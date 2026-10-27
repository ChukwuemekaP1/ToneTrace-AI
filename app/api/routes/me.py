"""User profile, skin profile, sensitivities, and privacy consent endpoints."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user
from app.db.models import User
from app.db.session import get_db_session
from app.schemas.common import ResponseEnvelope
from app.schemas.consent import UserConsentResponse, UserConsentUpdateRequest
from app.schemas.profile import (
    MeSummaryResponse,
    SkinProfileResponse,
    SkinProfileUpdateRequest,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserSensitivityCreateRequest,
    UserSensitivityItem,
)
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/me", tags=["User Profile"])


@router.get(
    "",
    response_model=ResponseEnvelope[MeSummaryResponse],
    summary="Get current user aggregate profile and preferences",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[MeSummaryResponse]:
    """Retrieve full account details, profile, skin attributes, sensitivities, and preferences."""
    service = ProfileService(db)
    summary = await service.get_me_summary(current_user)
    return ResponseEnvelope(data=summary)


@router.patch(
    "",
    response_model=ResponseEnvelope[UserProfileResponse],
    summary="Update user display name or timezone",
)
async def update_my_profile(
    payload: UserProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[UserProfileResponse]:
    """Update profile metadata strictly scoped to the authenticated caller."""
    service = ProfileService(db)
    profile = await service.update_profile(current_user.id, payload)
    return ResponseEnvelope(data=UserProfileResponse.model_validate(profile))


@router.get(
    "/skin-profile",
    response_model=ResponseEnvelope[SkinProfileResponse],
    summary="Get self-reported skin profile attributes",
)
async def get_my_skin_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[SkinProfileResponse]:
    """Retrieve user-reported skin type, concerns, and goals."""
    service = ProfileService(db)
    skin_profile = await service.get_or_create_skin_profile(current_user.id)
    return ResponseEnvelope(data=SkinProfileResponse.model_validate(skin_profile))


@router.put(
    "/skin-profile",
    response_model=ResponseEnvelope[SkinProfileResponse],
    summary="Update or set skin profile attributes",
)
async def update_my_skin_profile(
    payload: SkinProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[SkinProfileResponse]:
    """Set or update self-reported skin type, concerns, and goals."""
    service = ProfileService(db)
    skin_profile = await service.update_skin_profile(current_user.id, payload)
    return ResponseEnvelope(data=SkinProfileResponse.model_validate(skin_profile))


@router.get(
    "/sensitivities",
    response_model=ResponseEnvelope[list[UserSensitivityItem]],
    summary="List reported ingredient sensitivities",
)
async def list_my_sensitivities(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[list[UserSensitivityItem]]:
    """List all cosmetic ingredient sensitivities reported by the caller."""
    service = ProfileService(db)
    sensitivities = await service.list_sensitivities(current_user.id)
    return ResponseEnvelope(data=[UserSensitivityItem.model_validate(s) for s in sensitivities])


@router.post(
    "/sensitivities",
    response_model=ResponseEnvelope[UserSensitivityItem],
    status_code=status.HTTP_201_CREATED,
    summary="Add an ingredient sensitivity to avoid",
)
async def add_my_sensitivity(
    payload: UserSensitivityCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[UserSensitivityItem]:
    """Add a new ingredient avoidance or sensitivity record."""
    service = ProfileService(db)
    sensitivity = await service.add_sensitivity(current_user.id, payload)
    return ResponseEnvelope(data=UserSensitivityItem.model_validate(sensitivity))


@router.delete(
    "/sensitivities/{sensitivity_id}",
    response_model=ResponseEnvelope[dict[str, str]],
    summary="Remove an ingredient sensitivity",
)
async def delete_my_sensitivity(
    sensitivity_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[dict[str, str]]:
    """Remove a sensitivity record belonging to the authenticated user."""
    service = ProfileService(db)
    await service.delete_sensitivity(current_user.id, sensitivity_id)
    return ResponseEnvelope(data={"message": "Sensitivity record removed successfully."})


@router.get(
    "/consents",
    response_model=ResponseEnvelope[list[UserConsentResponse]],
    summary="List all privacy and data processing consents",
)
async def list_my_consents(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[list[UserConsentResponse]]:
    """List all explicit consent records recorded for this user."""
    service = ProfileService(db)
    consents = await service.list_consents(current_user.id)
    return ResponseEnvelope(data=[UserConsentResponse.model_validate(c) for c in consents])


@router.put(
    "/consents/{purpose}",
    response_model=ResponseEnvelope[UserConsentResponse],
    summary="Record or update consent for a specific purpose",
)
async def update_my_consent(
    purpose: str,
    payload: UserConsentUpdateRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[UserConsentResponse]:
    """Record grant or revocation of consent with verifiable audit metadata."""
    audit_metadata: dict[str, Any] = {
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    service = ProfileService(db)
    consent = await service.upsert_consent(
        user_id=current_user.id,
        purpose=purpose,
        payload=payload,
        audit_metadata=audit_metadata,
    )
    return ResponseEnvelope(data=UserConsentResponse.model_validate(consent))
