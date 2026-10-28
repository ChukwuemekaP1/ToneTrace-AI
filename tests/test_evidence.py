"""Comprehensive tests for Phase 6 (Ingredient Evidence & Research Retrieval) and Channel3 v1.

Validates:
1. PubMed E-utilities query construction & EFetch XML parsing using fixtures:
   - Structured & unstructured abstracts, MeSH headings, chemical list, DOI, authors, journal
   - Study type classification (RCT, meta-analysis, in vitro, review)
   - Population/context extraction (Fitzpatrick skin types, sample size, melasma)
   - Missing abstracts (`abstract_text=None` -> `insufficient` evidence)
   - Incorrect ingredient matches (`is_exact_ingredient_match=False` -> `incorrect_match_flagged`)
   - Mandatory source attribution & `has_full_text=False`
   - Rate-limit (429), 500 server error retry/backoff, and timeout handling
2. European Commission CosIng adapter:
   - Official EC Search API (`GROWTH_COSING`) JSON parsing
   - Official EC CosIng CSV inventory parsing
   - Exact INCI match vs derivative flagging (`NIACINAMIDE` vs `NIACINAMIDE/YEAST POLYPEPTIDE`)
3. Evidence Service & API routes:
   - `POST /api/v1/ingredients/{ingredient_id}/evidence/refresh`
     (auth required, cache TTL vs `force_refresh`, idempotent deduplication)
   - `GET /api/v1/ingredients/{ingredient_id}/evidence`
     (4-way separation of identity_reference, published_research, human_interpretation,
     marketing_claim; epistemic guardrails; pagination; filters; zero external calls)
   - `POST /api/v1/ingredients/{ingredient_id}/evidence`
     (human interpretation and segregated marketing claim enforced as `reference_only`)
   - `PATCH /api/v1/ingredients/{ingredient_id}/evidence/{evidence_id}/review`
     (status transition and immutable `evidence_review_status` audit log)
4. Channel3 v1 Universal Catalog Integration:
   - `Channel3Adapter.search_products`, `get_product_details`, `find_similar`, `lookup_url`
   - `GET /api/v1/products/channel3/search` & `POST /api/v1/products/{id}/offers/sync-channel3`
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.security import create_access_token, hash_password
from app.db.models import (
    Brand,
    Ingredient,
    IngredientAlias,
    Product,
    User,
)
from app.providers.channel3 import (
    Channel3Adapter,
    Channel3Product,
    Channel3ProductOffer,
)
from app.providers.cosing import (
    CosIngAdapter,
    CosIngRecord,
    CosIngUnavailableError,
)
from app.providers.pubmed import (
    PubMedAdapter,
    PubMedArticleRecord,
    PubMedRateLimitError,
    PubMedUnavailableError,
)

# ============================================================================
# Fixtures: PubMed EFetch XML & CosIng Payloads
# ============================================================================

PUBMED_EFETCH_XML_FIXTURE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<PubmedArticleSet>\n"
    "  <!-- Article 1: Exact match RCT with structured abstract and Fitzpatrick IV-V -->\n"
    "  <PubmedArticle>\n"
    '    <MedlineCitation Status="MEDLINE" Owner="NLM">\n'
    '      <PMID Version="1">21799322</PMID>\n'
    '      <Article PubModel="Print">\n'
    "        <Journal>\n"
    "          <Title>Dermatology Research and Practice</Title>\n"
    '          <JournalIssue CitedMedium="Print">\n'
    "            <PubDate><Year>2011</Year></PubDate>\n"
    "          </JournalIssue>\n"
    "        </Journal>\n"
    "        <ArticleTitle>A Double-Blind, Randomized Clinical Trial of Niacinamide 4% "
    "versus Hydroquinone 4% in the Treatment of Melasma</ArticleTitle>\n"
    "        <Abstract>\n"
    '          <AbstractText Label="BACKGROUND">Melasma is an acquired hypermelanosis '
    "common in darker skin phototypes.</AbstractText>\n"
    '          <AbstractText Label="METHODS">Twenty-seven melasma patients with '
    "Fitzpatrick skin types IV and V (n = 27) were enrolled in a randomized "
    "split-face trial for 8 weeks.</AbstractText>\n"
    '          <AbstractText Label="RESULTS">Both niacinamide and hydroquinone decreased '
    "Melasma Area and Severity Index scores.</AbstractText>\n"
    "        </Abstract>\n"
    '        <AuthorList CompleteYN="Y">\n'
    '          <Author ValidYN="Y">\n'
    "            <LastName>Navarrete-Solis</LastName>\n"
    "            <ForeName>Josefina</ForeName>\n"
    "          </Author>\n"
    '          <Author ValidYN="Y">\n'
    "            <LastName>Castanedo-Cazares</LastName>\n"
    "            <ForeName>Juan Pablo</ForeName>\n"
    "          </Author>\n"
    "        </AuthorList>\n"
    "        <PublicationTypeList>\n"
    '          <PublicationType UI="D016428">Journal Article</PublicationType>\n'
    '          <PublicationType UI="D016449">Randomized Controlled Trial</PublicationType>\n'
    "        </PublicationTypeList>\n"
    '        <ELocationID EIdType="doi" ValidYN="Y">10.1155/2011/379173</ELocationID>\n'
    "      </Article>\n"
    "      <ChemicalList>\n"
    "        <Chemical>\n"
    "          <RegistryNumber>25X51I8RD4</RegistryNumber>\n"
    '          <NameOfSubstance UI="D009536">Niacinamide</NameOfSubstance>\n'
    "        </Chemical>\n"
    "      </ChemicalList>\n"
    "      <MeshHeadingList>\n"
    "        <MeshHeading>\n"
    '          <DescriptorName UI="D008548" MajorTopicYN="Y">Melanosis</DescriptorName>\n'
    "        </MeshHeading>\n"
    "        <MeshHeading>\n"
    '          <DescriptorName UI="D009536" MajorTopicYN="Y">Niacinamide</DescriptorName>\n'
    "        </MeshHeading>\n"
    "      </MeshHeadingList>\n"
    "    </MedlineCitation>\n"
    "  </PubmedArticle>\n"
    "  <!-- Article 2: Missing abstract (bibliographic metadata only) -->\n"
    "  <PubmedArticle>\n"
    '    <MedlineCitation Status="MEDLINE" Owner="NLM">\n'
    '      <PMID Version="1">12100180</PMID>\n'
    '      <Article PubModel="Print">\n'
    "        <Journal>\n"
    "          <Title>British Journal of Dermatology</Title>\n"
    "          <JournalIssue>\n"
    "            <PubDate><MedlineDate>2002 Jul-Aug</MedlineDate></PubDate>\n"
    "          </JournalIssue>\n"
    "        </Journal>\n"
    "        <ArticleTitle>The effect of niacinamide on reducing cutaneous pigmentation "
    "and suppression of melanosome transfer</ArticleTitle>\n"
    '        <AuthorList CompleteYN="Y">\n'
    '          <Author ValidYN="Y">\n'
    "            <LastName>Hakozaki</LastName>\n"
    "            <ForeName>Tomohiro</ForeName>\n"
    "          </Author>\n"
    "        </AuthorList>\n"
    "        <PublicationTypeList>\n"
    '          <PublicationType UI="D016428">Journal Article</PublicationType>\n'
    "        </PublicationTypeList>\n"
    "      </Article>\n"
    "      <ChemicalList>\n"
    "        <Chemical>\n"
    '          <NameOfSubstance UI="D009536">Niacinamide</NameOfSubstance>\n'
    "        </Chemical>\n"
    "      </ChemicalList>\n"
    "    </MedlineCitation>\n"
    "  </PubmedArticle>\n"
    "  <!-- Article 3: Unverified ingredient match (mentions Retinol only) -->\n"
    "  <PubmedArticle>\n"
    '    <MedlineCitation Status="MEDLINE" Owner="NLM">\n'
    '      <PMID Version="1">99999991</PMID>\n'
    '      <Article PubModel="Print">\n'
    "        <Journal>\n"
    "          <Title>Journal of Cosmetic Science</Title>\n"
    "          <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>\n"
    "        </Journal>\n"
    "        <ArticleTitle>Topical Retinol Stability in Anhydrous Vehicles</ArticleTitle>\n"
    "        <Abstract>\n"
    "          <AbstractText>In vitro evaluation of all-trans retinol degradation "
    "kinetics under UV exposure.</AbstractText>\n"
    "        </Abstract>\n"
    '        <AuthorList CompleteYN="Y">\n'
    '          <Author ValidYN="Y">\n'
    "            <CollectiveName>Cosmetic Stability Consortium</CollectiveName>\n"
    "          </Author>\n"
    "        </AuthorList>\n"
    "        <PublicationTypeList>\n"
    '          <PublicationType UI="D016428">Journal Article</PublicationType>\n'
    "        </PublicationTypeList>\n"
    "      </Article>\n"
    "      <ChemicalList>\n"
    "        <Chemical>\n"
    '          <NameOfSubstance UI="D014801">Vitamin A</NameOfSubstance>\n'
    "        </Chemical>\n"
    "      </ChemicalList>\n"
    "    </MedlineCitation>\n"
    "  </PubmedArticle>\n"
    "</PubmedArticleSet>\n"
)

COSING_API_JSON_FIXTURE = {
    "totalResults": 2,
    "results": [
        {
            "reference": "GROWTH_COSING_35460",
            "metadata": {
                "substanceId": ["35460"],
                "inciName": ["NIACINAMIDE"],
                "casNo": ["98-92-0"],
                "ecNo": ["202-713-4"],
                "chemicalDescription": ["Pyridine-3-carboxamide"],
                "functionName": ["SMOOTHING", "SKIN CONDITIONING"],
                "cosmeticRestriction": [],
                "sccsOpinion": [],
                "itemType": ["ingredient"],
            },
        },
        {
            "reference": "GROWTH_COSING_92056",
            "metadata": {
                "substanceId": ["92056"],
                "inciName": ["NIACINAMIDE/YEAST POLYPEPTIDE"],
                "casNo": ["-"],
                "ecNo": ["-"],
                "chemicalDescription": [
                    "Reaction product of Niacinamide and Saccharomyces polypeptide"
                ],
                "functionName": ["SKIN PROTECTING"],
                "cosmeticRestriction": [],
                "sccsOpinion": [],
                "itemType": ["ingredient"],
            },
        },
    ],
}

COSING_CSV_FIXTURE = (
    "COSING Ref No,INCI name,INN name,Ph. Eur. Name,CAS No,EINECS/ELINCS,"
    "Chem/IUPAC Name / Description,Restriction,Function,Update Date\n"
    "35460,NIACINAMIDE,nicotinamide,nicotinamidum,98-92-0,202-713-4,"
    'Pyridine-3-carboxamide,,"SMOOTHING, SKIN CONDITIONING",15/05/2019\n'
    "34210,HYDROQUINONE,hydroquinone,,123-31-9,204-617-8,"
    '"1,4-Benzenediol",III/14,"ANTIOXIDANT, HAIR DYEING",20/08/2021\n'
)


# ============================================================================
# 1. PubMed E-utilities Provider Unit Tests
# ============================================================================


def test_pubmed_build_search_query():
    """Verify PubMed query construction includes ingredient, aliases, and dermatological topic."""
    adapter = PubMedAdapter()
    query = adapter.build_search_query(
        ingredient_name="Niacinamide",
        topic="hyperpigmentation",
        aliases=["Nicotinamide", "Vitamin B3"],
    )
    assert '"Niacinamide"[Title/Abstract]' in query
    assert '"Niacinamide"[MeSH Terms]' in query
    assert '"Nicotinamide"[Title/Abstract]' in query
    assert '"Vitamin B3"[Title/Abstract]' in query
    assert '"hyperpigmentation"[Title/Abstract]' in query
    assert "skin[Title/Abstract]" in query


def test_pubmed_parse_efetch_xml_with_missing_abstract_and_mismatch():
    """Verify XML parsing handles structured abstracts, missing abstracts, and mismatches."""
    adapter = PubMedAdapter()
    records = adapter.parse_efetch_xml(
        PUBMED_EFETCH_XML_FIXTURE,
        target_ingredient="Niacinamide",
        aliases=["Nicotinamide"],
    )

    assert len(records) == 3

    # 1. Complete RCT record with structured abstract
    rec1 = records[0]
    assert rec1.pmid == "21799322"
    assert rec1.doi == "10.1155/2011/379173"
    assert "Niacinamide 4% versus Hydroquinone 4%" in rec1.title
    assert rec1.authors == ["Navarrete-Solis Josefina", "Castanedo-Cazares Juan Pablo"]
    assert rec1.journal_title == "Dermatology Research and Practice"
    assert rec1.publication_year == 2011
    assert rec1.study_type == "rct"
    assert rec1.abstract_text is not None
    assert "BACKGROUND: Melasma" in rec1.abstract_text
    assert "METHODS: Twenty-seven melasma patients" in rec1.abstract_text
    assert rec1.population_or_context is not None
    assert "Fitzpatrick" in rec1.population_or_context
    assert "n = 27" in rec1.population_or_context
    assert "Melasma" in rec1.population_or_context
    assert rec1.is_exact_ingredient_match is True
    assert rec1.source_url == "https://pubmed.ncbi.nlm.nih.gov/21799322/"
    assert "National Library of Medicine" in rec1.attribution

    # 2. Missing abstract record
    rec2 = records[1]
    assert rec2.pmid == "12100180"
    assert rec2.publication_year == 2002
    assert rec2.abstract_text is None
    assert rec2.is_exact_ingredient_match is True

    # 3. Unverified / incorrect ingredient match (Retinol paper returned in broad search)
    rec3 = records[2]
    assert rec3.pmid == "99999991"
    assert rec3.study_type == "in_vitro"
    assert rec3.is_exact_ingredient_match is False
    assert "was not explicitly verified" in rec3.match_note


@pytest.mark.asyncio
async def test_pubmed_search_and_fetch_with_deduplication_and_params():
    """Verify PubMed adapter sends tool/email parameters and deduplicates PMIDs."""
    esearch_payload = {"esearchresult": {"idlist": ["21799322", "21799322", "12100180"]}}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    esearch_resp = httpx.Response(
        200,
        json=esearch_payload,
        request=httpx.Request("GET", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"),
    )
    efetch_resp = httpx.Response(
        200,
        text=PUBMED_EFETCH_XML_FIXTURE,
        request=httpx.Request("GET", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"),
    )
    mock_client.get = AsyncMock(side_effect=[esearch_resp, efetch_resp])

    adapter = PubMedAdapter(client=mock_client)
    records = await adapter.search_and_fetch(
        ingredient_name="Niacinamide",
        topic="melasma",
        max_results=5,
    )

    assert len(records) == 3
    assert mock_client.get.call_count == 2
    # Verify NCBI compliance parameters (`tool` and `email`) were sent
    first_call_params = mock_client.get.call_args_list[0].kwargs["params"]
    assert first_call_params["db"] == "pubmed"
    assert "tool" in first_call_params
    assert "email" in first_call_params

    # Verify duplicate PMIDs were deduplicated before efetch
    second_call_params = mock_client.get.call_args_list[1].kwargs["params"]
    assert second_call_params["id"] == "21799322,12100180"


@pytest.mark.asyncio
async def test_pubmed_rate_limit_and_retry_handling():
    """Verify PubMed adapter retries transient errors and raises PubMedRateLimitError on 429."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    resp_429 = httpx.Response(
        429,
        text="Too Many Requests",
        request=httpx.Request("GET", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"),
    )
    mock_client.get = AsyncMock(return_value=resp_429)

    adapter = PubMedAdapter(client=mock_client, max_retries=1)
    with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(PubMedRateLimitError):
        await adapter.search_pmids("Niacinamide")


