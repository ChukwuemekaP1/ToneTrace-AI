"""European Commission CosIng (Cosmetic Ingredient Database) provider adapter.

Supports both official documented CosIng access methods:
1. Official EC Search REST API (`https://api.tech.ec.europa.eu/search-api/prod/rest/search`)
   querying the `GROWTH_COSING` dataset for INCI nomenclature, CosIng Ref/Substance ID,
   CAS/EC identifiers, cosmetic functions, and EU Regulation (EC) No 1223/2009 restrictions.
2. Official EC CosIng Inventory CSV download parser (`parse_cosing_csv`), matching the
   European Commission Decision (EU) 2022/677 Common Glossary export format.

Compliance & Epistemic Rules:
- Distinguishes exact INCI matches (`NIACINAMIDE`) from compound derivatives
  (`NIACINAMIDE/YEAST POLYPEPTIDE`) to prevent false ingredient conflation.
- Preserves official regulatory functions and restrictions as `identity_reference`
  data rather than clinical efficacy claims.
"""

import asyncio
import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class CosIngError(Exception):
    """Base exception for European Commission CosIng operations."""

    pass


class CosIngRateLimitError(CosIngError):
    """Raised when EC CosIng API rate limit (HTTP 429) is exceeded."""

    pass


class CosIngUnavailableError(CosIngError):
    """Raised when EC CosIng API is unreachable, times out, or returns 5xx."""

    pass


@dataclass(frozen=True)
class CosIngRecord:
    """Structured regulatory and identity record from the European Commission CosIng database."""

    cosing_ref_no: str
    inci_name: str
    source_url: str
    retrieved_at: datetime
    cas_no: str | None = None
    ec_no: str | None = None
    chemical_description: str | None = None
    functions: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    max_concentration: str | None = None
    sccs_opinions: list[str] = field(default_factory=list)
    annex_no: str | None = None
    is_exact_inci_match: bool = True
    match_note: str = "Exact INCI name match in EC CosIng inventory."
    attribution: str = (
        "European Commission CosIng Database "
        "(Regulation (EC) No 1223/2009 & Decision (EU) 2022/677)."
    )


def _clean_dash(value: str | None) -> str | None:
    """Normalize placeholder dashes ('-') in CosIng metadata to None."""
    if not value:
        return None
    cleaned = value.strip()
    if cleaned in ("-", "N/A", "null", "[]", ""):
        return None
    return cleaned


def _first_clean(items: list[Any] | Any) -> str | None:
    """Extract first non-empty string from a CosIng metadata array."""
    if isinstance(items, list):
        for el in items:
            cleaned = _clean_dash(str(el))
            if cleaned:
                return cleaned
        return None
    if isinstance(items, str):
        return _clean_dash(items)
    return None


