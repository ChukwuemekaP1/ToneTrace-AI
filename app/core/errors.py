"""Centralized domain exceptions and exception handlers.

Ensures all errors return consistent JSON envelopes conforming to ErrorResponse,
and prevents leaking stack traces or internal secrets to clients in production.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception for all domain and operational errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "Resource not found", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class AuthenticationError(AppException):
    """Raised when user credentials or tokens are missing or invalid."""

    def __init__(self, message: str = "Authentication failed", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class PermissionDeniedError(AppException):
    """Raised when an authenticated user lacks authorization for an action."""

    def __init__(self, message: str = "Permission denied", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ValidationError(AppException):
    """Raised when input fails domain or business rule validation."""

    def __init__(self, message: str = "Validation failed", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class ConflictError(AppException):
    """Raised when an operation conflicts with existing state (e.g. duplicate resource)."""

    def __init__(self, message: str = "Resource conflict", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class DependencyError(AppException):
    """Raised when a downstream external service or dependency fails or is unavailable."""

    def __init__(
        self,
        message: str = "Service dependency unavailable",
        status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE,
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code="DEPENDENCY_ERROR",
            status_code=status_code,
            details=details,
        )


class RateLimitError(AppException):
    """Raised when request rate exceeds allowed threshold."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class ConfigurationError(AppException):
    """Raised when invalid or missing configuration prevents safe operation."""

    def __init__(self, message: str = "Invalid configuration", details: Any = None) -> None:
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


def _get_request_id(request: Request) -> str | None:
    """Retrieve the request ID from request state or context variable."""
    return getattr(request.state, "request_id", None) or request_id_ctx.get()


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    req_id = _get_request_id(request)
    logger.warning(
        f"Domain error [{exc.code}] at {request.method} {request.url.path}: {exc.message}",
        extra={"code": exc.code, "status_code": exc.status_code, "details": exc.details},
    )
    payload = ErrorResponse(
        error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            request_id=req_id,
            details=exc.details,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI / Pydantic schema validation errors."""
    req_id = _get_request_id(request)
    # Simplify error details for safe response
    simplified_errors = []
    for error in exc.errors():
        loc = " -> ".join(str(item) for item in error.get("loc", []))
        simplified_errors.append(
            {
                "field": loc,
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
        )

    logger.info(
        f"Validation failure at {request.method} {request.url.path}",
        extra={"validation_errors": simplified_errors},
    )

    payload = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="The request payload failed validation.",
            request_id=req_id,
            details=simplified_errors,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=payload.model_dump(),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard Starlette / FastAPI HTTPExceptions."""
    req_id = _get_request_id(request)
    code = f"HTTP_{exc.status_code}"
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "NOT_FOUND"
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "UNAUTHORIZED"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "FORBIDDEN"

    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=str(exc.detail),
            request_id=req_id,
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(),
        headers=exc.headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions.

    Logs full traceback internally, but strictly guarantees no stack traces
    or environment leak to client responses.
    """
    req_id = _get_request_id(request)
    logger.exception(
        f"Unhandled server error at {request.method} {request.url.path}: {exc}",
        exc_info=exc,
    )

    payload = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. Please contact support.",
            request_id=req_id,
            details=None,  # Never leak stack trace to client
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=payload.model_dump(),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on the FastAPI application."""
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore
