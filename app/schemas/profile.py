"""User profile, skin profile, sensitivities, and preferences schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import UserResponse


class UserProfileResponse(BaseModel):
    """User profile attributes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    timezone: str
    created_at: datetime
    updated_at: datetime


class UserProfileUpdateRequest(BaseModel):
    """Partial update payload for user profile."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str | None = Field(default=None, min_length=1, max_length=50)


class SkinProfileResponse(BaseModel):
    """Skin attributes, concerns, and goals."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    skin_type: str | None = None
    skin_concerns: list[str] = Field(default_factory=list)
    skin_goals: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SkinProfileUpdateRequest(BaseModel):
    """Update payload for skin profile."""

    skin_type: str | None = Field(
        default=None,
        description="dry, oily, combination, normal, or sensitive",
    )
    skin_concerns: list[str] | None = Field(default=None, description="Reported skin concerns")
    skin_goals: list[str] | None = Field(default=None, description="Skincare goals")


class UserSensitivityItem(BaseModel):
    """Ingredient sensitivity record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    ingredient_name: str
    severity: str
    notes: str | None = None
    created_at: datetime


class UserSensitivityCreateRequest(BaseModel):
    """Payload to add a cosmetic ingredient sensitivity."""

    ingredient_name: str = Field(min_length=1, max_length=150)
    severity: str = Field(default="moderate", pattern="^(low|moderate|high|severe)$")
    notes: str | None = Field(default=None, max_length=255)


class UserPreferencesResponse(BaseModel):
    """User product, routine, and notification preferences."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    product_preferences: dict[str, Any] = Field(default_factory=dict)
    routine_preferences: dict[str, Any] = Field(default_factory=dict)
    notification_preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class UserPreferencesUpdateRequest(BaseModel):
    """Update payload for preferences."""

    product_preferences: dict[str, Any] | None = None
    routine_preferences: dict[str, Any] | None = None
    notification_preferences: dict[str, Any] | None = None


class MeSummaryResponse(BaseModel):
    """Aggregate profile response for the authenticated user."""

    user: UserResponse
    profile: UserProfileResponse | None = None
    skin_profile: SkinProfileResponse | None = None
    sensitivities: list[UserSensitivityItem] = Field(default_factory=list)
    preferences: UserPreferencesResponse | None = None
