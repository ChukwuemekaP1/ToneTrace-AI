"""First-party authentication endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user, rate_limit_auth
from app.db.models import User
from app.db.session import get_db_session
from app.schemas.auth import (
    AuthSuccessResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.common import ResponseEnvelope
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=ResponseEnvelope[AuthSuccessResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
    summary="Register a new user account",
)
async def register(
    payload: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[AuthSuccessResponse]:
    """Register a new user with Argon2id password hashing and return an authenticated session."""
    service = AuthService(db)
    user, tokens = await service.register_user(payload)
    return ResponseEnvelope(
        data=AuthSuccessResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        )
    )


@router.post(
    "/login",
    response_model=ResponseEnvelope[AuthSuccessResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth)],
    summary="Authenticate with email and password",
)
async def login(
    payload: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[AuthSuccessResponse]:
    """Validate credentials and return a signed JWT access token and rotating refresh token."""
    service = AuthService(db)
    user, tokens = await service.authenticate_user(payload)
    return ResponseEnvelope(
        data=AuthSuccessResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        )
    )


@router.post(
    "/refresh",
    response_model=ResponseEnvelope[TokenResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_auth)],
    summary="Rotate refresh token and obtain new access token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[TokenResponse]:
    """Rotate an unrevoked refresh token.

    Detects replay attacks to revoke sessions if compromised.
    """
    service = AuthService(db)
    tokens = await service.refresh_session(payload)
    return ResponseEnvelope(data=tokens)


@router.post(
    "/logout",
    response_model=ResponseEnvelope[dict[str, str]],
    status_code=status.HTTP_200_OK,
    summary="Revoke an active refresh token session",
)
async def logout(
    payload: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[dict[str, str]]:
    """Revoke a single refresh token session."""
    service = AuthService(db)
    await service.logout(payload.refresh_token)
    return ResponseEnvelope(data={"message": "Logged out successfully."})


@router.post(
    "/logout-all",
    response_model=ResponseEnvelope[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Revoke all active sessions for the current user",
)
async def logout_all(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[dict[str, Any]]:
    """Revoke all active refresh sessions belonging to the authenticated caller."""
    service = AuthService(db)
    count = await service.logout_all(current_user.id)
    return ResponseEnvelope(
        data={
            "message": "All sessions terminated successfully.",
            "sessions_revoked": count,
        }
    )
