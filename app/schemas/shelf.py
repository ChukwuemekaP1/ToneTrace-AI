"""Pydantic v2 schemas for My Shelf and Product Discovery (Phase 9)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ai_explanations import ExplanationResponse

RULE_ENGINE_VERSION = "tonetrace-discovery-rules-v1.0"

CONCENTRATION_DISCLOSURE = (
    "Exact ingredient concentrations are unknown unless explicitly backed by a verified "
    "source. Packaging ingredient order indicates relative descending order above 1% only "
    "and cannot be used to infer exact percentage concentration."
)

COMMERCIAL_SEGREGATION_NOTICE = (
    "Commercial merchant offers and pricing are strictly separated from scientific "
    "ingredient evidence. Paid or affiliate offers never influence suitability scores "
    "or scientific recommendations."
)

PIGMENTATION_AND_MEDICAL_DISCLAIMER = (
    "Recommendations are transparent, rule-based cosmetic suitability assessments. "
    "They never guarantee results for hyperpigmentation or melasma, never treat missing "
    "ingredient data as proof of safety, and never constitute medical advice or diagnosis."
)

ShelfStatusLiteral = Literal[
    "in_use",
    "wishlist",
    "finished",
    "paused",
    "discontinued",
    "avoided",
]

ReactionTypeLiteral = Literal[
    "well_tolerated",
    "irritation",
    "redness",
    "breakout",
    "dryness",
    "stinging",
    "allergic_suspect",
    "no_visible_change",
]

ReactionSeverityLiteral = Literal["none", "mild", "moderate", "severe"]


class ProductReactionCreateInput(BaseModel):
    """Input payload for recording a personal product reaction or tolerance note."""

    reaction_type: ReactionTypeLiteral = Field(
        ...,
        description="Observed skin tolerance or reaction category.",
    )
    severity: ReactionSeverityLiteral = Field(
        default="none",
        description="Perceived severity of the reaction.",
    )
    suspected_ingredient_names: list[str] = Field(
        default_factory=list,
        max_length=25,
        description="Optional ingredient names the user suspects contributed to the reaction.",
    )
    notes: str | None = Field(
        default=None,
        max_length=1500,
        description="Strictly private user notes about the reaction.",
    )
    observed_at: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when the reaction was observed.",
    )


class ProductReactionResponse(BaseModel):
    """Response model for a recorded user product reaction."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    user_product_id: UUID
    product_id: UUID | None = None
    reaction_type: str
    severity: str
    suspected_ingredient_names: list[str]
    notes: str | None = None
    observed_at: datetime
    created_at: datetime


class ShelfItemCreateRequest(BaseModel):
    """Request payload to add a catalogue-linked or custom product to My Shelf."""

    product_id: UUID | None = Field(
        default=None,
        description="Public catalogue Product UUID when adding a catalogue-linked item.",
    )
    variant_id: UUID | None = Field(
        default=None,
        description="Optional ProductVariant UUID.",
    )
    ocr_job_id: UUID | None = Field(
        default=None,
        description="Optional user-owned OCRJob UUID for custom scanned products.",
    )
    custom_name: str | None = Field(
        default=None,
        max_length=255,
        description="Custom product name (required when product_id is omitted).",
    )
    custom_brand: str | None = Field(
        default=None,
        max_length=150,
        description="Custom brand name (required when product_id is omitted).",
    )
    custom_category: str | None = Field(
        default=None,
        max_length=100,
        description="Skincare category for custom product (e.g. cleanser, serum, sunscreen).",
    )
    custom_ingredient_text: str | None = Field(
        default=None,
        max_length=8000,
        description="Optional raw ingredient declaration for a custom product.",
    )
    status: ShelfStatusLiteral = Field(
        default="in_use",
        description="Initial shelf status.",
    )
    opened_at: datetime | None = Field(
        default=None,
        description="Optional date/time when the product was opened.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiration or Period-After-Opening target date.",
    )
    purchase_price_minor_units: int | None = Field(
        default=None,
        ge=0,
        description="Optional purchase price in integer minor units (e.g. cents).",
    )
    purchase_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Optional ISO 4217 currency code (e.g. USD, EUR, GBP).",
    )
    private_notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Personal notes kept strictly private to the owning user.",
    )
    initial_reaction: ProductReactionCreateInput | None = Field(
        default=None,
        description="Optional initial reaction or tolerance observation.",
    )

    @model_validator(mode="after")
    def validate_catalogue_or_custom(self) -> "ShelfItemCreateRequest":
        has_catalogue = self.product_id is not None
        clean_name = self.custom_name.strip() if self.custom_name else ""
        clean_brand = self.custom_brand.strip() if self.custom_brand else ""

        if not has_catalogue and (not clean_name or not clean_brand):
            raise ValueError(
                "Either 'product_id' (for a catalogue product) or both 'custom_name' and "
                "'custom_brand' (for a custom product) must be provided."
            )
        if clean_name:
            self.custom_name = clean_name
        if clean_brand:
            self.custom_brand = clean_brand
        if self.custom_category:
            self.custom_category = self.custom_category.strip().lower()
        if self.purchase_currency:
            self.purchase_currency = self.purchase_currency.strip().upper()
        return self


