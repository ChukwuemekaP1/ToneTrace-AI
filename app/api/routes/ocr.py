"""OCR and product label scanning API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import get_current_active_user, rate_limit_heavy_scan
from app.db.models import User
from app.db.session import get_db_session
from app.providers.storage import (
    LocalStorageProvider,
    PostgresStorageProvider,
    get_storage_provider,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.ocr import (
    ConfirmScanRequest,
    ConfirmScanResponse,
    MediaAssetDeleteResponse,
    OCRScanResponse,
)
from app.services.ocr_service import OCRService

router = APIRouter(prefix="/ocr", tags=["OCR & Label Scanning"])


@router.post(
    "/scans",
    response_model=ResponseEnvelope[OCRScanResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_heavy_scan)],
    summary="Upload product label image and extract formulation ingredients",
)
async def create_scan(
    file: Annotated[UploadFile, File(description="Product label image (JPEG, PNG, WebP)")],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str | None, Form(description="Optional idempotency key")] = None,
) -> ResponseEnvelope[OCRScanResponse]:
    """Upload product label image, store securely, and trigger OCR ingredient segmentation."""
    file_bytes = await file.read()
    service = OCRService(db, settings=settings)

    media_asset = await service.validate_and_store_image(
        user=current_user,
        file_bytes=file_bytes,
        original_filename=file.filename,
        declared_content_type=file.content_type,
    )

    scan_response = await service.create_and_process_scan(
        user=current_user,
        media_asset=media_asset,
        image_bytes=file_bytes,
        idempotency_key=idempotency_key,
    )
    return ResponseEnvelope(data=scan_response)


@router.get(
    "/scans/{scan_id}",
    response_model=ResponseEnvelope[OCRScanResponse],
    summary="Retrieve OCR scan status, raw text, and candidate ingredients",
)
async def get_scan(
    scan_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResponseEnvelope[OCRScanResponse]:
    """Retrieve details and candidate ingredients for an existing OCR scan job."""
    service = OCRService(db, settings=settings)
    scan_response = await service.get_scan(scan_id, current_user.id)
    return ResponseEnvelope(data=scan_response)


@router.post(
    "/scans/{scan_id}/confirm",
    response_model=ResponseEnvelope[ConfirmScanResponse],
    summary="Review, edit, and confirm candidate ingredients from OCR scan",
)
async def confirm_scan(
    scan_id: UUID,
    payload: ConfirmScanRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResponseEnvelope[ConfirmScanResponse]:
    """Apply human review and corrections to the extracted candidate ingredients."""
    service = OCRService(db, settings=settings)
    confirm_response = await service.confirm_scan(
        scan_id=scan_id,
        user_id=current_user.id,
        confirmed_items=payload.ingredients,
    )
    return ResponseEnvelope(data=confirm_response)


@router.get(
    "/assets/by-id/{asset_id}",
    summary="Retrieve owned private image asset bytes (authenticated owner only)",
)
async def get_owned_asset(
    asset_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Stream raw image bytes from PostgreSQL BYTEA if owned by the authenticated user."""
    service = OCRService(db, settings=settings)
    data, content_type = await service.retrieve_owned_asset_bytes(asset_id, current_user.id)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/assets/by-id/{asset_id}",
    response_model=ResponseEnvelope[MediaAssetDeleteResponse],
    summary="Delete owned private image asset bytes from PostgreSQL",
)
async def delete_owned_asset(
    asset_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResponseEnvelope[MediaAssetDeleteResponse]:
    """Delete raw image bytes for a user-owned MediaAsset (enforces authenticated ownership)."""
    service = OCRService(db, settings=settings)
    result = await service.delete_owned_asset(asset_id, current_user.id)
    return ResponseEnvelope(data=result)


@router.get(
    "/assets/view",
    summary="Stream private stored image asset via time-limited signed URL",
)
async def view_asset(
    key: Annotated[str, Query(..., description="Storage object key")],
    exp: Annotated[int, Query(..., description="Timestamp of token expiration")],
    sig: Annotated[str, Query(..., description="HMAC-SHA256 signature")],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Stream private media object from PostgreSQL BYTEA or local storage if HMAC token is valid."""
    storage = get_storage_provider()
    if isinstance(storage, (PostgresStorageProvider, LocalStorageProvider)):
        is_valid = storage.verify_token(key, exp, sig)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired asset token.",
            )
        service = OCRService(db, storage_provider=storage, settings=settings)
        try:
            data, content_type = await service.retrieve_asset_by_storage_key(key)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found.",
            ) from exc
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Asset viewing proxy requires PostgresStorageProvider or LocalStorageProvider.",
    )
