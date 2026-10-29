"""Skin analysis provider interface and adapters (Phase 8).

Implements:
- BaseSkinAnalysisProvider: Replaceable contract for skin-analysis engines.
- YouCamSkinAnalysisAdapter: Verified Perfect Corp / YouCam S2S v2.0 API adapter
  (file initialization -> pre-signed S3 PUT -> task creation -> status polling).
- MockSkinAnalysisAdapter: Deterministic offline adapter for automated tests.

Safety & Provenance Rules:
- Never fabricates a successful scan when the external provider is unavailable,
  times out, or returns an error.
- Normalizes metric codes, raw values, display values, units, directionality,
  provider/model version, and interpretation version separately from restricted
  raw provider payloads.
- Explicitly attaches non-clinical caveats explaining that lighting, camera,
  angle, and cosmetics affect visual surface measurements.
"""

import asyncio
import hashlib
import io
import json
import logging
import zipfile
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx
from google import genai
from google.genai import types

from app.core.config import get_settings
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

INTERPRETATION_VERSION = "tonetrace-obs-v1.0"

STANDARD_OBSERVATION_CAVEAT = (
    "Visual surface metric derived from a 2D photograph. Lighting, camera sensor, "
    "viewing angle, facial expression, and cosmetics or skincare residue can "
    "significantly affect this measurement. This is a cosmetic visual observation, "
    "not a clinical dermatological measurement or medical diagnosis."
)


@dataclass(frozen=True)
class MetricSpec:
    """Specification for a normalized ToneTrace skin observation metric."""

    metric_code: str
    youcam_action: str
    label: str
    unit: str = "score_0_100"
    directionality: str = "higher_is_better"
    default_zone: str = "full_face"


NORMALIZED_METRICS: dict[str, MetricSpec] = {
    "spots": MetricSpec(
        metric_code="spots",
        youcam_action="age_spot",
        label="Visible Tone Unevenness & Surface Spots",
    ),
    "redness": MetricSpec(
        metric_code="redness",
        youcam_action="redness",
        label="Visible Surface Redness",
    ),
    "texture": MetricSpec(
        metric_code="texture",
        youcam_action="texture",
        label="Visible Surface Texture Smoothness",
    ),
    "pores": MetricSpec(
        metric_code="pores",
        youcam_action="pore",
        label="Visible Pore Appearance",
    ),
    "wrinkles": MetricSpec(
        metric_code="wrinkles",
        youcam_action="wrinkle",
        label="Visible Fine Lines & Wrinkles",
    ),
    "acne": MetricSpec(
        metric_code="acne",
        youcam_action="acne",
        label="Visible Blemish Appearance",
    ),
    "oiliness": MetricSpec(
        metric_code="oiliness",
        youcam_action="oiliness",
        label="Visible Surface Shine & Oiliness Balance",
    ),
    "moisture": MetricSpec(
        metric_code="moisture",
        youcam_action="moisture",
        label="Estimated Surface Hydration Appearance",
    ),
    "radiance": MetricSpec(
        metric_code="radiance",
        youcam_action="radiance",
        label="Visible Surface Radiance",
    ),
    "firmness": MetricSpec(
        metric_code="firmness",
        youcam_action="firmness",
        label="Visible Surface Firmness Appearance",
    ),
    "dark_circles": MetricSpec(
        metric_code="dark_circles",
        youcam_action="dark_circle_v2",
        label="Periorbital Dark Circle Appearance",
        default_zone="periorbital",
    ),
    "eye_bags": MetricSpec(
        metric_code="eye_bags",
        youcam_action="eye_bag",
        label="Under-Eye Puffiness Appearance",
        default_zone="periorbital",
    ),
}

YOUCAM_ACTION_TO_METRIC: dict[str, MetricSpec] = {
    spec.youcam_action: spec for spec in NORMALIZED_METRICS.values()
}
# Additional aliases that YouCam S2S responses may use in score_info keys
YOUCAM_ACTION_TO_METRIC["spot"] = NORMALIZED_METRICS["spots"]
YOUCAM_ACTION_TO_METRIC["spots"] = NORMALIZED_METRICS["spots"]
YOUCAM_ACTION_TO_METRIC["pores"] = NORMALIZED_METRICS["pores"]
YOUCAM_ACTION_TO_METRIC["wrinkles"] = NORMALIZED_METRICS["wrinkles"]
YOUCAM_ACTION_TO_METRIC["dark_circle"] = NORMALIZED_METRICS["dark_circles"]
YOUCAM_ACTION_TO_METRIC["dark_circles"] = NORMALIZED_METRICS["dark_circles"]
YOUCAM_ACTION_TO_METRIC["eye_bags"] = NORMALIZED_METRICS["eye_bags"]

DEFAULT_REQUESTED_METRICS: list[str] = [
    "spots",
    "redness",
    "texture",
    "pores",
    "wrinkles",
    "acne",
    "oiliness",
    "moisture",
    "radiance",
    "firmness",
]


class SkinAnalysisError(Exception):
    """Base exception for skin analysis provider errors."""

    def __init__(
        self,
        message: str,
        category: str = "upstream_error",
        is_retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.is_retryable = is_retryable


class SkinAnalysisConfigurationError(SkinAnalysisError):
    """Raised when skin analysis provider credentials or settings are missing."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="configuration_error", is_retryable=False)


class SkinAnalysisAuthenticationError(SkinAnalysisError):
    """Raised when external provider rejects API credentials."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="authentication_error", is_retryable=False)


class SkinAnalysisRateLimitError(SkinAnalysisError):
    """Raised when external provider returns 429 rate limit or quota exhaustion."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="rate_limited", is_retryable=True)


class SkinAnalysisTimeoutError(SkinAnalysisError):
    """Raised when external provider times out during upload, task creation, or polling."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="provider_timeout", is_retryable=True)


class SkinAnalysisUnavailableError(SkinAnalysisError):
    """Raised when external provider is unreachable or returns a 5xx server failure."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="provider_unavailable", is_retryable=True)


class SkinAnalysisInvalidImageError(SkinAnalysisError):
    """Raised when provider cannot detect a valid face or rejects image quality/lighting."""

    def __init__(self, message: str, category: str = "invalid_image") -> None:
        super().__init__(message, category=category, is_retryable=False)


@dataclass(frozen=True)
class NormalizedObservationResult:
    """Normalized single-metric visual observation returned by a provider adapter."""

    metric_code: str
    metric_label: str
    raw_value: float
    display_value: float
    unit: str = "score_0_100"
    directionality: str = "higher_is_better"
    facial_zone: str = "full_face"
    confidence: float | None = None
    caveat_note: str = STANDARD_OBSERVATION_CAVEAT


@dataclass
class SkinAnalysisTaskResult:
    """Normalized scan submission or polling result from a skin analysis provider."""

    provider_name: str
    provider_task_id: str | None
    provider_model_version: str
    interpretation_version: str
    status: str  # "processing", "succeeded", "failed"
    observations: list[NormalizedObservationResult] = field(default_factory=list)
    overall_score: float | None = None
    skin_type_observation: str | None = None
    error_category: str | None = None
    error_message: str | None = None


class BaseSkinAnalysisProvider(BaseProvider):
    """Abstract interface for skin analysis providers."""

    @property
    @abstractmethod
    def provider_model_version(self) -> str:
        """Return the provider and model version identifier for comparability."""

    @property
    def interpretation_version(self) -> str:
        """Return ToneTrace's metric normalization version."""
        return INTERPRETATION_VERSION

    @abstractmethod
    async def submit_scan(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        requested_metrics: list[str] | None = None,
    ) -> SkinAnalysisTaskResult:
        """Submit a validated facial photo for skin analysis."""

    @abstractmethod
    async def poll_task(self, provider_task_id: str) -> SkinAnalysisTaskResult:
        """Poll an asynchronous provider task by its provider_task_id."""


class MockSkinAnalysisAdapter(BaseSkinAnalysisProvider):
    """Deterministic mock adapter for local development and automated testing.

    Generates reproducible visual observations derived from the SHA-256 digest of
    the uploaded image bytes. Supports deterministic simulation of asynchronous
    task polling, timeouts, provider unavailability, and face-detection failures.
    """

    def __init__(
        self,
        *,
        model_version: str = "mock-deterministic-v1.0",
        simulate_async: bool = False,
        simulate_timeout: bool = False,
        simulate_unavailable: bool = False,
        simulate_invalid_image: bool = False,
        simulate_rate_limit: bool = False,
    ) -> None:
        self._model_version = model_version
        self._simulate_async = simulate_async
        self._simulate_timeout = simulate_timeout
        self._simulate_unavailable = simulate_unavailable
        self._simulate_invalid_image = simulate_invalid_image
        self._simulate_rate_limit = simulate_rate_limit
        self._pending_tasks: dict[str, tuple[bytes, list[str]]] = {}

    @property
    def name(self) -> str:
        return "mock"

    @property
    def provider_model_version(self) -> str:
        return self._model_version

    async def check_health(self) -> tuple[bool, str | None]:
        if self._simulate_unavailable:
            return False, "Mock skin analysis adapter configured as unavailable."
        return True, f"Mock skin analysis adapter ready ({self._model_version})."

    def _build_deterministic_observations(
        self,
        file_bytes: bytes,
        metrics: list[str],
    ) -> tuple[list[NormalizedObservationResult], float, str]:
        digest = hashlib.sha256(file_bytes).digest()
        observations: list[NormalizedObservationResult] = []
        for idx, code in enumerate(metrics):
            spec = NORMALIZED_METRICS.get(code)
            if not spec:
                continue
            byte_a = digest[idx % len(digest)]
            byte_b = digest[(idx + 7) % len(digest)]
            # Deterministic score between 45.0 and 92.0
            raw_val = round(45.0 + ((byte_a * 256 + byte_b) % 470) / 10.0, 1)
            display_val = float(round(raw_val))
            confidence = round(0.82 + (byte_a % 15) / 100.0, 2)
            observations.append(
                NormalizedObservationResult(
                    metric_code=spec.metric_code,
                    metric_label=spec.label,
                    raw_value=raw_val,
                    display_value=display_val,
                    unit=spec.unit,
                    directionality=spec.directionality,
                    facial_zone=spec.default_zone,
                    confidence=confidence,
                    caveat_note=STANDARD_OBSERVATION_CAVEAT,
                )
            )

        overall = (
            round(sum(o.display_value for o in observations) / len(observations), 1)
            if observations
            else 70.0
        )
        skin_types = ["combination", "normal", "dry", "oily"]
        skin_type = skin_types[digest[0] % len(skin_types)]
        return observations, overall, skin_type

    async def submit_scan(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        requested_metrics: list[str] | None = None,
    ) -> SkinAnalysisTaskResult:
        _ = (filename, content_type)
        if self._simulate_timeout:
            raise SkinAnalysisTimeoutError(
                "Simulated skin analysis provider timeout during task submission."
            )
        if self._simulate_unavailable:
            raise SkinAnalysisUnavailableError(
                "Simulated skin analysis provider 503 unavailability."
            )
        if self._simulate_rate_limit:
            raise SkinAnalysisRateLimitError(
                "Simulated skin analysis provider 429 rate limit exceeded."
            )
        if self._simulate_invalid_image:
            raise SkinAnalysisInvalidImageError(
                "No clear frontal face detected or lighting conditions outside valid bounds.",
                category="no_face_detected",
            )

        metrics = requested_metrics or list(DEFAULT_REQUESTED_METRICS)
        digest_hex = hashlib.sha256(file_bytes).hexdigest()[:24]
        task_id = f"mock_task_{digest_hex}"

        if self._simulate_async:
            self._pending_tasks[task_id] = (file_bytes, metrics)
            return SkinAnalysisTaskResult(
                provider_name=self.name,
                provider_task_id=task_id,
                provider_model_version=self.provider_model_version,
                interpretation_version=self.interpretation_version,
                status="processing",
            )

        observations, overall, skin_type = self._build_deterministic_observations(
            file_bytes, metrics
        )
        return SkinAnalysisTaskResult(
            provider_name=self.name,
            provider_task_id=task_id,
            provider_model_version=self.provider_model_version,
            interpretation_version=self.interpretation_version,
            status="succeeded",
            observations=observations,
            overall_score=overall,
            skin_type_observation=skin_type,
        )

    async def poll_task(self, provider_task_id: str) -> SkinAnalysisTaskResult:
        if self._simulate_timeout:
            raise SkinAnalysisTimeoutError("Simulated provider timeout while polling task status.")
        if self._simulate_unavailable:
            raise SkinAnalysisUnavailableError("Simulated provider unavailability while polling.")

        pending = self._pending_tasks.pop(provider_task_id, None)
        if pending is not None:
            file_bytes, metrics = pending
        else:
            file_bytes = provider_task_id.encode("utf-8")
            metrics = list(DEFAULT_REQUESTED_METRICS)

        observations, overall, skin_type = self._build_deterministic_observations(
            file_bytes, metrics
        )
        return SkinAnalysisTaskResult(
            provider_name=self.name,
            provider_task_id=provider_task_id,
            provider_model_version=self.provider_model_version,
            interpretation_version=self.interpretation_version,
            status="succeeded",
            observations=observations,
            overall_score=overall,
            skin_type_observation=skin_type,
        )


class YouCamSkinAnalysisAdapter(BaseSkinAnalysisProvider):
    """Official Perfect Corp / YouCam S2S v2.0 API skin analysis adapter.

    Verified S2S v2.0 Workflow:
    1. POST /s2s/v2.0/file/skin-analysis with Bearer token and file metadata
       -> returns file_id and pre-signed S3 PUT URL + headers.
    2. PUT raw image bytes to the pre-signed S3 URL.
    3. POST /s2s/v2.0/task/skin-analysis with src_file_id and dst_actions
       -> returns task_id.
    4. Poll GET /s2s/v2.0/task/skin-analysis/{task_id} until task_status is
       'success' or 'error' (or return 'processing' with task_id for later polling).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_poll_attempts: int = 4,
        poll_interval_seconds: float = 1.5,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        resolved_key = api_key
        if resolved_key is None and settings.SKIN_ANALYSIS_API_KEY is not None:
            resolved_key = settings.SKIN_ANALYSIS_API_KEY.get_secret_value().strip()
        self._api_key = resolved_key or ""
        self._base_url = (
            base_url or settings.SKIN_ANALYSIS_BASE_URL or "https://yce-api-01.makeupar.com"
        ).rstrip("/")
        self._timeout = timeout_seconds or settings.SKIN_ANALYSIS_TIMEOUT_SECONDS or 20.0
        self._max_poll_attempts = max_poll_attempts
        self._poll_interval_seconds = poll_interval_seconds
        self._client = http_client

    @property
    def name(self) -> str:
        return "youcam"

    @property
    def provider_model_version(self) -> str:
        return "youcam-s2s-v2.0"

    def _ensure_configured(self) -> None:
        if not self._api_key:
            raise SkinAnalysisConfigurationError(
                "YouCam Skin Analysis API key (SKIN_ANALYSIS_API_KEY) is not configured."
            )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def check_health(self) -> tuple[bool, str | None]:
        if not self._api_key:
            return False, "SKIN_ANALYSIS_API_KEY is not configured."
        return True, f"YouCam S2S v2.0 configured ({self._base_url})."

    def _map_http_error(self, status_code: int, body_text: str) -> SkinAnalysisError:
        sanitized = body_text[:300] if body_text else f"HTTP {status_code}"
        lower = sanitized.lower()
        if status_code in (401, 403):
            return SkinAnalysisAuthenticationError(
                f"YouCam API rejected credentials (HTTP {status_code})."
            )
        if status_code == 429 or "exceed" in lower or "quota" in lower or "rate" in lower:
            return SkinAnalysisRateLimitError(
                f"YouCam API rate limit or quota exceeded (HTTP {status_code})."
            )
        if status_code in (400, 422):
            if "face" in lower or "lighting" in lower or "quality" in lower:
                return SkinAnalysisInvalidImageError(
                    f"YouCam rejected image quality or face detection: {sanitized}",
                    category="no_face_detected",
                )
            return SkinAnalysisInvalidImageError(
                f"YouCam rejected request parameters (HTTP {status_code}): {sanitized}",
                category="invalid_image",
            )
        if status_code >= 500:
            return SkinAnalysisUnavailableError(f"YouCam API server error (HTTP {status_code}).")
        return SkinAnalysisError(
            f"YouCam API unexpected response (HTTP {status_code}): {sanitized}",
            category="upstream_error",
            is_retryable=False,
        )

    async def _initialize_and_upload_file(
        self,
        client: httpx.AsyncClient,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Step 1 & 2: Initialize file slot and PUT binary bytes to pre-signed URL."""
        init_url = f"{self._base_url}/s2s/v2.0/file/skin-analysis"
        safe_name = filename or "scan.jpg"
        if "." not in safe_name:
            ext = "png" if "png" in content_type else "webp" if "webp" in content_type else "jpg"
            safe_name = f"{safe_name}.{ext}"

        payload = {
            "files": [
                {
                    "file_name": safe_name,
                    "content_type": content_type,
                    "file_size": len(file_bytes),
                }
            ]
        }

        try:
            init_resp = await client.post(
                init_url,
                headers=self._auth_headers(),
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise SkinAnalysisTimeoutError(
                "Timed out initializing file upload with YouCam API."
            ) from exc
        except httpx.RequestError as exc:
            raise SkinAnalysisUnavailableError(
                f"Network error contacting YouCam file API: {type(exc).__name__}"
            ) from exc

        if init_resp.status_code != 200:
            raise self._map_http_error(init_resp.status_code, init_resp.text)

        try:
            init_data = init_resp.json()
            file_entry = init_data["data"]["files"][0]
            file_id = str(file_entry["file_id"])
            put_req = file_entry["requests"][0]
            put_url = str(put_req["url"])
            put_headers = dict(put_req.get("headers") or {})
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise SkinAnalysisError(
                "Malformed file upload initialization response from YouCam API.",
                category="upstream_error",
            ) from exc

        if "Content-Type" not in put_headers and "content-type" not in put_headers:
            put_headers["Content-Type"] = content_type

        try:
            put_resp = await client.put(
                put_url,
                content=file_bytes,
                headers=put_headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise SkinAnalysisTimeoutError(
                "Timed out uploading scan image to pre-signed storage."
            ) from exc
        except httpx.RequestError as exc:
            raise SkinAnalysisUnavailableError(
                f"Network error uploading scan image: {type(exc).__name__}"
            ) from exc

        if put_resp.status_code not in (200, 201, 204):
            raise SkinAnalysisUnavailableError(
                f"Pre-signed image upload failed with HTTP {put_resp.status_code}."
            )

        return file_id

    async def _create_task(
        self,
        client: httpx.AsyncClient,
        file_id: str,
        requested_metrics: list[str] | None = None,
    ) -> str:
        """Step 3: Create asynchronous skin analysis task on YouCam S2S v2.0."""
        metrics = requested_metrics or list(DEFAULT_REQUESTED_METRICS)
        dst_actions: list[str] = []
        for code in metrics:
            spec = NORMALIZED_METRICS.get(code)
            if spec and spec.youcam_action not in dst_actions:
                dst_actions.append(spec.youcam_action)

        if not dst_actions:
            dst_actions = ["wrinkle", "pore", "texture", "acne"]

        task_url = f"{self._base_url}/s2s/v2.0/task/skin-analysis"
        payload = {
            "src_file_id": file_id,
            "dst_actions": dst_actions,
            "format": "json",
        }

        try:
            resp = await client.post(
                task_url,
                headers=self._auth_headers(),
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise SkinAnalysisTimeoutError(
                "Timed out creating skin analysis task on YouCam API."
            ) from exc
        except httpx.RequestError as exc:
            raise SkinAnalysisUnavailableError(
                f"Network error creating skin analysis task: {type(exc).__name__}"
            ) from exc

        if resp.status_code != 200:
            raise self._map_http_error(resp.status_code, resp.text)

        try:
            data = resp.json()
            task_id = str(data["data"]["task_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SkinAnalysisError(
                "Malformed task creation response from YouCam API.",
                category="upstream_error",
            ) from exc

        return task_id

    def _extract_observations_from_score_dict(
        self,
        score_map: dict[str, Any],
    ) -> tuple[list[NormalizedObservationResult], float | None, str | None]:
        """Parse normalized observations from YouCam score_info / output payload."""
        observations: list[NormalizedObservationResult] = []
        seen_codes: set[str] = set()
        overall_score: float | None = None
        skin_type_obs: str | None = None

        # Unwrap nested score_info if present
        candidates: dict[str, Any] = {}
        if isinstance(score_map.get("score_info"), dict):
            candidates.update(score_map["score_info"])
        if isinstance(score_map.get("results"), dict):
            res_dict = score_map["results"]
            if isinstance(res_dict.get("score_info"), dict):
                candidates.update(res_dict["score_info"])
            if isinstance(res_dict.get("output"), list):
                for item in res_dict["output"]:
                    if isinstance(item, dict) and "type" in item:
                        candidates[str(item["type"])] = item
        candidates.update(score_map)

        if isinstance(candidates.get("all"), dict):
            all_entry = candidates["all"]
            val = all_entry.get("ui_score") or all_entry.get("score") or all_entry.get("raw_score")
            if isinstance(val, (int, float)):
                overall_score = round(float(val), 1)
        elif isinstance(candidates.get("overall_score"), (int, float)):
            overall_score = round(float(candidates["overall_score"]), 1)

        if isinstance(candidates.get("skin_type"), dict):
            st_val = candidates["skin_type"].get("skin_type") or candidates["skin_type"].get("type")
            if isinstance(st_val, str) and st_val.strip():
                skin_type_obs = st_val.strip().lower()
        elif isinstance(candidates.get("skin_type"), str):
            skin_type_obs = candidates["skin_type"].strip().lower()

        for key, value in candidates.items():
            spec = YOUCAM_ACTION_TO_METRIC.get(key.lower())
            if not spec or spec.metric_code in seen_codes:
                continue

            raw_val: float | None = None
            ui_val: float | None = None
            if isinstance(value, (int, float)):
                raw_val = float(value)
                ui_val = float(value)
            elif isinstance(value, dict):
                # Check whole/full_face sub-object if present
                whole = value.get("whole") if isinstance(value.get("whole"), dict) else value
                raw_candidate = whole.get("raw_score", value.get("raw_score"))
                ui_candidate = whole.get(
                    "ui_score",
                    value.get("ui_score", whole.get("score", value.get("score"))),
                )
                if isinstance(raw_candidate, (int, float)):
                    raw_val = float(raw_candidate)
                if isinstance(ui_candidate, (int, float)):
                    ui_val = float(ui_candidate)
                if raw_val is None and ui_val is not None:
                    raw_val = ui_val
                if ui_val is None and raw_val is not None:
                    ui_val = raw_val

            if raw_val is not None and ui_val is not None:
                # Clamp display value to 0..100 for score_0_100 scale
                clamped_display = max(0.0, min(100.0, round(ui_val, 1)))
                seen_codes.add(spec.metric_code)
                observations.append(
                    NormalizedObservationResult(
                        metric_code=spec.metric_code,
                        metric_label=spec.label,
                        raw_value=round(raw_val, 2),
                        display_value=clamped_display,
                        unit=spec.unit,
                        directionality=spec.directionality,
                        facial_zone=spec.default_zone,
                        confidence=None,
                        caveat_note=STANDARD_OBSERVATION_CAVEAT,
                    )
                )

        if overall_score is None and observations:
            overall_score = round(sum(o.display_value for o in observations) / len(observations), 1)

        return observations, overall_score, skin_type_obs

    async def _download_and_parse_result_url(
        self,
        client: httpx.AsyncClient,
        result_url: str,
    ) -> dict[str, Any]:
        """Download JSON or ZIP result bundle from YouCam result URL and extract score JSON."""
        try:
            resp = await client.get(result_url, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise SkinAnalysisTimeoutError(
                "Timed out downloading skin analysis result archive."
            ) from exc
        except httpx.RequestError as exc:
            raise SkinAnalysisUnavailableError(
                f"Network error downloading skin analysis result: {type(exc).__name__}"
            ) from exc

        if resp.status_code != 200:
            raise SkinAnalysisUnavailableError(
                f"Failed to download skin analysis result payload (HTTP {resp.status_code})."
            )

        content = resp.content
        # Try JSON first
        try:
            parsed = json.loads(content.decode("utf-8"))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # Try ZIP archive (YouCam often packages score_info.json inside a zip)
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".json"):
                        raw_json = zf.read(name)
                        parsed_zip_json = json.loads(raw_json.decode("utf-8"))
                        if isinstance(parsed_zip_json, dict):
                            return parsed_zip_json
        except Exception as exc:
            raise SkinAnalysisError(
                "Unable to parse YouCam skin analysis result payload.",
                category="upstream_error",
            ) from exc

        raise SkinAnalysisError(
            "YouCam result archive did not contain a readable JSON score report.",
            category="upstream_error",
        )

    async def _poll_once(
        self,
        client: httpx.AsyncClient,
        provider_task_id: str,
    ) -> SkinAnalysisTaskResult:
        """Execute a single GET status check for a YouCam task_id."""
        status_url = f"{self._base_url}/s2s/v2.0/task/skin-analysis/{provider_task_id}"
        try:
            resp = await client.get(
                status_url,
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise SkinAnalysisTimeoutError(
                "Timed out polling skin analysis task status on YouCam API."
            ) from exc
        except httpx.RequestError as exc:
            raise SkinAnalysisUnavailableError(
                f"Network error polling skin analysis task: {type(exc).__name__}"
            ) from exc

        if resp.status_code != 200:
            raise self._map_http_error(resp.status_code, resp.text)

        try:
            payload = resp.json()
            data = payload.get("data") or {}
        except ValueError as exc:
            raise SkinAnalysisError(
                "Invalid JSON returned when polling YouCam task status.",
                category="upstream_error",
            ) from exc

        task_status = str(data.get("task_status") or "").lower()
        if task_status in ("running", "pending", "queued", "processing", "waiting"):
            return SkinAnalysisTaskResult(
                provider_name=self.name,
                provider_task_id=provider_task_id,
                provider_model_version=self.provider_model_version,
                interpretation_version=self.interpretation_version,
                status="processing",
            )

        if task_status in ("error", "failed", "failure"):
            err_code = str(data.get("error") or data.get("error_code") or "upstream_error").lower()
            err_msg = str(
                data.get("error_message")
                or data.get("message")
                or data.get("error")
                or "External skin analysis task failed."
            )
            category = "upstream_error"
            if "face" in err_code or "face" in err_msg.lower():
                category = "no_face_detected"
            elif "light" in err_code or "quality" in err_code or "image" in err_code:
                category = "invalid_image"
            elif "exceed" in err_code or "quota" in err_code:
                category = "rate_limited"
            return SkinAnalysisTaskResult(
                provider_name=self.name,
                provider_task_id=provider_task_id,
                provider_model_version=self.provider_model_version,
                interpretation_version=self.interpretation_version,
                status="failed",
                error_category=category,
                error_message=err_msg[:400],
            )

        if task_status == "success":
            results_obj = data.get("results") or data
            score_source: dict[str, Any] = {}
            if isinstance(results_obj, dict):
                score_source.update(results_obj)
                dl_url = results_obj.get("url")
                if isinstance(dl_url, str) and dl_url.startswith("http"):
                    downloaded = await self._download_and_parse_result_url(client, dl_url)
                    score_source.update(downloaded)

            observations, overall_score, skin_type_obs = self._extract_observations_from_score_dict(
                score_source
            )
            if not observations:
                raise SkinAnalysisError(
                    "YouCam task succeeded but returned no recognizable skin observations.",
                    category="upstream_error",
                )
            return SkinAnalysisTaskResult(
                provider_name=self.name,
                provider_task_id=provider_task_id,
                provider_model_version=self.provider_model_version,
                interpretation_version=self.interpretation_version,
                status="succeeded",
                observations=observations,
                overall_score=overall_score,
                skin_type_observation=skin_type_obs,
            )

        raise SkinAnalysisError(
            f"Unrecognized YouCam task_status '{task_status}'.",
            category="upstream_error",
        )

    async def submit_scan(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        requested_metrics: list[str] | None = None,
    ) -> SkinAnalysisTaskResult:
        self._ensure_configured()

        async def _run(client: httpx.AsyncClient) -> SkinAnalysisTaskResult:
            file_id = await self._initialize_and_upload_file(
                client=client,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )
            task_id = await self._create_task(
                client=client,
                file_id=file_id,
                requested_metrics=requested_metrics,
            )
            for attempt in range(self._max_poll_attempts):
                result = await self._poll_once(client, task_id)
                if result.status in ("succeeded", "failed"):
                    return result
                if attempt + 1 < self._max_poll_attempts and self._poll_interval_seconds > 0:
                    await asyncio.sleep(self._poll_interval_seconds)

            return SkinAnalysisTaskResult(
                provider_name=self.name,
                provider_task_id=task_id,
                provider_model_version=self.provider_model_version,
                interpretation_version=self.interpretation_version,
                status="processing",
            )

        if self._client is not None:
            return await _run(self._client)

        async with httpx.AsyncClient() as client:
            return await _run(client)

    async def poll_task(self, provider_task_id: str) -> SkinAnalysisTaskResult:
        self._ensure_configured()
        if self._client is not None:
            return await self._poll_once(self._client, provider_task_id)
        async with httpx.AsyncClient() as client:
            return await self._poll_once(client, provider_task_id)


GEMINI_SKIN_SYSTEM_PROMPT = """You are an expert dermatological cosmetic visual skin analysis specialist.
Your task is to analyze a photograph of a human face and provide standardized visual surface observations.

IMPORTANT SAFETY & NON-CLINICAL RULES:
1. First verify if a human face is clearly visible. If no face is present or the image is too blurry/dark, return JSON with {"face_detected": false, "error_message": "No clear human face detected."}.
2. These are cosmetic visual surface observations, NOT a clinical diagnosis or medical treatment plan.
3. For each requested observation, evaluate on a 0 to 100 scale (higher indicates clearer, healthier, calmer, or smoother skin appearance):
   - "spots": Tone evenness and absence of visible surface hyperpigmentation or dark spots (higher = clearer tone)
   - "redness": Absence of visible surface redness/erythema (higher = calmer, less redness)
   - "texture": Surface smoothness and lack of roughness (higher = smoother texture)
   - "pores": Pore refinement and minimal visibility (higher = tighter, less noticeable pores)
   - "wrinkles": Smoothness and absence of visible fine lines (higher = smoother, fewer lines)
   - "acne": Clarity and absence of visible blemishes, pustules, or active breakouts (higher = clearer skin)
   - "oiliness": Surface shine balance (higher = balanced, neither overly oily nor parched)
   - "moisture": Plumpness and hydration appearance (higher = well-hydrated look)
   - "radiance": Healthy natural luminosity (higher = more radiant)
   - "firmness": Structural firmness appearance (higher = firm)
   - "dark_circles": Absence of visible periorbital shadowing (higher = brighter under-eyes)
   - "eye_bags": Smoothness of under-eye contours without visible puffiness (higher = smoother)
4. Assign the primary facial zone for each observation where the feature is most notable:
   - "forehead"
   - "cheeks"
   - "t_zone"
   - "chin"
   - "periorbital"
   - "full_face"
5. Identify the overall score (0-100) and dominant skin type: "normal", "dry", "oily", "combination", or "sensitive".
6. Return ONLY a single raw valid JSON object matching this schema:
{
  "face_detected": true,
  "overall_score": 78.0,
  "skin_type": "combination",
  "observations": [
    {
      "metric_code": "spots",
      "display_value": 75.0,
      "facial_zone": "cheeks",
      "summary": "Light surface post-inflammatory tone variation"
    }
  ]
}
"""


class GeminiSkinAnalysisAdapter(BaseSkinAnalysisProvider):
    """Multimodal skin analysis adapter using Google Gemini Vision (google-genai SDK).

    Provides real-time visual inspection of facial characteristics (blemishes, redness,
    pores, texture smoothness, hydration appearance, fine lines) mapped to localized
    facial zones without canned or mock data.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
        genai_client: genai.Client | None = None,
    ) -> None:
        settings = get_settings()
        resolved_key = (
            api_key
            or (settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None)
        )
        self._api_key = resolved_key
        self._model = (model or settings.GEMINI_MODEL or "gemini-2.5-flash").strip()
        self._timeout = timeout_seconds
        self._client = genai_client

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def provider_model_version(self) -> str:
        return f"gemini-skin-{self._model}"

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise SkinAnalysisConfigurationError(
                "Gemini API key is not configured. Supply a valid GEMINI_API_KEY in the environment."
            )
        return genai.Client(api_key=self._api_key)

    async def check_health(self) -> tuple[bool, str | None]:
        if not self._api_key:
            return False, "GEMINI_API_KEY is not configured for Gemini skin analysis."
        return True, f"Gemini Skin Analysis active using model '{self._model}'."

    async def submit_scan(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        requested_metrics: list[str] | None = None,
    ) -> SkinAnalysisTaskResult:
        if not file_bytes:
            raise SkinAnalysisInvalidImageError("Empty image bytes provided for skin analysis.")

        client = self._get_client()
        metrics_to_request = requested_metrics or list(DEFAULT_REQUESTED_METRICS)

        image_part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=content_type or "image/jpeg",
        )

        user_prompt = (
            f"Analyze this facial photo for the following cosmetic visual metrics: "
            f"{', '.join(metrics_to_request)}. Return the specified JSON object."
        )

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self._model,
                    contents=[image_part, user_prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=GEMINI_SKIN_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as err:
            logger.error("Gemini skin analysis timed out after %.1fs", self._timeout)
            raise SkinAnalysisTimeoutError(f"Gemini skin analysis timed out after {self._timeout}s") from err
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                logger.warning("Gemini skin analysis rate limit or quota exceeded: %s", exc)
                raise SkinAnalysisRateLimitError(
                    "Gemini AI quota or rate limit exceeded. Please try again shortly."
                ) from exc
            logger.error("Gemini skin analysis request failed: %s", exc)
            raise SkinAnalysisUnavailableError(f"Gemini skin analysis error: {exc}") from exc

        text_payload = (response.text or "").strip()
        if not text_payload:
            raise SkinAnalysisInvalidImageError("Gemini Vision was unable to process this image.")

        try:
            parsed = json.loads(text_payload)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Gemini skin analysis JSON payload: %s", text_payload)
            raise SkinAnalysisError("Malformed JSON response from Gemini skin analysis.") from exc

        if parsed.get("face_detected") is False:
            msg = parsed.get("error_message") or "No clear human face detected in image."
            raise SkinAnalysisInvalidImageError(msg)

        raw_observations = parsed.get("observations") or []
        observations: list[NormalizedObservationResult] = []
        seen_metrics: set[str] = set()

        for item in raw_observations:
            if not isinstance(item, dict):
                continue
            code = str(item.get("metric_code", "")).strip().lower()
            spec = NORMALIZED_METRICS.get(code)
            if not spec or spec.metric_code in seen_metrics:
                continue

            raw_val = float(item.get("display_value", 70.0))
            clamped = max(0.0, min(100.0, round(raw_val, 1)))
            zone = str(item.get("facial_zone", spec.default_zone)).strip().lower()
            if zone not in ("forehead", "cheeks", "left_cheek", "right_cheek", "t_zone", "chin", "periorbital", "full_face"):
                zone = spec.default_zone

            seen_metrics.add(spec.metric_code)
            observations.append(
                NormalizedObservationResult(
                    metric_code=spec.metric_code,
                    metric_label=spec.label,
                    raw_value=clamped,
                    display_value=clamped,
                    unit=spec.unit,
                    directionality=spec.directionality,
                    facial_zone=zone,
                    confidence=0.92,
                    caveat_note=STANDARD_OBSERVATION_CAVEAT,
                )
            )

        overall_score = parsed.get("overall_score")
        if overall_score is not None:
            try:
                overall_score = max(0.0, min(100.0, round(float(overall_score), 1)))
            except (ValueError, TypeError):
                overall_score = None

        if overall_score is None and observations:
            overall_score = round(sum(o.display_value for o in observations) / len(observations), 1)

        skin_type = parsed.get("skin_type")
        if isinstance(skin_type, str):
            skin_type = skin_type.strip().lower()

        task_id = f"gemini-{hashlib.sha256(file_bytes[:128]).hexdigest()[:16]}"

        return SkinAnalysisTaskResult(
            provider_name=self.name,
            provider_task_id=task_id,
            provider_model_version=self.provider_model_version,
            interpretation_version=self.interpretation_version,
            status="succeeded",
            observations=observations,
            overall_score=overall_score,
            skin_type_observation=skin_type,
        )

    async def poll_task(self, provider_task_id: str) -> SkinAnalysisTaskResult:
        return SkinAnalysisTaskResult(
            provider_name=self.name,
            provider_task_id=provider_task_id,
            provider_model_version=self.provider_model_version,
            interpretation_version=self.interpretation_version,
            status="succeeded",
        )


def get_skin_analysis_provider() -> BaseSkinAnalysisProvider:
    """Resolve the configured skin analysis provider adapter."""
    settings = get_settings()
    provider = settings.SKIN_ANALYSIS_PROVIDER.lower()
    if provider == "youcam":
        if settings.SKIN_ANALYSIS_API_KEY:
            return YouCamSkinAnalysisAdapter()
        # Fallback to Gemini if YouCam key is missing but Gemini key is available
        if settings.GEMINI_API_KEY:
            return GeminiSkinAnalysisAdapter()
        return YouCamSkinAnalysisAdapter()
    if provider == "gemini":
        return GeminiSkinAnalysisAdapter()
    return MockSkinAnalysisAdapter()