class ShelfItemUpdateRequest(BaseModel):
    """PATCH payload for updating a user's shelf item or recording a product reaction."""

    status: ShelfStatusLiteral | None = None
    opened_at: datetime | None = None
    expires_at: datetime | None = None
    purchase_price_minor_units: int | None = Field(default=None, ge=0)
    purchase_currency: str | None = Field(default=None, min_length=3, max_length=3)
    private_notes: str | None = Field(default=None, max_length=2000)
    custom_name: str | None = Field(default=None, min_length=1, max_length=255)
    custom_brand: str | None = Field(default=None, min_length=1, max_length=150)
    custom_category: str | None = Field(default=None, min_length=1, max_length=100)
    custom_ingredient_text: str | None = Field(default=None, max_length=8000)
    reaction: ProductReactionCreateInput | None = Field(
        default=None,
        description="Optional reaction or tolerance observation to append to this shelf item.",
    )


class ShelfItemResponse(BaseModel):
    """User-owned shelf item with resolved catalogue/custom details and sensitivity flags."""

    id: UUID
    user_id: UUID
    product_id: UUID | None = None
    variant_id: UUID | None = None
    ocr_job_id: UUID | None = None
    is_custom: bool
    display_name: str
    display_brand: str
    display_category: str
    catalogue_status: Literal["catalogue_linked", "custom_entry", "catalogue_unavailable"]
    ingredient_data_status: Literal["complete", "partial_text_only", "missing"]
    ingredient_names: list[str] = Field(default_factory=list)
    sensitivity_alerts: list[str] = Field(
        default_factory=list,
        description="Ingredients in this item that match the user's known sensitivities.",
    )
    incomplete_ingredient_warning: str | None = Field(
        default=None,
        description="Explicit warning when ingredient data is missing or unparsed.",
    )
    status: str
    opened_at: datetime | None = None
    expires_at: datetime | None = None
    purchase_price_minor_units: int | None = None
    purchase_currency: str | None = None
    private_notes: str | None = None
    is_public: bool = False
    reactions: list[ProductReactionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ShelfListResponse(BaseModel):
    """Paginated response of user shelf items."""

    items: list[ShelfItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RuleEvaluationItem(BaseModel):
    """Single explainable, versioned rule evaluation in the recommendation engine."""

    rule_id: str
    rule_version: str = "1.0"
    outcome: Literal["pass", "warning", "disqualified", "neutral", "info"]
    score_delta: int
    explanation: str
    source_ids: list[str] = Field(
        default_factory=list,
        description="Traceable source IDs (prod:<uuid>, ing:<uuid>, ev:<uuid>, res:<uuid>).",
    )


class RecommendationAssessment(BaseModel):
    """Transparent, rule-based suitability assessment for a product."""

    rule_engine_version: str = RULE_ENGINE_VERSION
    suitability_tier: Literal[
        "recommended_fit",
        "compatible_neutral",
        "insufficient_ingredient_data",
        "avoid_sensitivity_match",
    ]
    suitability_score: int = Field(..., ge=0, le=100)
    ingredient_data_status: Literal["complete", "partial_text_only", "missing"]
    missing_data_is_not_safety_proof: bool = True
    concentration_disclosure: str = CONCENTRATION_DISCLOSURE
    matched_sensitivities: list[str] = Field(default_factory=list)
    matched_reaction_suspects: list[str] = Field(default_factory=list)
    matched_goal_ingredients: list[str] = Field(default_factory=list)
    rules_triggered: list[RuleEvaluationItem] = Field(default_factory=list)
    summary_rationale: str
    scientific_vs_commercial_notice: str = COMMERCIAL_SEGREGATION_NOTICE
    pigmentation_and_medical_disclaimer: str = PIGMENTATION_AND_MEDICAL_DISCLAIMER


class DiscoveryIngredientDetail(BaseModel):
    """Canonical ingredient entry within a discovery product detail response."""

    ingredient_id: UUID
    source_id: str
    inci_name: str
    common_name: str | None = None
    position: int
    function: str | None = None
    concentration_percentage: float | None = None
    concentration_status: Literal["verified_percentage", "unknown_order_only"]
    is_user_sensitivity_match: bool = False
    evidence_count: int = 0
    evidence_summaries: list[str] = Field(default_factory=list)
    evidence_source_ids: list[str] = Field(default_factory=list)


class DiscoveryOfferSummary(BaseModel):
    """Commercial product offer strictly separated from scientific suitability."""

    offer_id: UUID
    merchant_name: str
    price_minor_units: int
    currency: str
    is_in_stock: bool
    offer_url: str | None = None
    retrieved_at: datetime
    commercial_segregation_label: str = "commercial_offer_not_scientific_endorsement"


class DiscoveryProductSummaryItem(BaseModel):
    """Product discovery card combining PostgreSQL canonical metadata and rule assessment."""

    product_id: UUID
    source_id: str
    name: str
    brand: str
    category: str
    description: str | None = None
    image_url: str | None = None
    ingredient_count: int
    ingredient_data_status: Literal["complete", "partial_text_only", "missing"]
    on_user_shelf: bool = False
    user_shelf_status: str | None = None
    lowest_offer_minor_units: int | None = None
    lowest_offer_currency: str | None = None
    recommendation: RecommendationAssessment


class DiscoveryProductListResponse(BaseModel):
    """Paginated product discovery response."""

    items: list[DiscoveryProductSummaryItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    search_backend_used: Literal[
        "elasticsearch",
        "postgresql_catalogue",
        "postgresql_fallback",
    ]
    degraded_search_warning: str | None = None
    rule_engine_version: str = RULE_ENGINE_VERSION


class DiscoveryProductDetailResponse(BaseModel):
    """Comprehensive product discovery view with ingredient provenance and AI explanation."""

    product_id: UUID
    source_id: str
    name: str
    brand: str
    category: str
    description: str | None = None
    ean_or_upc: str | None = None
    image_url: str | None = None
    formula_version: str | None = None
    full_ingredient_list: str | None = None
    ingredient_data_status: Literal["complete", "partial_text_only", "missing"]
    ingredients: list[DiscoveryIngredientDetail] = Field(default_factory=list)
    commercial_offers: list[DiscoveryOfferSummary] = Field(default_factory=list)
    on_user_shelf: bool = False
    user_shelf_item_id: UUID | None = None
    user_shelf_status: str | None = None
    recommendation: RecommendationAssessment
    grounded_ai_explanation: ExplanationResponse | None = Field(
        default=None,
        description=(
            "Optional Gemini explanation grounded strictly in retrieved product, "
            "ingredient, and evidence source IDs."
        ),
    )
