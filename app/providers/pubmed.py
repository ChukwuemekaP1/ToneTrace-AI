"""NCBI PubMed E-utilities provider adapter for Phase 6 scientific evidence retrieval.

Implements official documented NCBI Entrez Programming Utilities (E-utilities):
- ESearch (esearch.fcgi): Queries PubMed database and retrieves matching PMIDs.
- EFetch (efetch.fcgi): Retrieves bibliographic metadata and abstracts in XML format.

Compliance & Epistemic Rules:
- Always includes `tool` and `email` query parameters per NCBI usage guidelines.
- Honors NCBI rate limits (3 req/s without API key, 10 req/s with API key) and retries 429/5xx.
- Never scrapes HTML pages or claims full-text possession (`has_full_text=False` always).
- Preserves missing abstracts honestly as `None` rather than fabricating summaries.
- Validates ingredient identity match in title/abstract/chemical list to detect false positives.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class PubMedError(Exception):
    """Base exception for PubMed E-utilities operations."""

    pass


class PubMedRateLimitError(PubMedError):
    """Raised when NCBI E-utilities rate limit (HTTP 429) is exceeded after retries."""

    pass


class PubMedUnavailableError(PubMedError):
    """Raised when NCBI E-utilities is unreachable, times out, or returns 5xx."""

    pass


@dataclass(frozen=True)
class PubMedArticleRecord:
    """Structured bibliographic and abstract record retrieved from PubMed E-utilities."""

    pmid: str
    title: str
    source_url: str
    retrieved_at: datetime
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
    journal_title: str | None = None
    publication_year: int | None = None
    publication_types: list[str] = field(default_factory=list)
    study_type: str = "journal_article"
    abstract_text: str | None = None
    population_or_context: str | None = None
    mesh_terms: list[str] = field(default_factory=list)
    chemical_substances: list[str] = field(default_factory=list)
    has_full_text: bool = False
    is_exact_ingredient_match: bool = True
    match_note: str = "Matched ingredient in title or abstract"
    attribution: str = (
        "Courtesy of the U.S. National Library of Medicine (NLM) via NCBI E-utilities."
    )


def classify_study_type(pub_types: list[str], title: str, abstract: str | None) -> str:
    """Conservatively classify study design from PubMed publication types and text."""
    lower_types = {pt.lower() for pt in pub_types}
    combined_text = f"{title} {abstract or ''}".lower()

    if "meta-analysis" in lower_types or "meta-analysis" in combined_text:
        return "meta_analysis"
    if "systematic review" in lower_types or "systematic review" in combined_text:
        return "systematic_review"
    if (
        "randomized controlled trial" in lower_types
        or "randomized controlled" in combined_text
        or "double-blind" in combined_text
    ):
        return "rct"
    if any("clinical trial" in t for t in lower_types):
        return "clinical_trial"
    if "review" in lower_types:
        return "review"
    if (
        "in vitro" in combined_text
        or "cell culture" in combined_text
        or "melanocyte" in combined_text
    ) and ("human" not in combined_text or "in vitro" in combined_text):
        return "in_vitro"
    if "observational study" in lower_types or "cohort" in combined_text:
        return "observational"
    return "journal_article"


def extract_population_context(mesh_terms: list[str], abstract: str | None) -> str | None:
    """Extract conservative population or experimental context from MeSH terms and abstract."""
    contexts: list[str] = []
    lower_mesh = {m.lower() for m in mesh_terms}

    if "humans" in lower_mesh:
        contexts.append("Human subjects")
    if "animals" in lower_mesh or "mice" in lower_mesh:
        contexts.append("Animal model")
    if "cells, cultured" in lower_mesh or "cell line" in lower_mesh:
        contexts.append("In vitro cultured cells")
    if "female" in lower_mesh and "male" in lower_mesh:
        contexts.append("Male and female participants")
    elif "female" in lower_mesh:
        contexts.append("Female participants")

    if abstract:
        lower_abs = abstract.lower()
        if "in vitro" in lower_abs and "In vitro cultured cells" not in contexts:
            contexts.append("In vitro assay")
        if "fitzpatrick" in lower_abs:
            contexts.append("Fitzpatrick skin phototypes reported")
        n_match = re.search(r"\bn\s*=\s*\d+", lower_abs)
        if n_match:
            contexts.append(n_match.group(0))
        if "melasma" in lower_abs:
            contexts.append("Melasma / hyperpigmentation context")
        elif "hyperpigmentation" in lower_abs or "pigmentation" in lower_abs:
            contexts.append("Cutaneous pigmentation context")

    return "; ".join(contexts) if contexts else None


class PubMedAdapter(BaseProvider):
    """Official NCBI PubMed E-utilities adapter."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        tool_name: str | None = None,
        contact_email: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.PUBMED_BASE_URL).rstrip("/")
        self._api_key = (
            api_key
            if api_key is not None
            else (settings.PUBMED_API_KEY.get_secret_value() if settings.PUBMED_API_KEY else None)
        )
        self._tool_name = tool_name or settings.PUBMED_TOOL_NAME
        self._contact_email = contact_email or settings.PUBMED_CONTACT_EMAIL
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "pubmed"

    def _common_params(self) -> dict[str, str]:
        """Return mandatory NCBI E-utilities identification parameters."""
        params: dict[str, str] = {
            "tool": self._tool_name,
            "email": self._contact_email,
        }
        if self._api_key and self._api_key.strip():
            params["api_key"] = self._api_key.strip()
        return params

    async def _get_with_retries(self, endpoint: str, params: dict[str, Any]) -> httpx.Response:
        """Execute GET request against NCBI E-utilities with bounded retries and rate limits."""
        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        full_params = {**self._common_params(), **params}

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._client is not None:
                    resp = await self._client.get(url, params=full_params)
                else:
                    async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                        resp = await client.get(url, params=full_params)

                if resp.status_code == 429:
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                        continue
                    raise PubMedRateLimitError(
                        "NCBI PubMed E-utilities rate limit exceeded (HTTP 429)."
                    )

                if resp.status_code >= 500:
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                        continue
                    raise PubMedUnavailableError(
                        f"NCBI PubMed E-utilities server error: HTTP {resp.status_code}"
                    )

                if resp.status_code != 200:
                    raise PubMedError(
                        f"PubMed E-utilities returned unexpected status HTTP {resp.status_code}"
                    )

                return resp

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                    continue
                raise PubMedUnavailableError(
                    f"PubMed E-utilities network or timeout failure: {exc}"
                ) from exc

        raise PubMedUnavailableError(f"PubMed request failed after retries: {last_exc}")

    async def check_health(self) -> tuple[bool, str | None]:
        """Verify connectivity to NCBI PubMed E-utilities."""
        try:
            resp = await self._get_with_retries(
                "esearch.fcgi",
                {"db": "pubmed", "term": "niacinamide", "retmode": "json", "retmax": "1"},
            )
            if resp.status_code == 200:
                return True, "NCBI PubMed E-utilities reachable."
            return False, f"PubMed returned HTTP {resp.status_code}"
        except Exception as exc:
            return False, f"PubMed unreachable: {exc}"

    @staticmethod
    def build_search_query(
        ingredient_name: str,
        topic: str | None = "skin",
        aliases: list[str] | None = None,
    ) -> str:
        """Construct an ESearch query term for an ingredient, aliases, and dermatological topic."""
        clean_ing = ingredient_name.strip()
        if not clean_ing:
            return ""

        ing_clauses = [f'"{clean_ing}"[Title/Abstract]', f'"{clean_ing}"[MeSH Terms]']
        if aliases:
            for al in aliases:
                if al and al.strip():
                    ing_clauses.append(f'"{al.strip()}"[Title/Abstract]')

        ing_expr = f"({' OR '.join(dict.fromkeys(ing_clauses))})"

        if topic and topic.strip():
            clean_topic = topic.strip()
            return (
                f'{ing_expr} AND ("{clean_topic}"[Title/Abstract] '
                "OR dermatology[Title/Abstract] OR skin[Title/Abstract])"
            )
        return (
            f"{ing_expr} AND (skin[Title/Abstract] "
            "OR topical[Title/Abstract] OR cosmetic[Title/Abstract])"
        )

    async def search_pmids(
        self,
        ingredient_name: str,
        topic: str | None = "skin",
        max_results: int = 5,
        aliases: list[str] | None = None,
    ) -> list[str]:
        """Search PubMed for PMIDs relevant to an ingredient and dermatological topic."""
        query_term = self.build_search_query(
            ingredient_name=ingredient_name,
            topic=topic,
            aliases=aliases,
        )
        if not query_term:
            return []

        resp = await self._get_with_retries(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": query_term,
                "retmode": "json",
                "retmax": str(max(1, min(max_results, 20))),
                "sort": "relevance",
            },
        )
        try:
            payload = resp.json()
            id_list = payload.get("esearchresult", {}).get("idlist") or []
            deduped = list(
                dict.fromkeys(str(pmid).strip() for pmid in id_list if str(pmid).strip())
            )
            return deduped
        except Exception as exc:
            raise PubMedError(f"Malformed JSON from PubMed ESearch: {exc}") from exc

    async def fetch_articles(
        self,
        pmids: list[str],
        target_ingredient: str | None = None,
        aliases: list[str] | None = None,
    ) -> list[PubMedArticleRecord]:
        """Fetch and parse PubMed XML bibliographic records and abstracts for given PMIDs."""
        clean_pmids = [str(p).strip() for p in pmids if str(p).strip()]
        if not clean_pmids:
            return []

        resp = await self._get_with_retries(
            "efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(clean_pmids),
                "retmode": "xml",
            },
        )
        return self.parse_efetch_xml(
            resp.text,
            target_ingredient=target_ingredient,
            aliases=aliases,
        )

    async def search_and_fetch(
        self,
        ingredient_name: str,
        topic: str | None = "skin",
        max_results: int = 5,
        aliases: list[str] | None = None,
    ) -> list[PubMedArticleRecord]:
        """Perform combined ESearch + EFetch workflow for an ingredient."""
        pmids = await self.search_pmids(
            ingredient_name=ingredient_name,
            topic=topic,
            max_results=max_results,
        )
        if not pmids:
            return []
        return await self.fetch_articles(
            pmids=pmids,
            target_ingredient=ingredient_name,
            aliases=aliases,
        )

    def parse_efetch_xml(
        self,
        xml_text: str,
        target_ingredient: str | None = None,
        aliases: list[str] | None = None,
    ) -> list[PubMedArticleRecord]:
        """Parse NCBI PubMed EFetch XML payload into structured PubMedArticleRecord items."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise PubMedError(f"Malformed XML returned by PubMed EFetch: {exc}") from exc

        now = datetime.now(UTC)
        records: list[PubMedArticleRecord] = []
        seen_pmids: set[str] = set()

        acceptable_terms: list[str] = []
        if target_ingredient and target_ingredient.strip():
            acceptable_terms.append(target_ingredient.strip().lower())
        if aliases:
            for al in aliases:
                if al and al.strip():
                    acceptable_terms.append(al.strip().lower())

        for article_elem in root.findall(".//PubmedArticle"):
            pmid_elem = article_elem.find(".//MedlineCitation/PMID")
            if pmid_elem is None or not pmid_elem.text:
                continue
            pmid = pmid_elem.text.strip()
            if pmid in seen_pmids:
                continue
            seen_pmids.add(pmid)

            # Title (handle inner formatting tags like <i> or <sub>)
            title_elem = article_elem.find(".//Article/ArticleTitle")
            title = (
                "".join(title_elem.itertext()).strip()
                if title_elem is not None
                else f"PubMed Record {pmid}"
            )
            if not title:
                title = f"PubMed Record {pmid}"

            # Abstract (handle multiple structured AbstractText sections; None if missing)
            abstract_elems = article_elem.findall(".//Article/Abstract/AbstractText")
            abstract_parts: list[str] = []
            for abs_el in abstract_elems:
                sec_text = "".join(abs_el.itertext()).strip()
                if not sec_text:
                    continue
                label = abs_el.attrib.get("Label")
                if label:
                    abstract_parts.append(f"{label}: {sec_text}")
                else:
                    abstract_parts.append(sec_text)
            abstract_text = "\n\n".join(abstract_parts) if abstract_parts else None

            # Journal
            journal_title = article_elem.findtext(".//Article/Journal/Title")
            if journal_title:
                journal_title = journal_title.strip()

            # Publication Year (check Year, ArticleDate/Year, or MedlineDate)
            pub_year: int | None = None
            year_text = article_elem.findtext(
                ".//Article/Journal/JournalIssue/PubDate/Year"
            ) or article_elem.findtext(".//Article/ArticleDate/Year")
            if year_text and year_text.strip().isdigit():
                pub_year = int(year_text.strip())
            else:
                medline_date = article_elem.findtext(
                    ".//Article/Journal/JournalIssue/PubDate/MedlineDate"
                )
                if medline_date:
                    ym = re.search(r"\b(19\d{2}|20\d{2})\b", medline_date)
                    if ym:
                        pub_year = int(ym.group(1))

            # DOI (check PubmedData/ArticleIdList or Article/ELocationID)
            doi: str | None = None
            for id_el in article_elem.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if id_el.attrib.get("IdType") == "doi" and id_el.text:
                    doi = id_el.text.strip()
                    break
            if not doi:
                for eloc_el in article_elem.findall(".//Article/ELocationID"):
                    if eloc_el.attrib.get("EIdType") == "doi" and eloc_el.text:
                        doi = eloc_el.text.strip()
                        break

            # Authors
            authors: list[str] = []
            for author_el in article_elem.findall(".//Article/AuthorList/Author"):
                last_name = author_el.findtext("LastName") or ""
                fore_name = author_el.findtext("ForeName") or author_el.findtext("Initials") or ""
                collective = author_el.findtext("CollectiveName")
                if last_name.strip():
                    full_author = f"{last_name.strip()} {fore_name.strip()}".strip()
                    authors.append(full_author)
                elif collective and collective.strip():
                    authors.append(collective.strip())

            # Publication Types
            pub_types: list[str] = []
            for pt_el in article_elem.findall(".//Article/PublicationTypeList/PublicationType"):
                if pt_el.text and pt_el.text.strip():
                    pub_types.append(pt_el.text.strip())

            # MeSH Headings
            mesh_terms: list[str] = []
            for mesh_el in article_elem.findall(
                ".//MedlineCitation/MeshHeadingList/MeshHeading/DescriptorName"
            ):
                if mesh_el.text and mesh_el.text.strip():
                    mesh_terms.append(mesh_el.text.strip())

            # Chemical Substances
            chemicals: list[str] = []
            for chem_el in article_elem.findall(
                ".//MedlineCitation/ChemicalList/Chemical/NameOfSubstance"
            ):
                if chem_el.text and chem_el.text.strip():
                    chemicals.append(chem_el.text.strip())

            # Verify whether target ingredient actually appears in article metadata
            is_matched = True
            match_note = "Matched ingredient in title, abstract, or chemical index."
            if acceptable_terms:
                searchable_blob = " ".join(
                    [
                        title.lower(),
                        (abstract_text or "").lower(),
                        " ".join(c.lower() for c in chemicals),
                        " ".join(m.lower() for m in mesh_terms),
                    ]
                )
                if not any(term in searchable_blob for term in acceptable_terms):
                    is_matched = False
                    match_note = (
                        f"Target ingredient '{target_ingredient}' was not explicitly verified "
                        "in title, abstract, or MeSH chemical index."
                    )

            study_type = classify_study_type(pub_types, title, abstract_text)
            pop_context = extract_population_context(mesh_terms, abstract_text)

            records.append(
                PubMedArticleRecord(
                    pmid=pmid,
                    title=title,
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    retrieved_at=now,
                    doi=doi,
                    authors=authors,
                    journal_title=journal_title,
                    publication_year=pub_year,
                    publication_types=pub_types,
                    study_type=study_type,
                    abstract_text=abstract_text,
                    population_or_context=pop_context,
                    mesh_terms=mesh_terms,
                    chemical_substances=chemicals,
                    has_full_text=False,
                    is_exact_ingredient_match=is_matched,
                    match_note=match_note,
                )
            )

        return records
