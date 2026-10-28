"""Domain service for Phase 6: Ingredient Evidence and Research Retrieval.

Enforces strict epistemic and provenance boundaries:
1. Separates ingredient identity/reference data (CosIng), published research (PubMed),
   human-reviewed interpretations, and commercial marketing claims.
2. Uses database caching and idempotent deduplication (`source_type`, `external_id`)
   so ordinary GET requests never invoke external network calls.
3. Explicitly flags non-exact ingredient matches (`incorrect_match_flagged`) and
   missing abstracts (`insufficient`).
4. Never fabricates citations, clinical conclusions, concentrations, or full-text possession.
"""

import logging
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import DependencyError, NotFoundError, RateLimitError
from app.db.models import (
    DataSource,
    EvidenceReviewStatus,
    EvidenceSourceLink,
    Ingredient,
    IngredientEvidence,
    ResearchRecord,
    User,
)
from app.providers.cosing import CosIngAdapter, CosIngError, CosIngRecord
from app.providers.pubmed import (
    PubMedAdapter,
    PubMedArticleRecord,
    PubMedError,
    PubMedRateLimitError,
)
from app.schemas.common import PaginationMeta
from app.schemas.evidence import (
    CreateEvidenceRequest,
    EpistemicGuardrailsResponse,
    EvidenceRefreshRequest,
    EvidenceRefreshResponse,
    EvidenceReviewStatusResponse,
    EvidenceSourceLinkResponse,
    IngredientEvidenceItemResponse,
    IngredientEvidenceListResponse,
    ResearchRecordResponse,
    SeparatedEvidenceGroups,
    UpdateEvidenceReviewRequest,
)
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class EvidenceService(BaseService):
    """Service managing auditable ingredient evidence, research records, and review workflows."""

    def __init__(
        self,
        db: AsyncSession,
        pubmed_adapter: PubMedAdapter | None = None,
        cosing_adapter: CosIngAdapter | None = None,
    ) -> None:
        super().__init__(db)
        self._pubmed = pubmed_adapter or PubMedAdapter()
        self._cosing = cosing_adapter or CosIngAdapter()

    async def _get_ingredient_or_404(self, ingredient_id: UUID) -> Ingredient:
        stmt = (
            select(Ingredient)
            .where(Ingredient.id == ingredient_id)
            .options(selectinload(Ingredient.alias_records))
        )
        res = await self.db.execute(stmt)
        ingredient = res.scalar_one_or_none()
        if ingredient is None:
            raise NotFoundError(f"Ingredient with ID '{ingredient_id}' was not found.")
        return ingredient

    async def _get_or_create_data_source(
        self,
        code: str,
        name: str,
        attribution_url: str,
        license_or_terms: str,
    ) -> DataSource:
        stmt = select(DataSource).where(DataSource.code == code)
        res = await self.db.execute(stmt)
        ds = res.scalar_one_or_none()
        if ds is None:
            ds = DataSource(
                code=code,
                name=name,
                attribution_url=attribution_url,
                license_or_terms=license_or_terms,
            )
            self.db.add(ds)
            await self.db.flush()
        return ds

    async def get_ingredient_evidence(
        self,
        ingredient_id: UUID,
        source_type: str | None = None,
        evidence_category: str | None = None,
        review_status: str | None = None,
        study_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> IngredientEvidenceListResponse:
        """Retrieve cached, auditable evidence for an ingredient without external network calls."""
        ingredient = await self._get_ingredient_or_404(ingredient_id)

        stmt = (
            select(IngredientEvidence)
            .where(IngredientEvidence.ingredient_id == ingredient.id)
            .options(
                selectinload(IngredientEvidence.source_links).selectinload(
                    EvidenceSourceLink.research_record
                ),
                selectinload(IngredientEvidence.review_history),
            )
            .order_by(IngredientEvidence.retrieved_at.desc(), IngredientEvidence.id.asc())
            .execution_options(populate_existing=True)
        )

        if evidence_category:
            stmt = stmt.where(IngredientEvidence.evidence_category == evidence_category)
        if review_status:
            stmt = stmt.where(IngredientEvidence.review_status == review_status)
        if study_type:
            stmt = stmt.where(IngredientEvidence.study_type == study_type)
        if source_type:
            stmt = (
                stmt.join(
                    EvidenceSourceLink,
                    EvidenceSourceLink.evidence_id == IngredientEvidence.id,
                )
                .join(
                    ResearchRecord,
                    ResearchRecord.id == EvidenceSourceLink.research_record_id,
                )
                .where(func.lower(ResearchRecord.source_type) == source_type.lower())
                .distinct()
            )

        res = await self.db.execute(stmt)
        all_matching = list(res.scalars().all())

        total_items = len(all_matching)
        total_pages = max(1, math.ceil(total_items / page_size)) if total_items > 0 else 0
        offset = (page - 1) * page_size
        paged_models = all_matching[offset : offset + page_size]

        mapped_items = [self._map_evidence_item(ev) for ev in paged_models]

        # Build separated groups from the current page items
        separated = SeparatedEvidenceGroups(
            identity_reference=[
                item for item in mapped_items if item.evidence_category == "identity_reference"
            ],
            published_research=[
                item for item in mapped_items if item.evidence_category == "published_research"
            ],
            human_interpretation=[
                item for item in mapped_items if item.evidence_category == "human_interpretation"
            ],
            marketing_claims=[
                item for item in mapped_items if item.evidence_category == "marketing_claim"
            ],
        )

        has_conflicting = any(
            ev.evidence_direction == "conflicting"
            or ev.evidence_strength == "conflicting"
            or ev.review_status == "conflicting_flagged"
            for ev in all_matching
        )
        has_insufficient = len(all_matching) == 0 or any(
            ev.evidence_direction == "insufficient" or ev.evidence_strength == "insufficient"
            for ev in all_matching
        )
        last_retrieved = (
            max((ev.retrieved_at for ev in all_matching), default=None) if all_matching else None
        )

        return IngredientEvidenceListResponse(
            ingredient_id=ingredient.id,
            inci_name=ingredient.inci_name,
            common_name=ingredient.common_name,
            items=mapped_items,
            separated_groups=separated,
            has_conflicting_evidence=has_conflicting,
            has_insufficient_evidence=has_insufficient,
            last_retrieved_at=last_retrieved,
            epistemic_guardrails=EpistemicGuardrailsResponse(),
            pagination=PaginationMeta(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def refresh_ingredient_evidence(
        self,
        ingredient_id: UUID,
        payload: EvidenceRefreshRequest,
        reviewer_user: User | None = None,
    ) -> EvidenceRefreshResponse:
        """Retrieve or refresh external CosIng and PubMed evidence with caching & deduplication."""
        settings = get_settings()
        ingredient = await self._get_ingredient_or_404(ingredient_id)
        now = datetime.now(UTC)

        # 1. Check cache freshness unless force_refresh=True
        if not payload.force_refresh:
            cutoff = now - timedelta(hours=settings.EVIDENCE_CACHE_TTL_HOURS)
            cache_stmt = select(func.max(IngredientEvidence.retrieved_at)).where(
                IngredientEvidence.ingredient_id == ingredient.id
            )
            cache_res = await self.db.execute(cache_stmt)
            latest_ts: datetime | None = cache_res.scalar_one_or_none()
            if latest_ts is not None:
                if latest_ts.tzinfo is None:
                    latest_ts = latest_ts.replace(tzinfo=UTC)
                if latest_ts >= cutoff:
                    return EvidenceRefreshResponse(
                        ingredient_id=ingredient.id,
                        inci_name=ingredient.inci_name,
                        used_cache=True,
                        retrieved_at=latest_ts,
                        message=(
                            "Cached evidence is fresh within TTL window; skipped external calls. "
                            "Pass force_refresh=true to force upstream re-retrieval."
                        ),
                    )

        cosing_processed = 0
        pubmed_processed = 0
        new_evidence_count = 0
        dedup_count = 0
        flagged_incorrect_count = 0

        # 2. Retrieve from European Commission CosIng
        if "cosing" in payload.sources:
            cosing_ds = await self._get_or_create_data_source(
                code="ec_cosing",
                name="European Commission CosIng Database",
                attribution_url="https://ec.europa.eu/growth/tools-databases/cosing/",
                license_or_terms=(
                    "European Union Open Data / Decision (EU) 2022/677 — "
                    "Source: European Commission CosIng Cosmetic Ingredient Database."
                ),
            )
            try:
                cosing_records = await self._cosing.search_ingredient(
                    ingredient.inci_name, max_results=3
                )
            except CosIngError as exc:
                raise DependencyError(f"EC CosIng upstream error: {exc}") from exc
            for c_rec in cosing_records:
                cosing_processed += 1
                created, deduped, flagged = await self._ingest_cosing_record(
                    ingredient=ingredient,
                    cosing_rec=c_rec,
                    data_source=cosing_ds,
                    reviewer_user=reviewer_user,
                )
                if created:
                    new_evidence_count += 1
                if deduped:
                    dedup_count += 1
                if flagged:
                    flagged_incorrect_count += 1

        # 3. Retrieve from NCBI PubMed E-utilities
        if "pubmed" in payload.sources:
            pubmed_ds = await self._get_or_create_data_source(
                code="ncbi_pubmed",
                name="NCBI PubMed E-utilities",
                attribution_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
                license_or_terms=(
                    "Courtesy of the U.S. National Library of Medicine (NLM) "
                    "via NCBI PubMed E-utilities."
                ),
            )
            aliases: list[str] = []
            if ingredient.common_name:
                aliases.append(ingredient.common_name)
            for al_rec in ingredient.alias_records:
                aliases.append(al_rec.alias_name)

            try:
                pubmed_records = await self._pubmed.search_and_fetch(
                    ingredient_name=ingredient.inci_name,
                    topic=payload.topic,
                    max_results=payload.max_pubmed_results,
                    aliases=aliases,
                )
            except PubMedRateLimitError as exc:
                raise RateLimitError(str(exc)) from exc
            except PubMedError as exc:
                raise DependencyError(f"PubMed E-utilities upstream error: {exc}") from exc
            for p_rec in pubmed_records:
                pubmed_processed += 1
                created, deduped, flagged = await self._ingest_pubmed_record(
                    ingredient=ingredient,
                    pubmed_rec=p_rec,
                    data_source=pubmed_ds,
                    topic=payload.topic or "dermatology",
                    reviewer_user=reviewer_user,
                )
                if created:
                    new_evidence_count += 1
                if deduped:
                    dedup_count += 1
                if flagged:
                    flagged_incorrect_count += 1

        await self.db.commit()

        return EvidenceRefreshResponse(
            ingredient_id=ingredient.id,
            inci_name=ingredient.inci_name,
            used_cache=False,
            cosing_records_processed=cosing_processed,
            pubmed_records_processed=pubmed_processed,
            new_evidence_created=new_evidence_count,
            deduplicated_existing_records=dedup_count,
            flagged_incorrect_matches=flagged_incorrect_count,
            retrieved_at=now,
            message=(
                f"Processed {cosing_processed} CosIng and {pubmed_processed} PubMed records "
                f"({new_evidence_count} new evidence items, {dedup_count} deduplicated)."
            ),
        )

    async def _ingest_cosing_record(
        self,
        ingredient: Ingredient,
        cosing_rec: CosIngRecord,
        data_source: DataSource,
        reviewer_user: User | None = None,
    ) -> tuple[bool, bool, bool]:
        """Idempotently persist a CosIng regulatory record and link to IngredientEvidence."""
        # 1. Upsert ResearchRecord by (source_type='cosing', external_id=cosing_ref_no)
        rec_stmt = select(ResearchRecord).where(
            ResearchRecord.source_type == "cosing",
            ResearchRecord.external_id == cosing_rec.cosing_ref_no,
        )
        rec_res = await self.db.execute(rec_stmt)
        research_rec = rec_res.scalar_one_or_none()
        was_deduped = research_rec is not None

        raw_meta = {
            "inci_name": cosing_rec.inci_name,
            "cas_no": cosing_rec.cas_no,
            "ec_no": cosing_rec.ec_no,
            "functions": cosing_rec.functions,
            "restrictions": cosing_rec.restrictions,
            "max_concentration": cosing_rec.max_concentration,
            "sccs_opinions": cosing_rec.sccs_opinions,
            "annex_no": cosing_rec.annex_no,
        }

        if research_rec is None:
            research_rec = ResearchRecord(
                source_type="cosing",
                external_id=cosing_rec.cosing_ref_no,
                title=(
                    f"EC CosIng Inventory Monograph: {cosing_rec.inci_name} "
                    f"(Ref #{cosing_rec.cosing_ref_no})"
                ),
                authors=["European Commission Directorate-General for Internal Market (GROWTH)"],
                journal_or_authority="European Commission CosIng Database",
                publication_types=["Regulatory Monograph"],
                study_type="regulatory_monograph",
                abstract_text=cosing_rec.chemical_description,
                has_full_text=False,
                source_url=cosing_rec.source_url,
                license_or_attribution=cosing_rec.attribution,
                raw_metadata=raw_meta,
                retrieved_at=cosing_rec.retrieved_at,
            )
            self.db.add(research_rec)
            await self.db.flush()
        else:
            research_rec.retrieved_at = cosing_rec.retrieved_at
            research_rec.raw_metadata = raw_meta

        # 2. Check if already linked to this ingredient
        link_stmt = (
            select(EvidenceSourceLink)
            .join(IngredientEvidence, IngredientEvidence.id == EvidenceSourceLink.evidence_id)
            .where(
                IngredientEvidence.ingredient_id == ingredient.id,
                EvidenceSourceLink.research_record_id == research_rec.id,
            )
        )
        link_res = await self.db.execute(link_stmt)
        if link_res.scalar_one_or_none() is not None:
            return False, True, not cosing_rec.is_exact_inci_match

        # 3. Determine review status based on exact vs derivative INCI match
        is_exact = cosing_rec.is_exact_inci_match
        review_status = "verified" if is_exact else "incorrect_match_flagged"

        func_str = ", ".join(cosing_rec.functions) if cosing_rec.functions else "Not specified"
        restr_str = (
            "; ".join(cosing_rec.restrictions)
            if cosing_rec.restrictions
            else "No specific Annex restrictions listed"
        )
        summary = (
            f"Official EC CosIng record for '{cosing_rec.inci_name}' "
            f"(Ref #{cosing_rec.cosing_ref_no}). "
            f"Documented cosmetic functions: {func_str}. "
            f"CAS: {cosing_rec.cas_no or 'N/A'}, EC: {cosing_rec.ec_no or 'N/A'}. "
            f"Regulatory restrictions: {restr_str}."
        )
        limitations = (
            "CosIng lists official European Union cosmetic ingredient nomenclature, recognized "
            "functions, and regulatory restrictions. It is a regulatory reference inventory and "
            "does not constitute clinical proof of efficacy for individual skin pigmentation."
        )
        if not is_exact:
            limitations = (
                f"FLAGGED MISMATCH: Queried ingredient '{ingredient.inci_name}', but CosIng entry "
                f"is for derivative/compound '{cosing_rec.inci_name}'. {limitations}"
            )

        # Update canonical ingredient function if exact match and currently empty
        if is_exact and not ingredient.function and cosing_rec.functions:
            ingredient.function = ", ".join(cosing_rec.functions)[:150]

        evidence = IngredientEvidence(
            ingredient_id=ingredient.id,
            evidence_category="identity_reference",
            topic_or_target="cosing_regulatory_identity",
            evidence_direction="reference_only",
            evidence_strength="reference_only",
            study_type="regulatory_monograph",
            population_or_context="European Union Regulation (EC) No 1223/2009 Cosmetic Inventory",
            summary_statement=summary,
            limitations_and_caveats=limitations,
            author_or_reviewer="system:cosing_importer",
            review_status=review_status,
            retrieved_at=cosing_rec.retrieved_at,
        )
        self.db.add(evidence)
        await self.db.flush()

        link = EvidenceSourceLink(
            evidence_id=evidence.id,
            research_record_id=research_rec.id,
            data_source_id=data_source.id,
            is_exact_match=is_exact,
            relevance_note=cosing_rec.match_note,
            quoted_excerpt=cosing_rec.chemical_description,
        )
        self.db.add(link)

        review_log = EvidenceReviewStatus(
            evidence_id=evidence.id,
            reviewer_user_id=reviewer_user.id if reviewer_user else None,
            previous_status="provisional",
            new_status=review_status,
            review_notes=cosing_rec.match_note,
            reviewed_at=cosing_rec.retrieved_at,
        )
        self.db.add(review_log)
        await self.db.flush()

        return True, was_deduped, not is_exact

    async def _ingest_pubmed_record(
        self,
        ingredient: Ingredient,
        pubmed_rec: PubMedArticleRecord,
        data_source: DataSource,
        topic: str,
        reviewer_user: User | None = None,
    ) -> tuple[bool, bool, bool]:
        """Idempotently persist a PubMed citation/abstract and link to IngredientEvidence."""
        # 1. Upsert ResearchRecord by (source_type='pubmed', external_id=pmid)
        rec_stmt = select(ResearchRecord).where(
            ResearchRecord.source_type == "pubmed",
            ResearchRecord.external_id == pubmed_rec.pmid,
        )
        rec_res = await self.db.execute(rec_stmt)
        research_rec = rec_res.scalar_one_or_none()
        was_deduped = research_rec is not None

        raw_meta = {
            "pmid": pubmed_rec.pmid,
            "mesh_terms": pubmed_rec.mesh_terms,
            "chemical_substances": pubmed_rec.chemical_substances,
            "publication_types": pubmed_rec.publication_types,
            "has_abstract": pubmed_rec.abstract_text is not None,
        }

        if research_rec is None:
            research_rec = ResearchRecord(
                source_type="pubmed",
                external_id=pubmed_rec.pmid,
                doi=pubmed_rec.doi,
                title=pubmed_rec.title,
                authors=pubmed_rec.authors,
                journal_or_authority=pubmed_rec.journal_title,
                publication_year=pubmed_rec.publication_year,
                publication_types=pubmed_rec.publication_types,
                study_type=pubmed_rec.study_type,
                abstract_text=pubmed_rec.abstract_text,
                has_full_text=False,
                source_url=pubmed_rec.source_url,
                license_or_attribution=pubmed_rec.attribution,
                raw_metadata=raw_meta,
                retrieved_at=pubmed_rec.retrieved_at,
            )
            self.db.add(research_rec)
            await self.db.flush()
        else:
            research_rec.retrieved_at = pubmed_rec.retrieved_at

        # 2. Check if already linked to this ingredient
        link_stmt = (
            select(EvidenceSourceLink)
            .join(IngredientEvidence, IngredientEvidence.id == EvidenceSourceLink.evidence_id)
            .where(
                IngredientEvidence.ingredient_id == ingredient.id,
                EvidenceSourceLink.research_record_id == research_rec.id,
            )
        )
        link_res = await self.db.execute(link_stmt)
        if link_res.scalar_one_or_none() is not None:
            return False, True, not pubmed_rec.is_exact_ingredient_match

        # 3. Evaluate abstract presence and ingredient match honesty
        is_exact = pubmed_rec.is_exact_ingredient_match
        has_abstract = bool(pubmed_rec.abstract_text and pubmed_rec.abstract_text.strip())

        if not is_exact:
            review_status = "incorrect_match_flagged"
            direction = "insufficient"
            strength = "insufficient"
        elif not has_abstract:
            review_status = "provisional"
            direction = "insufficient"
            strength = "insufficient"
        else:
            review_status = "provisional"
            direction = "neutral"
            strength = (
                "moderate"
                if pubmed_rec.study_type in ("rct", "meta_analysis", "systematic_review")
                else "preliminary"
            )

        if has_abstract and pubmed_rec.abstract_text:
            snippet = pubmed_rec.abstract_text[:450].strip()
            if len(pubmed_rec.abstract_text) > 450:
                snippet += "..."
            summary = (
                f"Published study ({pubmed_rec.study_type}, PMID {pubmed_rec.pmid}, "
                f"{pubmed_rec.publication_year or 'n.d.'}): {pubmed_rec.title}. "
                f"Abstract excerpt: {snippet}"
            )
        else:
            summary = (
                f"Bibliographic citation only (PMID {pubmed_rec.pmid}, "
                f"{pubmed_rec.publication_year or 'n.d.'}): {pubmed_rec.title}. "
                "No abstract text was available in PubMed E-utilities."
            )

        limitations_parts = [
            (
                "Retrieved via NCBI PubMed E-utilities as bibliographic metadata "
                "and abstract only (has_full_text=false)."
            ),
            "Do not treat an unreviewed abstract excerpt as a personal clinical conclusion.",
            (
                "Efficacy depends on formulation concentration, vehicle, and skin compatibility; "
                "concentration cannot be inferred from packaging ingredient order."
            ),
        ]
        if not has_abstract:
            limitations_parts.insert(
                0,
                (
                    "MISSING ABSTRACT: Only citation metadata was available; "
                    "study outcomes cannot be verified without full text."
                ),
            )
        if not is_exact:
            limitations_parts.insert(
                0,
                f"UNVERIFIED INGREDIENT MATCH: {pubmed_rec.match_note}",
            )

        evidence = IngredientEvidence(
            ingredient_id=ingredient.id,
            evidence_category="published_research",
            topic_or_target=topic[:150],
            evidence_direction=direction,
            evidence_strength=strength,
            study_type=pubmed_rec.study_type,
            population_or_context=pubmed_rec.population_or_context,
            summary_statement=summary,
            limitations_and_caveats=" ".join(limitations_parts),
            author_or_reviewer="system:pubmed_importer",
            review_status=review_status,
            retrieved_at=pubmed_rec.retrieved_at,
        )
        self.db.add(evidence)
        await self.db.flush()

        link = EvidenceSourceLink(
            evidence_id=evidence.id,
            research_record_id=research_rec.id,
            data_source_id=data_source.id,
            is_exact_match=is_exact,
            relevance_note=pubmed_rec.match_note,
            quoted_excerpt=pubmed_rec.abstract_text[:600] if pubmed_rec.abstract_text else None,
        )
        self.db.add(link)

        review_log = EvidenceReviewStatus(
            evidence_id=evidence.id,
            reviewer_user_id=reviewer_user.id if reviewer_user else None,
            previous_status="provisional",
            new_status=review_status,
            review_notes=pubmed_rec.match_note,
            reviewed_at=pubmed_rec.retrieved_at,
        )
        self.db.add(review_log)
        await self.db.flush()

        return True, was_deduped, not is_exact

    async def create_evidence_item(
        self,
        ingredient_id: UUID,
        payload: CreateEvidenceRequest,
        author_user: User,
    ) -> IngredientEvidenceItemResponse:
        """Create a human-reviewed interpretation or segregated marketing claim with provenance."""
        ingredient = await self._get_ingredient_or_404(ingredient_id)
        now = datetime.now(UTC)

        # Enforce marketing claim isolation rules
        direction = payload.evidence_direction
        strength = payload.evidence_strength
        limitations = payload.limitations_and_caveats
        if payload.evidence_category == "marketing_claim":
            direction = "reference_only"
            strength = "reference_only"
            if "marketing" not in limitations.lower():
                limitations = (
                    "COMMERCIAL MARKETING CLAIM (not peer-reviewed scientific evidence): "
                    f"{limitations}"
                )

        evidence = IngredientEvidence(
            ingredient_id=ingredient.id,
            evidence_category=payload.evidence_category,
            topic_or_target=payload.topic_or_target.strip(),
            evidence_direction=direction,
            evidence_strength=strength,
            study_type=payload.study_type,
            population_or_context=payload.population_or_context,
            summary_statement=payload.summary_statement.strip(),
            limitations_and_caveats=limitations.strip(),
            author_or_reviewer=f"user:{author_user.email}",
            review_status=payload.review_status,
            retrieved_at=now,
        )
        self.db.add(evidence)
        await self.db.flush()

        if payload.source_type and payload.external_id and payload.source_url:
            rec_stmt = select(ResearchRecord).where(
                ResearchRecord.source_type == payload.source_type.strip().lower(),
                ResearchRecord.external_id == payload.external_id.strip(),
            )
            rec_res = await self.db.execute(rec_stmt)
            research_rec = rec_res.scalar_one_or_none()
            if research_rec is None:
                research_rec = ResearchRecord(
                    source_type=payload.source_type.strip().lower(),
                    external_id=payload.external_id.strip(),
                    title=payload.source_title or payload.summary_statement[:120],
                    authors=[f"user:{author_user.email}"],
                    study_type=payload.study_type,
                    abstract_text=payload.quoted_excerpt,
                    has_full_text=False,
                    source_url=payload.source_url.strip(),
                    license_or_attribution="Curated citation / external reference link.",
                    retrieved_at=now,
                )
                self.db.add(research_rec)
                await self.db.flush()

            link = EvidenceSourceLink(
                evidence_id=evidence.id,
                research_record_id=research_rec.id,
                is_exact_match=True,
                relevance_note="Curated source link attached at creation.",
                quoted_excerpt=payload.quoted_excerpt,
            )
            self.db.add(link)

        review_log = EvidenceReviewStatus(
            evidence_id=evidence.id,
            reviewer_user_id=author_user.id,
            previous_status="provisional",
            new_status=payload.review_status,
            review_notes=f"Created in category '{payload.evidence_category}'.",
            reviewed_at=now,
        )
        self.db.add(review_log)
        await self.db.commit()

        return await self._get_single_evidence_response(evidence.id)

    async def update_evidence_review(
        self,
        ingredient_id: UUID,
        evidence_id: UUID,
        payload: UpdateEvidenceReviewRequest,
        reviewer_user: User,
    ) -> IngredientEvidenceItemResponse:
        """Transition review status and record audit trail in evidence_review_status."""
        stmt = select(IngredientEvidence).where(
            IngredientEvidence.id == evidence_id,
            IngredientEvidence.ingredient_id == ingredient_id,
        )
        res = await self.db.execute(stmt)
        evidence = res.scalar_one_or_none()
        if evidence is None:
            raise NotFoundError(
                f"Evidence record '{evidence_id}' for ingredient '{ingredient_id}' was not found."
            )

        prev_status = evidence.review_status
        evidence.review_status = payload.new_status
        evidence.author_or_reviewer = f"reviewer:{reviewer_user.email}"

        if payload.summary_statement_override:
            evidence.summary_statement = payload.summary_statement_override.strip()
        if payload.limitations_override:
            evidence.limitations_and_caveats = payload.limitations_override.strip()
        if payload.evidence_direction_override:
            evidence.evidence_direction = payload.evidence_direction_override
        if payload.evidence_strength_override:
            evidence.evidence_strength = payload.evidence_strength_override

        review_log = EvidenceReviewStatus(
            evidence_id=evidence.id,
            reviewer_user_id=reviewer_user.id,
            previous_status=prev_status,
            new_status=payload.new_status,
            review_notes=payload.review_notes,
            reviewed_at=datetime.now(UTC),
        )
        self.db.add(review_log)
        await self.db.commit()

        return await self._get_single_evidence_response(evidence.id)

    async def _get_single_evidence_response(
        self, evidence_id: UUID
    ) -> IngredientEvidenceItemResponse:
        stmt = (
            select(IngredientEvidence)
            .where(IngredientEvidence.id == evidence_id)
            .options(
                selectinload(IngredientEvidence.source_links).selectinload(
                    EvidenceSourceLink.research_record
                ),
                selectinload(IngredientEvidence.review_history),
            )
            .execution_options(populate_existing=True)
        )
        res = await self.db.execute(stmt)
        ev = res.scalar_one()
        return self._map_evidence_item(ev)

    def _map_evidence_item(self, ev: IngredientEvidence) -> IngredientEvidenceItemResponse:
        links_resp: list[EvidenceSourceLinkResponse] = []
        for link in ev.source_links:
            rec = link.research_record
            rec_resp = ResearchRecordResponse(
                id=rec.id,
                source_type=rec.source_type,
                external_id=rec.external_id,
                doi=rec.doi,
                title=rec.title,
                authors=rec.authors or [],
                journal_or_authority=rec.journal_or_authority,
                publication_year=rec.publication_year,
                publication_types=rec.publication_types or [],
                study_type=rec.study_type,
                abstract_text=rec.abstract_text,
                has_full_text=rec.has_full_text,
                source_url=rec.source_url,
                license_or_attribution=rec.license_or_attribution,
                raw_metadata=rec.raw_metadata or {},
                retrieved_at=rec.retrieved_at,
            )
            links_resp.append(
                EvidenceSourceLinkResponse(
                    id=link.id,
                    research_record_id=link.research_record_id,
                    data_source_id=link.data_source_id,
                    is_exact_match=link.is_exact_match,
                    relevance_note=link.relevance_note,
                    quoted_excerpt=link.quoted_excerpt,
                    research_record=rec_resp,
                )
            )

        history_resp = [
            EvidenceReviewStatusResponse(
                id=h.id,
                reviewer_user_id=h.reviewer_user_id,
                previous_status=h.previous_status,
                new_status=h.new_status,
                review_notes=h.review_notes,
                reviewed_at=h.reviewed_at,
            )
            for h in ev.review_history
        ]

        return IngredientEvidenceItemResponse(
            id=ev.id,
            ingredient_id=ev.ingredient_id,
            evidence_category=ev.evidence_category,
            topic_or_target=ev.topic_or_target,
            evidence_direction=ev.evidence_direction,
            evidence_strength=ev.evidence_strength,
            study_type=ev.study_type,
            population_or_context=ev.population_or_context,
            summary_statement=ev.summary_statement,
            limitations_and_caveats=ev.limitations_and_caveats,
            author_or_reviewer=ev.author_or_reviewer,
            review_status=ev.review_status,
            retrieved_at=ev.retrieved_at,
            source_links=links_resp,
            review_history=history_resp,
        )
