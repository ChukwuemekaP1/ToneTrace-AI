"""Authentication domain service implementing registration, login, rotation, and logout."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, ValidationError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import SkinProfile, User, UserPreference, UserProfile, UserSession
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.services.base import BaseService


class AuthService(BaseService):
    """First-party authentication and session management service."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db=db)
        self.settings = get_settings()

    async def register_user(self, payload: UserRegisterRequest) -> tuple[User, TokenResponse]:
        """Register a new user, initialize their profile, and issue an initial auth session."""
        normalized_email = payload.email.strip().lower()

        # Enforce minimum password length rule
        if len(payload.password) < self.settings.PASSWORD_MIN_LENGTH:
            raise ValidationError(
                f"Password must be at least {self.settings.PASSWORD_MIN_LENGTH} characters long."
            )

        # Check for existing email registration
        stmt = select(User).where(User.email == normalized_email)
        existing_user = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing_user is not None:
            raise ConflictError("An account with this email address already exists.")

        # Hash password using Argon2id
        hashed_password = hash_password(payload.password)

        new_user = User(
            email=normalized_email,
            password_hash=hashed_password,
            account_status="active",
            is_email_verified=False,
        )
        self.db.add(new_user)
        await self.db.flush()

        # Initialize default user profile
        profile = UserProfile(
            user_id=new_user.id,
            display_name=payload.display_name.strip(),
            timezone="UTC",
        )
        self.db.add(profile)

        # Initialize blank skin profile
        skin_profile = SkinProfile(
            user_id=new_user.id,
            skin_type=None,
            skin_concerns=[],
            skin_goals=[],
        )
        self.db.add(skin_profile)

        # Initialize default user preferences
        preferences = UserPreference(
            user_id=new_user.id,
            product_preferences={},
            routine_preferences={},
            notification_preferences={},
        )
        self.db.add(preferences)

        # Create session and rotating refresh token
        tokens = await self._create_user_session(
            user_id=new_user.id,
            device_label="Initial Registration",
        )

        await self.db.commit()
        await self.db.refresh(new_user)
        self.logger.info(f"User registered successfully: {new_user.id}")
        return new_user, tokens

    async def authenticate_user(self, payload: UserLoginRequest) -> tuple[User, TokenResponse]:
        """Authenticate user credentials and issue an active session."""
        normalized_email = payload.email.strip().lower()

        stmt = select(User).where(User.email == normalized_email)
        user = (await self.db.execute(stmt)).scalar_one_or_none()

        # Constant-time comparison resistance: verify dummy hash if user not found
        if user is None:
            dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy"
            verify_password("invalid_password", dummy_hash)
            raise AuthenticationError("Invalid email or password.")

        if not verify_password(payload.password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")

        if user.account_status != "active":
            raise AuthenticationError("Account is inactive or suspended.")

        tokens = await self._create_user_session(
            user_id=user.id,
            device_label=payload.device_label,
        )

        await self.db.commit()
        self.logger.info(f"User logged in successfully: {user.id}")
        return user, tokens

    async def refresh_session(self, payload: RefreshTokenRequest) -> TokenResponse:
        """Exchange a valid refresh token for a new access token and rotated refresh token."""
        hashed = hash_token(payload.refresh_token)

        stmt = select(UserSession).where(UserSession.hashed_refresh_token == hashed)
        session = (await self.db.execute(stmt)).scalar_one_or_none()

        if session is None:
            raise AuthenticationError("Invalid or unknown refresh token.")

        # Replay Attack Detection: If token is already revoked, revoke all sessions for this user
        if session.revoked_at is not None:
            self.logger.warning(
                f"Revoked refresh token reuse detected for user {session.user_id}! "
                "Revoking all sessions."
            )
            revoke_all_stmt = (
                update(UserSession)
                .where(
                    UserSession.user_id == session.user_id,
                    UserSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
            await self.db.execute(revoke_all_stmt)
            await self.db.commit()
            raise AuthenticationError(
                "Revoked refresh token reuse detected. All sessions terminated for security."
            )

        # Check expiration
        now = datetime.now(UTC)
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at <= now:
            session.revoked_at = now
            await self.db.commit()
            raise AuthenticationError("Refresh token has expired. Please log in again.")

        # Confirm owning user is still active
        user = await self.db.get(User, session.user_id)
        if user is None or user.account_status != "active":
            raise AuthenticationError("User account is inactive or not found.")

        # Revoke the consumed refresh token (Rotation)
        session.revoked_at = now

        # Issue newly rotated session
        device_label = payload.device_label or session.device_label
        tokens = await self._create_user_session(
            user_id=user.id,
            device_label=device_label,
        )

        await self.db.commit()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        """Revoke a single refresh token session."""
        hashed = hash_token(refresh_token)
        stmt = select(UserSession).where(UserSession.hashed_refresh_token == hashed)
        session = (await self.db.execute(stmt)).scalar_one_or_none()

        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)
            await self.db.commit()
            self.logger.info(f"Session {session.id} revoked for user {session.user_id}.")

    async def logout_all(self, user_id: uuid.UUID) -> int:
        """Revoke all active sessions for a user."""
        stmt = (
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        self.logger.info(f"Revoked all ({result.rowcount}) active sessions for user {user_id}.")
        return result.rowcount or 0

    async def _create_user_session(
        self,
        user_id: uuid.UUID,
        device_label: str | None = None,
    ) -> TokenResponse:
        """Internal helper to mint an access token and record a hashed refresh token session."""
        raw_refresh_token = generate_refresh_token()
        hashed_refresh = hash_token(raw_refresh_token)

        expires_at = datetime.now(UTC) + timedelta(days=self.settings.REFRESH_TOKEN_TTL_DAYS)

        new_session = UserSession(
            user_id=user_id,
            hashed_refresh_token=hashed_refresh,
            device_label=device_label,
            expires_at=expires_at,
        )
        self.db.add(new_session)

        access_token = create_access_token(user_id=user_id)
        expires_in = self.settings.ACCESS_TOKEN_TTL_MINUTES * 60

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="Bearer",
            expires_in=expires_in,
        )
