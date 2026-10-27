"""Standardized error response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error object returned within standard error envelopes."""

    code: str = Field(
        ...,
        description="Machine-readable error code (e.g. NOT_FOUND, VALIDATION_ERROR).",
    )
    message: str = Field(
        ...,
        description="Human-readable description of the error.",
    )
    request_id: str | None = Field(
        default=None,
        description="Correlation ID associated with the failing request.",
    )
    details: Any = Field(
        default=None,
        description="Contextual details or validation breakdown, if applicable.",
    )


class ErrorResponse(BaseModel):
    """Unified error envelope returned by all HTTP exception handlers."""

    error: ErrorDetail
