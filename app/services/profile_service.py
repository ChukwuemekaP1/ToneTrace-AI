"""Domain service managing user profiles, skin attributes, sensitivities, and consents."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    SkinProfile,
    User,
    UserConsent,
    UserPreference,
    UserProfile,
    UserSensitivity,
)
from app.schemas.auth import UserResponse
from app.schemas.consent import UserConsentUpdateRequest
from app.schemas.profile import (
    MeSummaryResponse,
    SkinProfileResponse,
    SkinProfileUpdateRequest,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserSensitivityCreateRequest,
    UserSensitivityItem,
)
from app.services.base import BaseService


class ProfileService(BaseService):
    """User profile, skin attributes, and consent lifecycle manager."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db=db)

    async def get_me_summary(self, user: User) -> MeSummaryResponse:
        """Fetch full aggregate profile details for the authenticated user."""
        profile = (
            await self.db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        ).scalar_one_or_none()
        skin_profile = (
            await self.db.execute(select(SkinProfile).where(SkinProfile.user_id == user.id))
        ).scalar_one_or_none()
        sensitivities = (
            (
                await self.db.execute(
                    select(UserSensitivity)
                    .where(UserSensitivity.user_id == user.id)
                    .order_by(UserSensitivity.ingredient_name)
                )
            )
            .scalars()
            .all()
        )
        preferences = (
            await self.db.execute(select(UserPreference).where(UserPreference.user_id == user.id))
        ).scalar_one_or_none()

        return MeSummaryResponse(
            user=UserResponse.model_validate(user),
            profile=UserProfileResponse.model_validate(profile) if profile else None,
            skin_profile=SkinProfileResponse.model_validate(skin_profile) if skin_profile else None,
            sensitivities=[UserSensitivityItem.model_validate(s) for s in sensitivities],
            preferences=preferences,  # type: ignore
        )

    async def update_profile(
        self, user_id: uuid.UUID, payload: UserProfileUpdateRequest
    ) -> UserProfile:
        """Partially update user profile attributes."""
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        profile = (await self.db.execute(stmt)).scalar_one_or_none()

        if profile is None:
            profile = UserProfile(
                user_id=user_id,
                display_name=payload.display_name or "User",
                timezone=payload.timezone or "UTC",
            )
            self.db.add(profile)
        else:
            if payload.display_name is not None:
                profile.display_name = payload.display_name.strip()
            if payload.timezone is not None:
                profile.timezone = payload.timezone.strip()

        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def get_or_create_skin_profile(self, user_id: uuid.UUID) -> SkinProfile:
        """Retrieve existing skin profile or create a default blank one."""
        stmt = select(SkinProfile).where(SkinProfile.user_id == user_id)
        skin_profile = (await self.db.execute(stmt)).scalar_one_or_none()

        if skin_profile is None:
            skin_profile = SkinProfile(
                user_id=user_id,
                skin_type=None,
                skin_concerns=[],
                skin_goals=[],
            )
            self.db.add(skin_profile)
            await self.db.commit()
            await self.db.refresh(skin_profile)

        return skin_profile

    async def update_skin_profile(
        self, user_id: uuid.UUID, payload: SkinProfileUpdateRequest
    ) -> SkinProfile:
        """Update or replace skin attributes, concerns, and goals."""
        skin_profile = await self.get_or_create_skin_profile(user_id)

        if payload.skin_type is not None:
            skin_profile.skin_type = payload.skin_type.strip().lower()
        if payload.skin_concerns is not None:
            skin_profile.skin_concerns = [c.strip().lower() for c in payload.skin_concerns]
        if payload.skin_goals is not None:
            skin_profile.skin_goals = [g.strip().lower() for g in payload.skin_goals]

        await self.db.commit()
        await self.db.refresh(skin_profile)
        return skin_profile

    async def list_sensitivities(self, user_id: uuid.UUID) -> list[UserSensitivity]:
        """List all reported sensitivities for a user."""
        stmt = (
            select(UserSensitivity)
            .where(UserSensitivity.user_id == user_id)
            .order_by(UserSensitivity.ingredient_name)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def add_sensitivity(
        self, user_id: uuid.UUID, payload: UserSensitivityCreateRequest
    ) -> UserSensitivity:
        """Record a new cosmetic ingredient sensitivity."""
        normalized_name = payload.ingredient_name.strip().lower()

        stmt = select(UserSensitivity).where(
            UserSensitivity.user_id == user_id,
            UserSensitivity.ingredient_name == normalized_name,
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Sensitivity for '{normalized_name}' already exists.")

        sensitivity = UserSensitivity(
            user_id=user_id,
            ingredient_name=normalized_name,
            severity=payload.severity,
            notes=payload.notes.strip() if payload.notes else None,
        )
        self.db.add(sensitivity)
        await self.db.commit()
        await self.db.refresh(sensitivity)
        return sensitivity

    async def delete_sensitivity(self, user_id: uuid.UUID, sensitivity_id: uuid.UUID) -> None:
        """Remove an ingredient sensitivity strictly scoped to the owning user."""
        stmt = select(UserSensitivity).where(
            UserSensitivity.id == sensitivity_id,
            UserSensitivity.user_id == user_id,
        )
        record = (await self.db.execute(stmt)).scalar_one_or_none()
        if record is None:
            raise NotFoundError("Sensitivity record not found or access denied.")

        await self.db.delete(record)
        await self.db.commit()

    async def list_consents(self, user_id: uuid.UUID) -> list[UserConsent]:
        """List all consent records for a user."""
        stmt = (
            select(UserConsent).where(UserConsent.user_id == user_id).order_by(UserConsent.purpose)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def upsert_consent(
        self,
        user_id: uuid.UUID,
        purpose: str,
        payload: UserConsentUpdateRequest,
        audit_metadata: dict[str, Any],
    ) -> UserConsent:
        """Record or update user consent for a specific processing purpose."""
        normalized_purpose = purpose.strip().lower()
        now = datetime.now(UTC)

        stmt = select(UserConsent).where(
            UserConsent.user_id == user_id,
            UserConsent.purpose == normalized_purpose,
        )
        consent = (await self.db.execute(stmt)).scalar_one_or_none()

        if consent is None:
            consent = UserConsent(
                user_id=user_id,
                purpose=normalized_purpose,
                policy_version=payload.policy_version,
                is_granted=payload.is_granted,
                granted_at=now if payload.is_granted else None,
                revoked_at=None if payload.is_granted else now,
                audit_metadata=audit_metadata,
            )
            self.db.add(consent)
        else:
            consent.policy_version = payload.policy_version
            consent.is_granted = payload.is_granted
            if payload.is_granted:
                consent.granted_at = now
                consent.revoked_at = None
            else:
                consent.revoked_at = now
            consent.audit_metadata = audit_metadata

        await self.db.commit()
        await self.db.refresh(consent)
        return consent
