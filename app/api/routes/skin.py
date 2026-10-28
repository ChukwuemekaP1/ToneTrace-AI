"""Skin Analysis and Longitudinal Skin Story API routes (Phase 8)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user, rate_limit_heavy_scan
from app.db.models import User
from app.db.session import get_db_session
from app.providers.skin_analysis import BaseSkinAnalysisProvider, get_skin_analysis_provider
from app.schemas.common import ResponseEnvelope
from app.schemas.skin import (
    CaptureConditionsInput,
    CreateSkinJournalEntryRequest,
    SkinJournalEntryResponse,
    SkinJournalListResponse,
    SkinScanDeleteResponse,
    SkinScanListResponse,
    SkinScanResponse,
    SkinStoryResponse,
)
from app.services.skin_service import SkinService

router = APIRouter(prefix="/skin", tags=["Skin Analysis & Skin Story"])


@router.post(
    "/scans",
    response_model=ResponseEnvelope[SkinScanResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_heavy_scan)],
    summary="Submit a facial photo for provider-backed skin analysis",
)
async def create_skin_scan(
    file: Annotated[UploadFile, File(description="Facial scan photo (JPEG, PNG, WebP)")],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
    idempotency_key: Annotated[
        str | None,
        Form(description="Optional idempotency key to prevent duplicate scans on retry"),
    ] = None,
    lighting_condition: Annotated[
        Literal[
            "natural_daylight",
            "indoor_warm",
            "indoor_cool",
            "ring_light",
            "dim_or_uneven",
            "unknown",
        ],
        Form(description="Self-reported ambient lighting condition"),
    ] = "unknown",
    camera_angle: Annotated[
        Literal["frontal", "slight_angle", "unknown"],
        Form(description="Self-reported camera orientation"),
    ] = "frontal",
    cosmetics_worn: Annotated[
        bool,
        Form(description="Whether makeup or tinted product was present during capture"),
    ] = False,
    capture_notes: Annotated[
        str | None,
        Form(max_length=300, description="Optional note on capture conditions"),
    ] = None,
    requested_metrics: Annotated[
        str | None,
        Form(
            description=(
                "Optional comma-separated normalized metric codes "
                "(e.g. 'spots,redness,texture,pores')"
            )
        ),
    ] = None,
) -> ResponseEnvelope[SkinScanResponse]:
    """Validate explicit consent, store photo privately, and execute or initiate skin analysis."""
    file_bytes = await file.read()
    conditions = CaptureConditionsInput(
        lighting_condition=lighting_condition,
        camera_angle=camera_angle,
        cosmetics_worn=cosmetics_worn,
        notes=capture_notes,
    )
    metrics_list: list[str] | None = None
    if requested_metrics and requested_metrics.strip():
        metrics_list = [m.strip().lower() for m in requested_metrics.split(",") if m.strip()]

    service = SkinService(db=db, skin_provider=skin_provider)
    scan_response = await service.create_and_process_scan(
        user=current_user,
        file_bytes=file_bytes,
        original_filename=file.filename,
        idempotency_key=idempotency_key,
        capture_conditions=conditions,
        requested_metrics=metrics_list,
    )
    return ResponseEnvelope(data=scan_response)


@router.get(
    "/scans",
    response_model=ResponseEnvelope[SkinScanListResponse],
    summary="List authenticated user's skin scans",
)
async def list_skin_scans(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    status_filter: Annotated[
        str | None,
        Query(alias="status", description="Optional status filter (processing, succeeded, failed)"),
    ] = None,
) -> ResponseEnvelope[SkinScanListResponse]:
    """Return paginated skin scans owned by the authenticated user."""
    service = SkinService(db=db, skin_provider=skin_provider)
    result = await service.list_scans(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
    )
    return ResponseEnvelope(data=result)


@router.get(
    "/scans/{scan_id}",
    response_model=ResponseEnvelope[SkinScanResponse],
    summary="Retrieve a specific skin scan and its normalized observations",
)
async def get_skin_scan(
    scan_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
    poll_if_processing: Annotated[
        bool,
        Query(description="If true and scan is in 'processing' status, poll external provider"),
    ] = False,
) -> ResponseEnvelope[SkinScanResponse]:
    """Fetch a user-owned skin scan by ID, optionally polling if still processing."""
    service = SkinService(db=db, skin_provider=skin_provider)
    if poll_if_processing:
        scan_response = await service.poll_scan(scan_id=scan_id, user_id=current_user.id)
    else:
        scan_response = await service.get_scan(scan_id=scan_id, user_id=current_user.id)
    return ResponseEnvelope(data=scan_response)


@router.post(
    "/scans/{scan_id}/poll",
    response_model=ResponseEnvelope[SkinScanResponse],
    summary="Poll external provider for an asynchronous skin scan task",
)
async def poll_skin_scan(
    scan_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
) -> ResponseEnvelope[SkinScanResponse]:
    """Explicitly poll the external skin analysis provider for a processing scan."""
    service = SkinService(db=db, skin_provider=skin_provider)
    scan_response = await service.poll_scan(scan_id=scan_id, user_id=current_user.id)
    return ResponseEnvelope(data=scan_response)


@router.delete(
    "/scans/{scan_id}",
    response_model=ResponseEnvelope[SkinScanDeleteResponse],
    summary="Delete a skin scan and purge its private stored media",
)
async def delete_skin_scan(
    scan_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
) -> ResponseEnvelope[SkinScanDeleteResponse]:
    """Delete a user-owned skin scan, its observations, and its private object storage photos."""
    service = SkinService(db=db, skin_provider=skin_provider)
    result = await service.delete_scan(scan_id=scan_id, user_id=current_user.id)
    return ResponseEnvelope(data=result)


@router.get(
    "/story",
    response_model=ResponseEnvelope[SkinStoryResponse],
    summary="Retrieve longitudinal Skin Story of compatible visual observations and journal notes",
)
async def get_skin_story(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
    metric: Annotated[
        str | None,
        Query(description="Optional filter for a single normalized metric_code"),
    ] = None,
    journal_limit: Annotated[
        int,
        Query(ge=1, le=50, description="Number of recent journal entries to include"),
    ] = 10,
) -> ResponseEnvelope[SkinStoryResponse]:
    """Generate a compatibility-checked, non-clinical longitudinal Skin Story."""
    service = SkinService(db=db, skin_provider=skin_provider)
    story = await service.get_skin_story(
        user_id=current_user.id,
        metric_filter=metric.strip().lower() if metric else None,
        journal_limit=journal_limit,
    )
    return ResponseEnvelope(data=story)


@router.post(
    "/journal",
    response_model=ResponseEnvelope[SkinJournalEntryResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a user-authored Skin Story journal entry",
)
async def create_skin_journal_entry(
    payload: CreateSkinJournalEntryRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
) -> ResponseEnvelope[SkinJournalEntryResponse]:
    """Record a longitudinal self-reported skin observation and routine log entry."""
    service = SkinService(db=db, skin_provider=skin_provider)
    entry = await service.create_journal_entry(user=current_user, payload=payload)
    return ResponseEnvelope(data=entry)


@router.get(
    "/journal",
    response_model=ResponseEnvelope[SkinJournalListResponse],
    summary="List authenticated user's Skin Story journal entries",
)
async def list_skin_journal_entries(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skin_provider: Annotated[BaseSkinAnalysisProvider, Depends(get_skin_analysis_provider)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
) -> ResponseEnvelope[SkinJournalListResponse]:
    """Return paginated Skin Story journal entries owned by the authenticated user."""
    service = SkinService(db=db, skin_provider=skin_provider)
    entries = await service.list_journal_entries(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return ResponseEnvelope(data=entries)
