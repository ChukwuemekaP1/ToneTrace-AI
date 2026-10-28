"""Pydantic exchange schemas for Phase 6: Ingredient Evidence and Research Retrieval."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.url_safety import validate_safe_external_url
from app.schemas.common import PaginationMeta

EvidenceCategoryType = Literal[
    "identity_reference",
    "published_research",
    "human_interpretation",
    "marketing_claim",
]

EvidenceDirectionType = Literal[
    "supportive",
    "neutral",
    "mixed",
    "conflicting",
    "insufficient",
    "reference_only",
]

EvidenceStrengthType = Literal[
    "strong",
    "moderate",
    "limited",
    "preliminary",
    "conflicting",
    "insufficient",
    "reference_only",
]

ReviewStatusType = Literal[
    "provisional",
    "verified",
    "disputed",
    "conflicting_flagged",
    "incorrect_match_flagged",
    "rejected",
]


class ResearchRecordResponse(BaseModel):
    """Citation, abstract, and regulatory provenance record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: str
    external_id: str
    doi: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    journal_or_authority: str | None = None
    publication_year: int | None = None
    publication_types: list[str] = Field(default_factory=list)
    study_type: str | None = None
    abstract_text: str | None = None
    has_full_text: bool = False
    source_url: str
    license_or_attribution: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime


class EvidenceSourceLinkResponse(BaseModel):
    """Link between an evidence assertion and its backing source record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    research_record_id: UUID
    data_source_id: UUID | None = None
    is_exact_match: bool = True
    relevance_note: str | None = None
    quoted_excerpt: str | None = None
    research_record: ResearchRecordResponse


class EvidenceReviewStatusResponse(BaseModel):
    """Audit log entry for evidence review status transitions."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reviewer_user_id: UUID | None = None
    previous_status: str
    new_status: str
    review_notes: str | None = None
    reviewed_at: datetime


class IngredientEvidenceItemResponse(BaseModel):
    """Single auditable ingredient evidence record with citations and review history."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ingredient_id: UUID
    evidence_category: str
    topic_or_target: str
    evidence_direction: str
    evidence_strength: str
    study_type: str | None = None
    population_or_context: str | None = None
    summary_statement: str
    limitations_and_caveats: str
    author_or_reviewer: str | None = None
    review_status: str
    retrieved_at: datetime
    source_links: list[EvidenceSourceLinkResponse] = Field(default_factory=list)
    review_history: list[EvidenceReviewStatusResponse] = Field(default_factory=list)


class EpistemicGuardrailsResponse(BaseModel):
    """Mandatory scientific and epistemic boundaries attached to every evidence response."""

    efficacy_disclaimer: str = (
        "Published literature or regulatory listings for an ingredient name alone do not "
        "prove clinical effectiveness for an individual's pigmentation or skin condition. "
        "Real-world outcomes depend on active concentration, formulation vehicle, pH, stability, "
        "and individual skin biology."
    )
    concentration_disclaimer: str = (
        "Ingredient concentration cannot be inferred from packaging ingredient order alone "
        "unless explicitly declared by a verified manufacturer source."
    )
    scan_causation_disclaimer: str = (
        "Skin scans and label scans cannot establish clinical causation or medical diagnosis."
    )
    full_text_disclaimer: str = (
        "Bibliographic records retrieved via PubMed E-utilities represent metadata and abstracts "
        "only (has_full_text=false) unless full open-access text is explicitly verified."
    )


class SeparatedEvidenceGroups(BaseModel):
    """Explicit 4-way separation of identity, published research, human review, and marketing."""

    identity_reference: list[IngredientEvidenceItemResponse] = Field(
        default_factory=list,
        description="1. Official ingredient identity & regulatory reference info (CosIng)",
    )
    published_research: list[IngredientEvidenceItemResponse] = Field(
        default_factory=list,
        description="2. Published peer-reviewed research records (PubMed)",
    )
    human_interpretation: list[IngredientEvidenceItemResponse] = Field(
        default_factory=list,
        description="3. Authored and human-reviewed dermatological interpretations",
    )
    marketing_claims: list[IngredientEvidenceItemResponse] = Field(
        default_factory=list,
        description="4. Product marketing claims (strictly isolated from scientific evidence)",
    )


class IngredientEvidenceListResponse(BaseModel):
    """Paginated and epistemically separated evidence response for an ingredient."""

    ingredient_id: UUID
    inci_name: str
    common_name: str | None = None
    items: list[IngredientEvidenceItemResponse] = Field(default_factory=list)
    separated_groups: SeparatedEvidenceGroups
    has_conflicting_evidence: bool = False
    has_insufficient_evidence: bool = False
    last_retrieved_at: datetime | None = None
    epistemic_guardrails: EpistemicGuardrailsResponse = Field(
        default_factory=EpistemicGuardrailsResponse
    )
    pagination: PaginationMeta


class EvidenceRefreshRequest(BaseModel):
    """Request payload for restricted external research retrieval and refresh."""

    sources: list[Literal["cosing", "pubmed"]] = Field(
        default=["cosing", "pubmed"],
        min_length=1,
        description="External authoritative sources to query",
    )
    topic: str | None = Field(
        default="hyperpigmentation OR skin barrier",
        max_length=200,
        description="Dermatological topic filter for PubMed ESearch",
    )
    max_pubmed_results: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Maximum PubMed records to fetch",
    )
    force_refresh: bool = Field(
        default=False,
        description="Bypass cache TTL and re-query external APIs",
    )


class EvidenceRefreshResponse(BaseModel):
    """Summary of an idempotent research retrieval/refresh operation."""

    ingredient_id: UUID
    inci_name: str
    used_cache: bool
    cosing_records_processed: int = 0
    pubmed_records_processed: int = 0
    new_evidence_created: int = 0
    deduplicated_existing_records: int = 0
    flagged_incorrect_matches: int = 0
    retrieved_at: datetime
    message: str


class CreateEvidenceRequest(BaseModel):
    """Payload to author a human-reviewed interpretation or record a segregated marketing claim."""

    evidence_category: EvidenceCategoryType
    topic_or_target: str = Field(..., min_length=2, max_length=150)
    evidence_direction: EvidenceDirectionType = "neutral"
    evidence_strength: EvidenceStrengthType = "preliminary"
    study_type: str | None = Field(default=None, max_length=80)
    population_or_context: str | None = None
    summary_statement: str = Field(..., min_length=5)
    limitations_and_caveats: str = Field(..., min_length=5)
    review_status: ReviewStatusType = "provisional"
    source_type: str | None = Field(default=None, max_length=50)
    external_id: str | None = Field(default=None, max_length=120)
    source_title: str | None = None
    source_url: str | None = Field(default=None, max_length=1024)
    quoted_excerpt: str | None = None

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: str | None) -> str | None:
        return validate_safe_external_url(v)


class UpdateEvidenceReviewRequest(BaseModel):
    """Payload to transition the review status of an IngredientEvidence record."""

    new_status: ReviewStatusType
    review_notes: str | None = Field(default=None, max_length=2000)
    summary_statement_override: str | None = None
    limitations_override: str | None = None
    evidence_direction_override: EvidenceDirectionType | None = None
    evidence_strength_override: EvidenceStrengthType | None = None
