"""Security primitives, authentication guards, and identity boundaries.

Enforces zero-trust principles:
1. Passwords hashed using Argon2id via pwdlib.
2. Signed JWT access tokens validated against issuer and audience.
3. Refresh tokens stored strictly as SHA-256 hashes.
4. Client-supplied IDs are never trusted as identity in production.
"""

import asyncio
import hashlib
import secrets
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, Request
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import EnvironmentType, Settings, get_settings
from app.core.errors import AuthenticationError, RateLimitError
from app.db.models import User
from app.db.session import get_db_session

# Production-grade Argon2id hasher instance
_password_hasher = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash in constant time."""
    return _password_hasher.verify(plain_password, hashed_password)


def generate_refresh_token() -> str:
    """Generate a high-entropy cryptographically secure URL-safe refresh token string."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Compute the SHA-256 hex digest of a token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: uuid.UUID | str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token with standardized claims."""
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    expire = now + ttl

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iss": settings.AUTH_JWT_ISSUER,
        "aud": settings.AUTH_JWT_AUDIENCE,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(
        payload,
        settings.AUTH_JWT_SECRET.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Validates signature, expiration, issuer, and audience.
    """
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.AUTH_JWT_SECRET.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.AUTH_JWT_ISSUER,
            audience=settings.AUTH_JWT_AUDIENCE,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid access token.") from exc


class InMemoryRateLimiter:
    """Sliding-window rate limiter for sensitive authentication endpoints."""

    def __init__(self, requests_per_minute: int = 30) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60.0
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, key: str, enabled: bool = True) -> None:
        """Record and enforce request limits per client key."""
        if not enabled:
            return

        now = time.monotonic()
        async with self._lock:
            cutoff = now - self.window_seconds
            timestamps = [t for t in self._history[key] if t > cutoff]
            if len(timestamps) >= self.requests_per_minute:
                raise RateLimitError(
                    message="Too many requests. Please slow down and try again in a minute."
                )
            timestamps.append(now)
            self._history[key] = timestamps

    def reset(self) -> None:
        """Clear rate limit history (primarily for tests)."""
        self._history.clear()


auth_rate_limiter = InMemoryRateLimiter(requests_per_minute=20)
ingest_rate_limiter = InMemoryRateLimiter(requests_per_minute=15)


async def rate_limit_auth(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """FastAPI dependency for rate limiting sensitive authentication requests."""
    client_ip = request.client.host if request.client else "unknown"
    await auth_rate_limiter.check_rate_limit(client_ip, enabled=settings.AUTH_RATE_LIMIT_ENABLED)


async def rate_limit_ingest(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """FastAPI dependency for rate limiting external catalog ingestion requests."""
    client_ip = request.client.host if request.client else "unknown"
    await ingest_rate_limiter.check_rate_limit(client_ip, enabled=settings.AUTH_RATE_LIMIT_ENABLED)


async def get_current_user(
    authorization: Annotated[str | None, Header(description="Bearer JWT token")] = None,
    x_user_id: Annotated[
        str | None, Header(description="Development bypass header (Dev/Test ONLY)")
    ] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> User:
    """Authenticate and retrieve the caller's user record.

    Zero-trust rules:
    1. If environment is production/staging, client-supplied bypass headers are strictly rejected.
    2. Bearer access token signature, audience, and expiration are strictly verified.
    3. The user record is retrieved from the database to confirm existence and active state.
    """
    if settings is None:
        settings = get_settings()

    is_dev_env = settings.ENVIRONMENT in (
        EnvironmentType.DEVELOPMENT,
        EnvironmentType.TEST,
    )

    # 1. Dev bypass path (explicitly restricted to development/test environments)
    if x_user_id is not None:
        if not is_dev_env or not settings.ALLOW_DEV_AUTH_BYPASS:
            raise AuthenticationError(
                "Client-supplied user ID headers (e.g. X-User-ID) are strictly forbidden "
                "in this environment."
            )
        try:
            user_uuid = uuid.UUID(x_user_id)
        except ValueError as exc:
            raise AuthenticationError("Invalid UUID format in dev bypass header.") from exc

        user = await db.get(User, user_uuid)
        if not user:
            raise AuthenticationError("Dev bypass user not found in database.")
        return user

    # 2. Standard token path
    if authorization is None:
        raise AuthenticationError("Authorization header is missing.")

    if not authorization.startswith("Bearer "):
        raise AuthenticationError("Invalid authorization header scheme. Must use 'Bearer <token>'.")

    token = authorization[7:].strip()
    if not token:
        raise AuthenticationError("Empty Bearer token provided.")

    # In development/test with bypass allowed, support synthetic test tokens
    if is_dev_env and settings.ALLOW_DEV_AUTH_BYPASS and token.startswith("dev-token-"):
        try:
            user_uuid = uuid.UUID(token.replace("dev-token-", ""))
            user = await db.get(User, user_uuid)
            if user:
                return user
        except ValueError:
            pass

    payload = decode_access_token(token)
    sub = payload.get("sub")
    if not sub:
        raise AuthenticationError("Token payload missing subject identifier.")

    try:
        user_uuid = uuid.UUID(sub)
    except ValueError as exc:
        raise AuthenticationError("Subject in token is not a valid UUID.") from exc

    user = await db.get(User, user_uuid)
    if user is None:
        raise AuthenticationError("User associated with this token no longer exists.")

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the authenticated user account is in 'active' status."""
    if current_user.account_status != "active":
        raise AuthenticationError("User account is inactive or suspended.")
    return current_user