class CosIngAdapter(BaseProvider):
    """Official European Commission CosIng regulatory reference adapter."""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._api_url = (api_url or settings.COSING_API_URL).rstrip("/")
        self._api_key = (
            api_key if api_key is not None else settings.COSING_API_KEY.get_secret_value()
        )
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "cosing"

    async def check_health(self) -> tuple[bool, str | None]:
        """Verify connectivity to European Commission CosIng Search API."""
        try:
            records = await self.search_ingredient("GLYCERIN", max_results=1)
            if records is not None:
                return True, "European Commission CosIng API reachable."
            return False, "CosIng API returned empty status."
        except Exception as exc:
            return False, f"CosIng API unreachable: {exc}"

    async def search_ingredient(
        self,
        inci_or_name: str,
        max_results: int = 5,
    ) -> list[CosIngRecord]:
        """Query the official EC CosIng Search API for an ingredient and parse records."""
        clean_query = inci_or_name.strip()
        if not clean_query:
            return []

        params = {
            "apiKey": self._api_key,
            "text": clean_query.upper(),
            "pageSize": str(max(1, min(max_results * 3, 25))),
            "pageNumber": "1",
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                if self._client is not None:
                    resp = await self._client.post(self._api_url, params=params)
                else:
                    async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                        resp = await client.post(self._api_url, params=params)

                if resp.status_code == 429:
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                        continue
                    raise CosIngRateLimitError("EC CosIng API rate limit exceeded (HTTP 429).")

                if resp.status_code >= 500:
                    if attempt < self._max_retries:
                        await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                        continue
                    raise CosIngUnavailableError(
                        f"EC CosIng API server error: HTTP {resp.status_code}"
                    )

                if resp.status_code != 200:
                    raise CosIngError(f"EC CosIng API unexpected status: HTTP {resp.status_code}")

                payload = resp.json()
                return self.parse_api_response(
                    payload,
                    target_inci=clean_query,
                    max_results=max_results,
                )

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))
                    continue
                raise CosIngUnavailableError(
                    f"EC CosIng API timeout or network error: {exc}"
                ) from exc

        raise CosIngUnavailableError(f"EC CosIng API failed after retries: {last_exc}")

    def parse_api_response(
        self,
        payload: dict[str, Any],
        target_inci: str | None = None,
        max_results: int = 5,
        *,
        target_ingredient: str | None = None,
    ) -> list[CosIngRecord]:
        """Parse official EC Search API JSON payload (`GROWTH_COSING` datasource)."""
        now = datetime.now(UTC)
        raw_results = payload.get("results") or []
        effective_target = target_inci or target_ingredient or ""
        target_upper = effective_target.strip().upper()

        exact_matches: list[CosIngRecord] = []
        partial_matches: list[CosIngRecord] = []
        seen_refs: set[str] = set()

        for item in raw_results:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") or {}
            if not isinstance(meta, dict):
                continue

            inci = _first_clean(meta.get("inciName")) or _first_clean(
                meta.get("nameOfCommonIngredientsGlossary")
            )
            if not inci:
                continue

            ref_no = (
                _first_clean(meta.get("substanceId"))
                or _first_clean(meta.get("refNo"))
                or _first_clean(meta.get("reference"))
                or item.get("reference")
            )
            if not ref_no:
                continue
            ref_no = str(ref_no).strip()
            if ref_no in seen_refs:
                continue
            seen_refs.add(ref_no)

            cas_no = _first_clean(meta.get("casNo"))
            ec_no = _first_clean(meta.get("ecNo"))
            chem_desc = _first_clean(meta.get("chemicalDescription")) or _first_clean(
                meta.get("chemicalName")
            )
            max_conc = _first_clean(meta.get("maximumConcentration"))
            annex_no = _first_clean(meta.get("annexNo"))

            raw_funcs = meta.get("functionName") or []
            functions = [
                str(f).strip()
                for f in (raw_funcs if isinstance(raw_funcs, list) else [raw_funcs])
                if _clean_dash(str(f))
            ]

            raw_restr = (meta.get("cosmeticRestriction") or []) + (
                meta.get("otherRestrictions") or []
            )
            restrictions = [str(r).strip() for r in raw_restr if _clean_dash(str(r))]

            raw_sccs = meta.get("sccsOpinion") or []
            sccs_opinions = [
                str(s).strip()
                for s in (raw_sccs if isinstance(raw_sccs, list) else [raw_sccs])
                if _clean_dash(str(s))
            ]

            inci_upper = inci.strip().upper()
            is_exact = inci_upper == target_upper
            match_note = (
                "Exact INCI match in European Commission CosIng inventory."
                if is_exact
                else f"Partial/derivative INCI match ('{inci}' vs queried '{target_inci}')."
            )

            record = CosIngRecord(
                cosing_ref_no=ref_no,
                inci_name=inci.strip(),
                source_url=f"https://ec.europa.eu/growth/tools-databases/cosing/details/{ref_no}",
                retrieved_at=now,
                cas_no=cas_no,
                ec_no=ec_no,
                chemical_description=chem_desc,
                functions=functions,
                restrictions=restrictions,
                max_concentration=max_conc,
                sccs_opinions=sccs_opinions,
                annex_no=annex_no,
                is_exact_inci_match=is_exact,
                match_note=match_note,
            )

            if is_exact:
                exact_matches.append(record)
            else:
                partial_matches.append(record)

        # Prioritize exact INCI matches first; only include partial matches if requested
        combined = exact_matches + partial_matches
        return combined[: max(1, max_results)]

    @staticmethod
    def parse_cosing_csv(
        csv_content: str,
        target_inci: str | None = None,
        *,
        target_ingredient: str | None = None,
    ) -> list[CosIngRecord]:
        """Parse official European Commission CosIng CSV inventory export.

        Handles official EC CSV files (which may include preamble lines before the
        `COSING Ref No,INCI name,...` header row).
        """
        now = datetime.now(UTC)
        lines = csv_content.splitlines()
        header_idx = 0
        for idx, line in enumerate(lines):
            if "COSING Ref No" in line or "INCI name" in line:
                header_idx = idx
                break

        clean_csv = "\n".join(lines[header_idx:])
        reader = csv.DictReader(io.StringIO(clean_csv))
        records: list[CosIngRecord] = []
        effective_target = target_inci or target_ingredient
        target_upper = effective_target.strip().upper() if effective_target else None

        for row in reader:
            if not row:
                continue
            norm_row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            ref_no = norm_row.get("COSING Ref No") or norm_row.get("Ref No")
            inci = norm_row.get("INCI name") or norm_row.get("INCI Name")
            if not ref_no or not inci:
                continue

            inci_upper = inci.upper()
            if target_upper and target_upper not in inci_upper:
                continue

            is_exact = (inci_upper == target_upper) if target_upper else True
            match_note = (
                "Exact INCI match from official EC CosIng CSV inventory."
                if is_exact
                else f"Derivative INCI match ('{inci}' vs '{target_inci}') in CosIng CSV."
            )

            raw_func = norm_row.get("Function") or ""
            functions = [f.strip() for f in raw_func.replace("/", ",").split(",") if _clean_dash(f)]

            raw_restr = norm_row.get("Restriction") or ""
            restrictions = [raw_restr] if _clean_dash(raw_restr) else []

            records.append(
                CosIngRecord(
                    cosing_ref_no=ref_no,
                    inci_name=inci,
                    source_url=f"https://ec.europa.eu/growth/tools-databases/cosing/details/{ref_no}",
                    retrieved_at=now,
                    cas_no=_clean_dash(norm_row.get("CAS No")),
                    ec_no=_clean_dash(norm_row.get("EC No")),
                    chemical_description=_clean_dash(norm_row.get("Chem/IUPAC Name / Description")),
                    functions=functions,
                    restrictions=restrictions,
                    is_exact_inci_match=is_exact,
                    match_note=match_note,
                )
            )

        return records