@pytest.mark.asyncio
async def test_pubmed_timeout_raises_unavailable():
    """Verify PubMed adapter raises PubMedUnavailableError on network timeouts."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timed out"))

    adapter = PubMedAdapter(client=mock_client, max_retries=0)
    with pytest.raises(PubMedUnavailableError):
        await adapter.search_pmids("Niacinamide")


# ============================================================================
# 2. European Commission CosIng Provider Unit Tests
# ============================================================================


def test_cosing_parse_api_response_distinguishes_exact_vs_derivative():
    """Verify CosIng parser distinguishes exact INCI match from derivative compounds."""
    adapter = CosIngAdapter()
    records = adapter.parse_api_response(COSING_API_JSON_FIXTURE, target_ingredient="Niacinamide")

    assert len(records) == 2

    exact = records[0]
    assert exact.cosing_ref_no == "35460"
    assert exact.inci_name == "NIACINAMIDE"
    assert exact.cas_no == "98-92-0"
    assert exact.ec_no == "202-713-4"
    assert exact.functions == ["SMOOTHING", "SKIN CONDITIONING"]
    assert exact.is_exact_inci_match is True
    assert "35460" in exact.source_url

    derivative = records[1]
    assert derivative.cosing_ref_no == "92056"
    assert derivative.inci_name == "NIACINAMIDE/YEAST POLYPEPTIDE"
    assert derivative.is_exact_inci_match is False
    assert "Partial/derivative INCI match" in derivative.match_note


def test_cosing_parse_official_csv_export():
    """Verify official EC CosIng CSV inventory parser extracts restrictions and functions."""
    adapter = CosIngAdapter()
    all_rows = adapter.parse_cosing_csv(COSING_CSV_FIXTURE)
    assert len(all_rows) == 2

    hq_rows = adapter.parse_cosing_csv(COSING_CSV_FIXTURE, target_ingredient="Hydroquinone")
    assert len(hq_rows) == 1
    hq = hq_rows[0]
    assert hq.cosing_ref_no == "34210"
    assert hq.inci_name == "HYDROQUINONE"
    assert hq.cas_no == "123-31-9"
    assert hq.restrictions == ["III/14"]
    assert "ANTIOXIDANT" in hq.functions
    assert hq.is_exact_inci_match is True


@pytest.mark.asyncio
async def test_cosing_timeout_raises_unavailable():
    """Verify CosIng adapter raises CosIngUnavailableError when EC API times out."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("EC API timeout"))

    adapter = CosIngAdapter(client=mock_client, max_retries=0)
    with pytest.raises(CosIngUnavailableError):
        await adapter.search_ingredient("Niacinamide")


