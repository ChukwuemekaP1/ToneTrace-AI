"""Ingredient Evidence and Research Retrieval API routes (Phase 6).

Provides endpoints for:
- GET /api/v1/ingredients/{ingredient_id}/evidence (cached read-only retrieval with
  pagination, source/category/review_status/study_type filters, citation metadata,
  and strict 4-way separation of identity reference, published research,
  human-reviewed interpretations, and marketing claims)
- POST /api/v1/ingredients/{ingredient_id}/evidence/refresh (restricted, rate-limited
  research retrieval/refresh from European Commission CosIng and NCBI PubMed E-utilities)
- POST /api/v1/ingredients/{ingredient_id}/evidence (authenticated authoring of
  human-reviewed interpretations or segregated marketing claims with provenance)
- PATCH /api/v1/ingredients/{ingredient_id}/evidence/{evidence_id}/review (authenticated
  review status transition with immutable audit trail in evidence_review_status)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user, rate_limit_ingest
from app.db.models import User
from app.db.session import get_db_session
from app.schemas.common import ResponseEnvelope
from app.schemas.evidence import (
    CreateEvidenceRequest,
    EvidenceRefreshRequest,
    EvidenceRefreshResponse,
    IngredientEvidenceItemResponse,
    IngredientEvidenceListResponse,
    UpdateEvidenceReviewRequest,
)
from app.services.evidence_service import EvidenceService

router = APIRouter(tags=["Ingredient Evidence & Research Retrieval"])


@router.get(
    "/ingredients/{ingredient_id}/evidence",
    response_model=ResponseEnvelope[IngredientEvidenceListResponse],
    summary="Get auditable ingredient evidence and research citations",
)
async def get_ingredient_evidence(
    ingredient_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Number of evidence records per page")
    ] = 20,
    source: Annotated[
        str | None,
        Query(description="Filter by upstream source_type (e.g. 'cosing', 'pubmed')"),
    ] = None,
    category: Annotated[
        str | None,
        Query(
            description=(
                "Filter by evidence_category ('identity_reference', 'published_research', "
                "'human_interpretation', 'marketing_claim')"
            )
        ),
    ] = None,
    review_status: Annotated[
        str | None,
        Query(
            description=(
                "Filter by review_status ('provisional', 'verified', 'disputed', "
                "'rejected', 'incorrect_match_flagged')"
            )
        ),
    ] = None,
    study_type: Annotated[
        str | None,
        Query(
            description=(
                "Filter by study_type ('rct', 'clinical_trial', 'meta_analysis', "
                "'systematic_review', 'observational', 'in_vitro', 'regulatory_monograph', etc.)"
            )
        ),
    ] = None,
) -> ResponseEnvelope[IngredientEvidenceListResponse]:
    """Retrieve cached ingredient evidence with strict epistemic separation and citation metadata.

    Never triggers external network requests on ordinary GET calls. Separates:
    - `identity_references` (CosIng nomenclature/functions/restrictions)
    - `published_research` (PubMed bibliographic metadata & abstracts, `has_full_text=False`)
    - `human_interpretations` (authored/reviewed evidence summaries with provenance)
    - `marketing_claims` (segregated commercial claims, never treated as scientific proof)
    """
    service = EvidenceService(db)
    result = await service.get_ingredient_evidence(
        ingredient_id=ingredient_id,
        source_type=source,
        evidence_category=category,
        review_status=review_status,
        study_type=study_type,
        page=page,
        page_size=page_size,
    )
    return ResponseEnvelope(data=result)


@router.post(
    "/ingredients/{ingredient_id}/evidence/refresh",
    response_model=ResponseEnvelope[EvidenceRefreshResponse],
    status_code=status.HTTP_200_OK,
    summary="Restricted research retrieval and refresh from CosIng and PubMed",
    dependencies=[Depends(rate_limit_ingest)],
)
async def refresh_ingredient_evidence(
    ingredient_id: UUID,
    payload: EvidenceRefreshRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[EvidenceRefreshResponse]:
    """Authenticated, rate-limited operation to retrieve or refresh external research records.

    Honors cache TTL (`EVIDENCE_CACHE_TTL_HOURS`) unless `force_refresh=True` is supplied.
    Idempotently deduplicates `ResearchRecord` rows by `(source_type, external_id)`.
    """
    service = EvidenceService(db)
    result = await service.refresh_ingredient_evidence(
        ingredient_id=ingredient_id,
        payload=payload,
        reviewer_user=current_user,
    )
    return ResponseEnvelope(data=result)


@router.post(
    "/ingredients/{ingredient_id}/evidence",
    response_model=ResponseEnvelope[IngredientEvidenceItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create human-reviewed interpretation or segregated marketing claim",
)
async def create_ingredient_evidence(
    ingredient_id: UUID,
    payload: CreateEvidenceRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[IngredientEvidenceItemResponse]:
    """Record an authored human interpretation or isolated marketing claim with provenance."""
    service = EvidenceService(db)
    result = await service.create_evidence_item(
        ingredient_id=ingredient_id,
        payload=payload,
        author_user=current_user,
    )
    return ResponseEnvelope(data=result)


@router.patch(
    "/ingredients/{ingredient_id}/evidence/{evidence_id}/review",
    response_model=ResponseEnvelope[IngredientEvidenceItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Update evidence review status and record audit trail",
)
async def update_ingredient_evidence_review(
    ingredient_id: UUID,
    evidence_id: UUID,
    payload: UpdateEvidenceReviewRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResponseEnvelope[IngredientEvidenceItemResponse]:
    """Transition an evidence record's review status (`verified`, `disputed`, `rejected`, etc.)."""
    service = EvidenceService(db)
    result = await service.update_evidence_review(
        ingredient_id=ingredient_id,
        evidence_id=evidence_id,
        payload=payload,
        reviewer_user=current_user,
    )
    return ResponseEnvelope(data=result)
