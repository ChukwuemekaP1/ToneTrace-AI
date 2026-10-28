"""Pydantic schemas for Phase 7: Gemini-Powered Grounded Explanations.

Enforces schema versioning, strict request size limits, structured output validation,
source-ID citation binding, uncertainty disclosures, and non-diagnostic safety notices.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExplanationEpistemicCategory = Literal[
    "identity_reference",
    "published_research",
    "human_interpretation",
    "marketing_claim",
    "formulation_observation",
    "general_guidance",
]

ExplanationEvidenceStrength = Literal[
    "strong",
    "moderate",
    "limited",
    "preliminary",
    "conflicting",
    "insufficient",
    "reference_only",
    "unknown",
]

GroundingStatusType = Literal[
    "verified",
    "fallback_applied",
    "insufficient_evidence",
    "safety_escalation",
]


class ExplanationRequest(BaseModel):
    """Schema-versioned request payload for POST /api/v1/ai/explanations."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = Field(
        default="1.0",
        description="Explanation API contract schema version.",
    )
    question: str = Field(
        ...,
        min_length=3,
        max_length=1500,
        description="User's skincare question or request for product/ingredient explanation.",
    )
    product_ids: list[UUID] = Field(
        default_factory=list,
        max_length=5,
        description="Optional explicit product UUIDs to ground the explanation.",
    )
    ingredient_ids: list[UUID] = Field(
        default_factory=list,
        max_length=15,
        description="Optional explicit ingredient UUIDs to ground the explanation.",
    )
    ocr_job_id: UUID | None = Field(
        default=None,
        description="Optional OCR label-scan job UUID owned by the user.",
    )
    search_query: str | None = Field(
        default=None,
        max_length=200,
        description="Optional explicit search query for retrieving products/ingredients.",
    )
    include_user_skin_profile: bool = Field(
        default=True,
        description=(
            "Whether to incorporate the authenticated user's self-reported skin profile "
            "and ingredient sensitivities into the grounded context."
        ),
    )

    @field_validator("question")
    @classmethod
    def validate_question_not_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3:
            raise ValueError("Question must contain at least 3 non-whitespace characters.")
        return cleaned

    @field_validator("search_query")
    @classmethod
    def validate_search_query(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None


class StructuredFindingItem(BaseModel):
    """Single grounded finding produced by the language model."""

    model_config = ConfigDict(extra="ignore")

    statement: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Grounded explanation statement referencing only supplied context records.",
    )
    cited_source_ids: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "List of context source IDs (e.g., 'ing:...', 'ev:...', 'res:...', 'prod:...')."
        ),
    )
    epistemic_category: ExplanationEpistemicCategory = Field(
        default="general_guidance",
        description="Epistemic classification of the finding.",
    )
    evidence_strength: ExplanationEvidenceStrength = Field(
        default="unknown",
        description="Strength of underlying evidence supporting this finding.",
    )


class GeminiStructuredExplanationPayload(BaseModel):
    """Strict structured JSON schema expected from Gemini generation."""

    model_config = ConfigDict(extra="ignore")

    summary: str = Field(
        ...,
        min_length=5,
        max_length=3000,
        description="Concise grounded synthesis answering the user's question.",
    )
    key_findings: list[StructuredFindingItem] = Field(
        ...,
        min_length=1,
        max_length=12,
        description="List of specific grounded findings with mandatory source ID citations.",
    )
    uncertainty_notes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Explicit uncertainty notes (e.g., unknown concentrations, abstract-only studies, "
            "conflicting evidence, or unverified OCR candidates)."
        ),
    )
    requires_professional_care_escalation: bool = Field(
        default=False,
        description=(
            "True if the user describes concerning medical/dermatological symptoms "
            "requiring professional clinical evaluation."
        ),
    )
    escalation_reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Reason for recommending professional medical care when applicable.",
    )