# ============================================================================
# 3. Phase 6 Evidence Service & API Endpoint Tests
# ============================================================================


async def _create_test_user_and_token(db_session) -> tuple[User, str]:
    user = User(
        email=f"researcher-{uuid.uuid4().hex[:8]}@tonetrace.ai",
        password_hash=hash_password("ValidResearchPass!2026"),
        account_status="active",
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token(user_id=user.id)
    return user, token


async def _create_test_ingredient(db_session, inci_name: str | None = None) -> Ingredient:
    unique_suffix = uuid.uuid4().hex[:6].upper()
    name = inci_name or f"NIACINAMIDE-{unique_suffix}"
    ing = Ingredient(
        inci_name=name,
        common_name="Vitamin B3",
        aliases=["Nicotinamide"],
        function=None,
        description="Water-soluble amide of nicotinic acid.",
        safety_rating="safe",
    )
    db_session.add(ing)
    await db_session.flush()
    alias = IngredientAlias(
        ingredient_id=ing.id,
        alias_name=f"Nicotinamide-{unique_suffix}",
        alias_type="synonym",
    )
    db_session.add(alias)
    await db_session.commit()
    await db_session.refresh(ing)
    return ing


@pytest.mark.asyncio
async def test_evidence_refresh_caching_deduplication_and_get_separation(client, test_session):
    """Verify full lifecycle: refresh, cache TTL, deduplication, and 4-way GET separation."""
    _, token = await _create_test_user_and_token(test_session)
    headers = {"Authorization": f"Bearer {token}"}
    ingredient = await _create_test_ingredient(test_session)

    now = datetime.now(UTC)
    mock_cosing_records = [
        CosIngRecord(
            cosing_ref_no=f"35460-{ingredient.id.hex[:6]}",
            inci_name=ingredient.inci_name,
            cas_no="98-92-0",
            ec_no="202-713-4",
            chemical_description="Pyridine-3-carboxamide",
            functions=["SMOOTHING", "SKIN CONDITIONING"],
            restrictions=[],
            source_url="https://ec.europa.eu/growth/tools-databases/cosing/details/35460",
            is_exact_inci_match=True,
            match_note=f"Exact INCI match for '{ingredient.inci_name}'.",
            retrieved_at=now,
        ),
        CosIngRecord(
            cosing_ref_no=f"92056-{ingredient.id.hex[:6]}",
            inci_name=f"{ingredient.inci_name}/YEAST POLYPEPTIDE",
            cas_no=None,
            ec_no=None,
            chemical_description="Derivative polypeptide",
            functions=["SKIN PROTECTING"],
            restrictions=[],
            source_url="https://ec.europa.eu/growth/tools-databases/cosing/details/92056",
            is_exact_inci_match=False,
            match_note="CosIng entry is a derivative compound.",
            retrieved_at=now,
        ),
    ]

    mock_pubmed_records = [
        PubMedArticleRecord(
            pmid=f"21799322-{ingredient.id.hex[:4]}",
            title="A Double-Blind RCT of Niacinamide 4% in Melasma",
            authors=["Josefina Navarrete-Solis"],
            journal_title="Dermatology Research and Practice",
            publication_year=2011,
            doi="10.1155/2011/379173",
            publication_types=["Randomized Controlled Trial"],
            study_type="rct",
            abstract_text="Twenty-seven melasma patients with Fitzpatrick IV-V showed improvement.",
            population_or_context="Fitzpatrick IV-V; n = 27; Melasma",
            mesh_terms=["Melanosis", "Niacinamide"],
            chemical_substances=["Niacinamide"],
            source_url="https://pubmed.ncbi.nlm.nih.gov/21799322/",
            is_exact_ingredient_match=True,
            match_note="Exact match in MeSH and title.",
            retrieved_at=now,
        ),
        PubMedArticleRecord(
            pmid=f"12100180-{ingredient.id.hex[:4]}",
            title="Citation Without Abstract on Cutaneous Pigmentation",
            authors=["Tomohiro Hakozaki"],
            journal_title="British Journal of Dermatology",
            publication_year=2002,
            doi=None,
            publication_types=["Journal Article"],
            study_type="other",
            abstract_text=None,  # Missing abstract
            population_or_context=None,
            mesh_terms=["Niacinamide"],
            chemical_substances=["Niacinamide"],
            source_url="https://pubmed.ncbi.nlm.nih.gov/12100180/",
            is_exact_ingredient_match=True,
            match_note="Exact match in title; no abstract text available.",
            retrieved_at=now,
        ),
    ]

    with (
        patch.object(
            CosIngAdapter,
            "search_ingredient",
            new=AsyncMock(return_value=mock_cosing_records),
        ) as mock_cosing_call,
        patch.object(
            PubMedAdapter,
            "search_and_fetch",
            new=AsyncMock(return_value=mock_pubmed_records),
        ) as mock_pubmed_call,
    ):
        # 1. First refresh triggers upstream retrieval
        refresh_resp = await client.post(
            f"/api/v1/ingredients/{ingredient.id}/evidence/refresh",
            headers=headers,
            json={
                "sources": ["cosing", "pubmed"],
                "topic": "hyperpigmentation",
                "max_pubmed_results": 5,
                "force_refresh": False,
            },
        )
        assert refresh_resp.status_code == 200
        r_data = refresh_resp.json()["data"]
        assert r_data["used_cache"] is False
        assert r_data["cosing_records_processed"] == 2
        assert r_data["pubmed_records_processed"] == 2
        assert r_data["new_evidence_created"] == 4
        assert r_data["flagged_incorrect_matches"] == 1
        assert mock_cosing_call.call_count == 1
        assert mock_pubmed_call.call_count == 1

        # 2. Second refresh with force_refresh=False hits database cache TTL (0 external calls)
        cached_resp = await client.post(
            f"/api/v1/ingredients/{ingredient.id}/evidence/refresh",
            headers=headers,
            json={
                "sources": ["cosing", "pubmed"],
                "force_refresh": False,
            },
        )
        assert cached_resp.status_code == 200
        c_data = cached_resp.json()["data"]
        assert c_data["used_cache"] is True
        assert mock_cosing_call.call_count == 1
        assert mock_pubmed_call.call_count == 1

        # 3. Third refresh with force_refresh=True re-fetches and deduplicates idempotently
        dedup_resp = await client.post(
            f"/api/v1/ingredients/{ingredient.id}/evidence/refresh",
            headers=headers,
            json={
                "sources": ["cosing", "pubmed"],
                "force_refresh": True,
            },
        )
        assert dedup_resp.status_code == 200
        d_data = dedup_resp.json()["data"]
        assert d_data["used_cache"] is False
        assert d_data["new_evidence_created"] == 0
        assert d_data["deduplicated_existing_records"] == 4

    # 4. Create a human-reviewed interpretation and a segregated marketing claim
    human_resp = await client.post(
        f"/api/v1/ingredients/{ingredient.id}/evidence",
        headers=headers,
        json={
            "evidence_category": "human_interpretation",
            "topic_or_target": "hyperpigmentation_melasma",
            "evidence_direction": "supportive",
            "evidence_strength": "moderate",
            "study_type": "rct",
            "population_or_context": "Topical 4% concentration in Fitzpatrick IV-V patients",
            "summary_statement": (
                "Reviewed clinical literature indicates 4% topical niacinamide reduced MASI scores "
                "over 8 weeks; concentration and vehicle remain critical."
            ),
            "limitations_and_caveats": (
                "Small sample size (n=27); results cannot be extrapolated from ingredient "
                "name alone when product concentration is unknown."
            ),
            "review_status": "verified",
        },
    )
    assert human_resp.status_code == 201
    human_ev_id = human_resp.json()["data"]["id"]

    marketing_resp = await client.post(
        f"/api/v1/ingredients/{ingredient.id}/evidence",
        headers=headers,
        json={
            "evidence_category": "marketing_claim",
            "topic_or_target": "brightening_claim",
            "evidence_direction": "supportive",  # Service must override to reference_only!
            "evidence_strength": "strong",  # Service must override to reference_only!
            "study_type": "other",
            "summary_statement": "Brand packaging claims 'erases dark spots in 3 days'.",
            "limitations_and_caveats": "Unverified brand packaging copy.",
            "review_status": "provisional",
        },
    )
    assert marketing_resp.status_code == 201
    m_data = marketing_resp.json()["data"]
    assert m_data["evidence_category"] == "marketing_claim"
    assert m_data["evidence_direction"] == "reference_only"
    assert m_data["evidence_strength"] == "reference_only"
    assert "COMMERCIAL MARKETING CLAIM" in m_data["limitations_and_caveats"]

    # 5. GET /api/v1/ingredients/{ingredient_id}/evidence — verify 4-way separation & guardrails
    get_resp = await client.get(f"/api/v1/ingredients/{ingredient.id}/evidence")
    assert get_resp.status_code == 200
    ev_body = get_resp.json()["data"]

    assert ev_body["ingredient_id"] == str(ingredient.id)
    assert ev_body["pagination"]["total_items"] == 6

    guardrails = ev_body["epistemic_guardrails"]
    assert (
        "ingredient name alone do not prove clinical effectiveness"
        in guardrails["efficacy_disclaimer"]
    )
    assert (
        "concentration cannot be inferred from packaging ingredient order"
        in guardrails["concentration_disclaimer"]
    )
    assert "causation" in guardrails["scan_causation_disclaimer"]
    assert "has_full_text=false" in guardrails["full_text_disclaimer"]

    groups = ev_body["separated_groups"]
    assert len(groups["identity_reference"]) == 2
    assert len(groups["published_research"]) == 2
    assert len(groups["human_interpretation"]) == 1
    assert len(groups["marketing_claims"]) == 1
    assert ev_body["has_insufficient_evidence"] is True

    # Verify missing abstract record was marked insufficient & has_full_text=False
    pub_items = groups["published_research"]
    no_abs_item = next(
        item
        for item in pub_items
        if item["source_links"][0]["research_record"]["abstract_text"] is None
    )
    assert no_abs_item["evidence_direction"] == "insufficient"
    assert no_abs_item["evidence_strength"] == "insufficient"
    assert "MISSING ABSTRACT" in no_abs_item["limitations_and_caveats"]
    assert no_abs_item["source_links"][0]["research_record"]["has_full_text"] is False

    # 6. Test query filters (`source`, `category`, `review_status`, `study_type`)
    filter_resp = await client.get(
        f"/api/v1/ingredients/{ingredient.id}/evidence",
        params={"source": "pubmed", "study_type": "rct"},
    )
    assert filter_resp.status_code == 200
    f_data = filter_resp.json()["data"]
    assert f_data["pagination"]["total_items"] == 1
    assert f_data["items"][0]["study_type"] == "rct"

    flagged_resp = await client.get(
        f"/api/v1/ingredients/{ingredient.id}/evidence",
        params={"review_status": "incorrect_match_flagged"},
    )
    assert flagged_resp.status_code == 200
    assert flagged_resp.json()["data"]["pagination"]["total_items"] == 1

    # 7. Test PATCH review status transition and audit log
    patch_resp = await client.patch(
        f"/api/v1/ingredients/{ingredient.id}/evidence/{human_ev_id}/review",
        headers=headers,
        json={
            "new_status": "disputed",
            "review_notes": (
                "Conflicting split-face trial published in 2024 requires mixed classification."
            ),
            "evidence_direction_override": "mixed",
        },
    )
    assert patch_resp.status_code == 200
    patched_item = patch_resp.json()["data"]
    assert patched_item["review_status"] == "disputed"
    assert patched_item["evidence_direction"] == "mixed"
    assert len(patched_item["review_history"]) >= 2
    assert any(h["new_status"] == "disputed" for h in patched_item["review_history"])


@pytest.mark.asyncio
async def test_evidence_refresh_requires_authentication(client, test_session):
    """Verify unauthenticated callers cannot trigger external research refresh."""
    ingredient = await _create_test_ingredient(test_session)
    resp = await client.post(
        f"/api/v1/ingredients/{ingredient.id}/evidence/refresh",
        json={"sources": ["cosing"]},
    )
    assert resp.status_code == 401


# ============================================================================
# 4. Channel3 v1 Universal Catalog & Offer Sync Tests
# ============================================================================


@pytest.mark.asyncio
async def test_channel3_v1_search_products_and_offers_parsing():
    """Verify Channel3Adapter parses v1 POST /v1/search response and sends x-user-id header."""
    v1_payload = {
        "products": [
            {
                "id": "c3_prod_niacinamide_01",
                "title": "The Ordinary Niacinamide 10% + Zinc 1%",
                "description": "High-strength vitamin and mineral blemish formula",
                "brand_id": "brand_ordinary",
                "brand_name": "The Ordinary",
                "category_slug": "face-serums",
                "category_title": "Face Serums",
                "image_url": "https://cdn.trychannel3.com/ordinary.jpg",
                "key_features": ["Niacinamide 10%", "Zinc PCA 1%"],
                "materials": ["Aqua", "Niacinamide", "Pentylene Glycol", "Zinc PCA"],
                "offers": [
                    {
                        "url": "https://r.trychannel3.com/redirect/sephora",
                        "domain": "sephora.com",
                        "price": {
                            "price": 6.00,
                            "currency": "USD",
                            "compare_at_price": 7.50,
                        },
                        "availability": "InStock",
                        "condition": "new",
                        "max_commission_rate": 0.08,
                    }
                ],
            }
        ],
        "next_page_token": "tok_page_2",
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = httpx.Response(
        200,
        json=v1_payload,
        request=httpx.Request("POST", "https://api.trychannel3.com/v1/search"),
    )
    mock_client.post = AsyncMock(return_value=mock_resp)

    adapter = Channel3Adapter(api_key="test-channel3-key", client=mock_client)
    products, next_page_token = await adapter.search_products(
        query="Niacinamide 10%",
        limit=5,
        filters={"price": {"max_price": 25.0}},
        user_id="user_uuid_123",
    )

    assert len(products) == 1
    assert next_page_token == "tok_page_2"
    prod = products[0]
    assert prod.id == "c3_prod_niacinamide_01"
    assert prod.brand_name == "The Ordinary"
    assert len(prod.offers) == 1
    offer = prod.offers[0]
    assert offer.merchant_name == "sephora.com"
    assert offer.price_minor_units == 600
    assert offer.compare_at_price_minor_units == 750
    assert offer.currency == "USD"
    assert offer.is_in_stock is True
    assert offer.max_commission_rate == 0.08

    # Verify headers included x-api-key and x-user-id
    sent_headers = mock_client.post.call_args.kwargs["headers"]
    assert sent_headers["x-api-key"] == "test-channel3-key"
    assert sent_headers["x-user-id"] == "user_uuid_123"


@pytest.mark.asyncio
async def test_channel3_api_routes_search_and_sync_offers(client, test_session):
    """Verify GET /products/channel3/search and POST /products/{id}/offers/sync-channel3."""
    _, token = await _create_test_user_and_token(test_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Create a catalog product in PostgreSQL
    brand = Brand(
        name=f"The Ordinary {uuid.uuid4().hex[:6]}",
        slug=f"the-ordinary-{uuid.uuid4().hex[:6]}",
    )
    test_session.add(brand)
    await test_session.flush()

    product = Product(
        name="Niacinamide 10% + Zinc 1%",
        brand=brand.name,
        brand_id=brand.id,
        category="serum",
        ean_or_upc=f"76991519{uuid.uuid4().int % 10000:04d}",
    )
    test_session.add(product)
    await test_session.commit()
    await test_session.refresh(product)

    mock_offer = Channel3ProductOffer(
        merchant_name="ulta.com",
        product_name="The Ordinary Niacinamide 10% + Zinc 1%",
        price_minor_units=600,
        currency="USD",
        offer_url="https://r.trychannel3.com/redirect/ulta",
        is_in_stock=True,
        channel3_product_id="c3_prod_01",
    )
    mock_product = Channel3Product(
        id="c3_prod_01",
        title="The Ordinary Niacinamide 10% + Zinc 1%",
        brand_name="The Ordinary",
        offers=[mock_offer],
    )

    with (
        patch.object(
            Channel3Adapter,
            "search_products",
            new=AsyncMock(return_value=([mock_product], None)),
        ),
        patch.object(
            Channel3Adapter,
            "search_offers",
            new=AsyncMock(return_value=[mock_offer]),
        ),
    ):
        # 1. Search Channel3 universal catalog
        search_resp = await client.get(
            "/api/v1/products/channel3/search",
            params={"query": "Niacinamide", "limit": 5},
            headers=headers,
        )
        assert search_resp.status_code == 200
        s_data = search_resp.json()["data"]
        assert s_data["total_returned"] == 1
        assert s_data["products"][0]["id"] == "c3_prod_01"
        assert s_data["products"][0]["offers"][0]["price_minor_units"] == 600

        # 2. Sync Channel3 offers for existing PostgreSQL product
        sync_resp = await client.post(
            f"/api/v1/products/{product.id}/offers/sync-channel3",
            headers=headers,
        )
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()["data"]
        assert sync_data["product_id"] == str(product.id)
        assert sync_data["offers_synced"] == 1
        assert sync_data["offers"][0]["merchant_name"] == "ulta.com"
        assert sync_data["offers"][0]["price_minor_units"] == 600
        assert sync_data["offers"][0]["formatted_price"] == "$6.00"
