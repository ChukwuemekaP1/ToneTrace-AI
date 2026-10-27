"""Common reusable response envelope and pagination schemas."""

from pydantic import BaseModel, Field


class ResponseMeta(BaseModel):
    """Metadata attached to standard API envelopes."""

    request_id: str | None = Field(
        default=None, description="Unique correlation ID for tracing the request."
    )
    timestamp: str | None = Field(default=None, description="ISO timestamp of response generation.")


class ResponseEnvelope[DataT](BaseModel):
    """Standardized top-level response envelope for consistent API payload structuring."""

    status: str = Field(default="success", description="Status indicator: 'success' or 'error'.")
    data: DataT = Field(description="The primary response payload.")
    meta: ResponseMeta | None = Field(default=None, description="Optional response metadata.")


class PaginationMeta(BaseModel):
    """Pagination cursor or offset metadata."""

    page: int = Field(ge=1, description="Current page index.")
    page_size: int = Field(ge=1, le=100, description="Number of items per page.")
    total_items: int = Field(ge=0, description="Total matching items across all pages.")
    total_pages: int = Field(ge=0, description="Total number of available pages.")
