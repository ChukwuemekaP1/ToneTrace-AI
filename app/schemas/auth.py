"""Authentication schemas for request validation and response serialization."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Payload for user self-registration."""

    email: EmailStr = Field(description="User email address")
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Plaintext password meeting minimum length requirement",
    )
    display_name: str = Field(
        min_length=1,
        max_length=100,
        description="Public display name for profile creation",
    )


class UserLoginRequest(BaseModel):
    """Payload for credentials login."""

    email: EmailStr = Field(description="Registered email address")
    password: str = Field(min_length=1, max_length=128, description="User password")
    device_label: str | None = Field(
        default=None,
        max_length=200,
        description="Optional client description or device name",
    )


class RefreshTokenRequest(BaseModel):
    """Payload for rotating refresh token exchange."""

    refresh_token: str = Field(min_length=10, max_length=255, description="Active refresh token")
    device_label: str | None = Field(
        default=None,
        max_length=200,
        description="Optional client device label",
    )


class TokenResponse(BaseModel):
    """Tokens returned upon successful authentication or rotation."""

    access_token: str = Field(description="Short-lived signed JWT access token")
    refresh_token: str = Field(description="Single-use rotating refresh token string")
    token_type: str = Field(default="Bearer", description="HTTP authorization scheme")
    expires_in: int = Field(description="Access token lifespan in seconds")


class UserResponse(BaseModel):
    """Safe public representation of a user entity (never leaks password or tokens)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    account_status: str
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime


class AuthSuccessResponse(BaseModel):
    """Combined response returning user profile summary alongside auth tokens."""

    user: UserResponse
    tokens: TokenResponse
