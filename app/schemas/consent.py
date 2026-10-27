"""User consent tracking and audit schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserConsentResponse(BaseModel):
    """User consent record representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    purpose: str
    policy_version: str
    is_granted: bool
    granted_at: datetime | None = None
    revoked_at: datetime | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class UserConsentUpdateRequest(BaseModel):
    """Payload to grant or revoke consent for a given purpose."""

    policy_version: str = Field(min_length=1, max_length=20, default="1.0")
    is_granted: bool = Field(description="True to grant, False to revoke consent")
