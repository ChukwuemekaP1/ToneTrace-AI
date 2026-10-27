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

from app.core.security import get_current_active_user
from app.db.models import User
from app.db.session import get_db_session
from app.providers.storage import get_storage_provider
from app.providers.storage.local import LocalStorageProvider
from app.schemas.common import ResponseEnvelope
from app.schemas.ocr import (
    ConfirmScanRequest,
    ConfirmScanResponse,
    OCRScanResponse,
)
from app.services.ocr_service import OCRService

router = APIRouter(prefix="/ocr", tags=["OCR & Label Scanning"])


@router.post(
    "/scans",
    response_model=ResponseEnvelope[OCRScanResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload product label image and extract formulation ingredients",
)
async def create_scan(
    file: Annotated[UploadFile, File(description="Product label image (JPEG, PNG, WebP)")],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Form(description="Optional idempotency key")] = None,
) -> ResponseEnvelope[OCRScanResponse]:
    """Upload product label image, store securely, and trigger OCR ingredient segmentation."""
    file_bytes = await file.read()
    service = OCRService(db)

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
) -> ResponseEnvelope[OCRScanResponse]:
    """Retrieve details and candidate ingredients for an existing OCR scan job."""
    service = OCRService(db)
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
) -> ResponseEnvelope[ConfirmScanResponse]:
    """Apply human review and corrections to the extracted candidate ingredients."""
    service = OCRService(db)
    confirm_response = await service.confirm_scan(
        scan_id=scan_id,
        user_id=current_user.id,
        confirmed_items=payload.ingredients,
    )
    return ResponseEnvelope(data=confirm_response)


@router.get(
    "/assets/view",
    summary="Stream private stored image asset via time-limited signed URL",
)
async def view_asset(
    key: Annotated[str, Query(..., description="Storage object key")],
    exp: Annotated[int, Query(..., description="Timestamp of token expiration")],
    sig: Annotated[str, Query(..., description="HMAC-SHA256 signature")],
) -> Response:
    """Stream private media object if short-lived signed URL token is valid."""
    storage = get_storage_provider()
    if isinstance(storage, LocalStorageProvider):
        is_valid = storage.verify_token(key, exp, sig)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired asset token.",
            )
        try:
            data = await storage.retrieve_object(key)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found.",
            ) from exc
        # Determine content type based on extension
        ext = key.split(".")[-1].lower() if "." in key else "jpeg"
        content_type = "image/jpeg"
        if ext == "png":
            content_type = "image/png"
        elif ext == "webp":
            content_type = "image/webp"
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )

    # For external providers (e.g. S3/R2), clients should directly use presigned URL
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Asset viewing proxy is only enabled for local storage provider.",
    )
