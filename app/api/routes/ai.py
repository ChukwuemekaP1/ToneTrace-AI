"""API routes for Phase 7: Gemini-Powered Grounded Explanations.

Provides:
- POST /api/v1/ai/explanations:
  Schema-versioned grounded explanation endpoint that retrieves product, ingredient,
  and evidence records from PostgreSQL and Elasticsearch, invokes the configured
  LLMExplanationProvider (Google Gemini), validates structured JSON output, confirms
  every cited source ID belongs to the retrieved context, and returns a safe deterministic
  fallback when model output is invalid or ungrounded.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import rate_limit_ai_explanations
from app.db.models import User
from app.db.session import get_db_session
from app.providers.gemini import GeminiExplanationProvider, LLMExplanationProvider
from app.schemas.ai_explanations import ExplanationRequest, ExplanationResponse
from app.schemas.common import ResponseEnvelope
from app.services.explanation_service import ExplanationService

router = APIRouter(tags=["AI Grounded Explanations"])


def get_llm_explanation_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LLMExplanationProvider:
    """Provide the configured language-model explanation provider."""
    api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
    return GeminiExplanationProvider(
        api_key=api_key,
        model=settings.GEMINI_MODEL,
        timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
        max_retries=settings.GEMINI_MAX_RETRIES,
    )


@router.post(
    "/ai/explanations",
    response_model=ResponseEnvelope[ExplanationResponse],
    status_code=status.HTTP_200_OK,
    summary="Generate a grounded skincare explanation backed by retrieved evidence",
)
async def create_grounded_explanation(
    payload: ExplanationRequest,
    current_user: Annotated[User, Depends(rate_limit_ai_explanations)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    llm_provider: Annotated[LLMExplanationProvider, Depends(get_llm_explanation_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResponseEnvelope[ExplanationResponse]:
    """Generate a grounded, non-diagnostic explanation for products and ingredients.

    Enforces:
    - Per-user sliding-window rate limits (`AI_RATE_LIMIT_PER_MINUTE`).
    - Strict request size validation (`schema_version="1.0"`).
    - Source-ID grounding verification against PostgreSQL and Elasticsearch records.
    - Prompt injection isolation for untrusted product descriptions and OCR text.
    - Deterministic safe fallback if model output contains unsupported citations or claims.
    """
    service = ExplanationService(
        db=db,
        llm_provider=llm_provider,
        settings=settings,
    )
    result = await service.generate_explanation(request=payload, user=current_user)
    return ResponseEnvelope(data=result)