class SourceReferenceItem(BaseModel):
    """Authoritative provenance record for a retrieved source in the grounding context."""

    model_config = ConfigDict(from_attributes=True)

    source_id: str = Field(
        ...,
        description="Canonical context source identifier (e.g. 'prod:<uuid>', 'ev:<uuid>').",
    )
    entity_type: Literal[
        "product",
        "ingredient",
        "ingredient_evidence",
        "research_record",
        "product_offer",
        "ocr_scan",
    ] = Field(..., description="Category of retrieved entity.")
    entity_uuid: UUID = Field(..., description="Database primary key UUID of the record.")
    title_or_name: str = Field(..., description="Display name or citation title.")
    source_type: str = Field(
        ...,
        description=(
            "Upstream provenance system (e.g., 'pubmed', 'cosing', 'open_beauty_facts', 'catalog')."
        ),
    )
    external_id: str | None = Field(
        default=None,
        description="External identifier such as PMID, CosIng Ref No, or EAN barcode.",
    )
    source_url: str | None = Field(
        default=None,
        description="Authoritative permalink to the upstream record when available.",
    )
    citation_label: str = Field(
        ...,
        description="Human-readable citation label (e.g. 'PubMed PMID 41319172 (2025)').",
    )
    epistemic_category: str | None = Field(
        default=None,
        description=(
            "Evidence category when applicable (identity_reference, published_research, etc.)."
        ),
    )
    has_full_text: bool = Field(
        default=False,
        description="Explicitly False when only bibliographic metadata or abstract is available.",
    )
    retrieved_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when this record was retrieved.",
    )


class GroundedFindingResponse(BaseModel):
    """Validated finding in the API response with verified source IDs."""

    statement: str
    cited_source_ids: list[str]
    epistemic_category: ExplanationEpistemicCategory
    evidence_strength: ExplanationEvidenceStrength


class UncertaintyDisclosure(BaseModel):
    """Structured disclosure of epistemic limitations and unknown variables."""

    missing_concentrations_noted: bool = Field(
        default=True,
        description="True when exact ingredient percentage concentrations are unknown.",
    )
    abstract_only_research_noted: bool = Field(
        default=False,
        description="True when cited literature records consist of metadata/abstracts only.",
    )
    conflicting_or_limited_evidence_noted: bool = Field(
        default=False,
        description="True when retrieved evidence is preliminary, limited, or conflicting.",
    )
    untrusted_label_or_ocr_noted: bool = Field(
        default=False,
        description=(
            "True when untrusted product descriptions, marketing claims, or OCR text were present."
        ),
    )
    statements: list[str] = Field(
        default_factory=list,
        description="Human-readable uncertainty and limitation disclosures.",
    )


class SafetyEscalationNotice(BaseModel):
    """Mandatory non-diagnostic safety boundary and symptom escalation notice."""

    is_diagnostic_service: Literal[False] = False
    requires_professional_care_escalation: bool = False
    escalation_guidance: str | None = None
    general_disclaimer: str = (
        "ToneTrace AI is an educational skincare companion, not a medical or diagnostic service. "
        "Explanations summarize general ingredient reference data and product-label findings "
        "without diagnosing conditions, inferring cause from scans, or guaranteeing outcomes."
    )


class GenerationMetadata(BaseModel):
    """Audit and telemetry metadata for the explanation generation pipeline."""

    provider: str
    model: str
    latency_ms: float
    fallback_used: bool = False
    fallback_reason: str | None = None
    rejected_source_ids: list[str] = Field(default_factory=list)
    prompt_injection_detected: bool = False
    retrieved_products_count: int = 0
    retrieved_ingredients_count: int = 0
    retrieved_evidence_count: int = 0
    search_backend_used: str = "postgresql"
    input_tokens: int | None = None
    output_tokens: int | None = None
    generated_at: datetime


class ExplanationResponse(BaseModel):
    """Schema-versioned response payload for POST /api/v1/ai/explanations."""

    schema_version: Literal["1.0"] = "1.0"
    explanation_id: UUID
    grounding_status: GroundingStatusType
    summary: str
    findings: list[GroundedFindingResponse]
    source_references: list[SourceReferenceItem]
    uncertainty_and_limitations: UncertaintyDisclosure
    safety_notice: SafetyEscalationNotice
    generation_metadata: GenerationMetadata
