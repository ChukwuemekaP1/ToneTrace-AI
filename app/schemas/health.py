"""Health and dependency status response schemas."""

from pydantic import BaseModel, Field

from app.core.config import IntegrationState


class LivenessResponse(BaseModel):
    """Payload for fast liveness probe."""

    status: str = Field(default="ok", description="Process health status.")
    version: str = Field(description="Application version.")
    timestamp: str = Field(description="ISO UTC timestamp.")
    uptime_seconds: float = Field(description="Application uptime in seconds.")


class DependencyStatus(BaseModel):
    """Status assessment for an individual dependency."""

    name: str = Field(description="Dependency identifier.")
    status: str = Field(
        description="Health condition: healthy, unhealthy, degraded, unconfigured, or disabled."
    )
    required: bool = Field(
        description="Whether this dependency is strictly required for application readiness."
    )
    latency_ms: float | None = Field(
        default=None, description="Roundtrip check latency in milliseconds."
    )
    details: str | None = Field(
        default=None, description="Sanitized diagnostic message, if applicable."
    )


class ReadinessResponse(BaseModel):
    """Payload for readiness probe, assessing runtime traffic suitability."""

    status: str = Field(description="Overall readiness: 'ready', 'degraded', or 'not_ready'.")
    version: str = Field(description="Application version.")
    environment: str = Field(description="Deployment environment name.")
    timestamp: str = Field(description="ISO UTC timestamp.")
    dependencies: dict[str, DependencyStatus] = Field(
        description="Map of dependency names to their individual readiness status."
    )


class IntegrationItem(BaseModel):
    """Safe status descriptor for an integration."""

    state: IntegrationState = Field(
        description="Configured, unconfigured, disabled, or unavailable."
    )
    provider: str | None = Field(
        default=None, description="Designated provider or backend system name."
    )
    description: str | None = Field(
        default=None, description="Sanitized capability or context summary."
    )


class IntegrationStatusResponse(BaseModel):
    """Safe integration status report, guaranteed not to leak secrets or keys."""

    status: str = Field(default="ok", description="Integration audit status.")
    environment: str = Field(description="Current deployment environment.")
    timestamp: str = Field(description="ISO UTC timestamp.")
    integrations: dict[str, IntegrationItem] = Field(
        description="Map of planned and configured integrations."
    )
