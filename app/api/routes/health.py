"""Health check and operational probe endpoints.

Implements standard Kubernetes and container health probe conventions:
- /health/live: Liveness probe (process vitality)
- /health/ready: Readiness probe (traffic readiness, required vs optional checks)
- /health/integrations: Safe diagnostic audit of all third-party integrations
"""

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.config import Settings, get_settings
from app.db.session import check_db_health
from app.providers.base import evaluate_integration_status
from app.providers.search_provider import get_search_provider
from app.schemas.health import (
    DependencyStatus,
    IntegrationStatusResponse,
    LivenessResponse,
    ReadinessResponse,
)

router = APIRouter(tags=["Health & Diagnostics"])

# Record start time for uptime calculation
START_TIME = time.time()


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
    summary="Process Liveness Probe",
    description=(
        "Confirms that the FastAPI process is responsive. Does not probe external dependencies."
    ),
)
async def liveness_probe(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    """Fast liveness check for process supervisors and orchestrators."""
    uptime = time.time() - START_TIME
    return LivenessResponse(
        status="ok",
        version=settings.VERSION,
        timestamp=datetime.now(UTC).isoformat(),
        uptime_seconds=round(uptime, 2),
    )


async def _probe_elasticsearch(settings: Settings) -> DependencyStatus:
    """Probe Elasticsearch instance with credentials and latency tracking."""
    if not settings.ELASTICSEARCH_ENABLED:
        return DependencyStatus(
            name="elasticsearch",
            status="disabled",
            required=False,
            latency_ms=None,
            details="Elasticsearch integration is currently disabled in configuration.",
        )

    if not settings.ELASTICSEARCH_URL:
        return DependencyStatus(
            name="elasticsearch",
            status="unconfigured",
            required=False,
            latency_ms=None,
            details="Elasticsearch URL is unconfigured.",
        )

    provider = get_search_provider()
    is_healthy, summary_msg, latency = provider.check_health()
    return DependencyStatus(
        name="elasticsearch",
        status="healthy" if is_healthy else "unhealthy",
        required=False,
        latency_ms=latency,
        details=summary_msg,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={
        200: {"description": "Service is ready to accept traffic."},
        503: {"description": "Required service dependency is unhealthy."},
    },
    summary="Service Readiness Probe",
    description=(
        "Evaluates critical runtime dependencies. Required failures return 503; "
        "optional failures report degraded without blocking traffic."
    ),
)
async def readiness_probe(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    """Readiness check that differentiates required from optional dependencies."""
    dependencies: dict[str, DependencyStatus] = {}

    # 1. Required Dependency: Database (Neon PostgreSQL)
    db_healthy, db_latency, db_error = await check_db_health(settings)
    dependencies["database"] = DependencyStatus(
        name="database",
        status="healthy" if db_healthy else "unhealthy",
        required=True,
        latency_ms=db_latency,
        details=db_error if not db_healthy else "Connected to relational datastore.",
    )

    # 2. Optional Dependency: Elasticsearch
    es_status = await _probe_elasticsearch(settings)
    dependencies["elasticsearch"] = es_status

    # Evaluate Overall Status
    # If ANY required dependency is unhealthy, service is NOT READY -> 503
    has_required_failure = any(
        dep.required and dep.status != "healthy" for dep in dependencies.values()
    )
    has_optional_issue = any(
        not dep.required and dep.status not in ("healthy", "disabled")
        for dep in dependencies.values()
    )

    if has_required_failure:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "not_ready"
    elif has_optional_issue:
        response.status_code = status.HTTP_200_OK
        overall_status = "degraded"
    else:
        response.status_code = status.HTTP_200_OK
        overall_status = "ready"

    return ReadinessResponse(
        status=overall_status,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT.value,
        timestamp=datetime.now(UTC).isoformat(),
        dependencies=dependencies,
    )


@router.get(
    "/health/integrations",
    response_model=IntegrationStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Safe Integration Status",
    description=(
        "Reports the configured state of all planned platform integrations "
        "with zero secret leakage."
    ),
)
async def integrations_status(
    settings: Annotated[Settings, Depends(get_settings)],
) -> IntegrationStatusResponse:
    """Audits integration configuration states without leaking sensitive secrets or tokens."""
    status_map = evaluate_integration_status(settings)
    return IntegrationStatusResponse(
        status="ok",
        environment=settings.ENVIRONMENT.value,
        timestamp=datetime.now(UTC).isoformat(),
        integrations=status_map,
    )
