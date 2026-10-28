"""Gemini language-model provider for Phase 7 grounded skincare explanations.

Implements a replaceable `LLMExplanationProvider` interface backed by the official
Google GenAI SDK (`google-genai` >= 2.30.1) using the Interactions API (`interactions.create`)
with `store=False` and structured JSON output (`response_format`).

Reliability & Security Guarantees:
- Never hard-codes credentials; reads `GEMINI_API_KEY` and `GEMINI_MODEL` from settings.
- Explicitly rejects deprecated legacy models (`gemini-1.5-*`, `gemini-2.0-*`, `gemini-2.5-*`)
  and unsupported model identifiers.
- Treats the Gemini free tier as quota-limited: handles HTTP 429 / RESOURCE_EXHAUSTED
  gracefully without retrying indefinitely or switching silently to another paid provider.
- Uses bounded retries with exponential backoff only for transient 5xx / timeout errors.
- Never exposes internal prompts, API keys, or provider stack traces.
"""

import asyncio
import logging
import time
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from google import genai

from app.core.config import get_settings
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_UNSET = object()

# Supported current Gemini & Gemma models per official Gemini API guidelines
SUPPORTED_GEMINI_MODELS: frozenset[str] = frozenset(
    {
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-pro-latest",
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it",
    }
)

DEPRECATED_GEMINI_PREFIXES: tuple[str, ...] = (
    "gemini-1.0",
    "gemini-1.5",
    "gemini-2.0",
    "gemini-2.5",
)


class LLMProviderError(Exception):
    """Base exception for language-model provider failures."""


class LLMConfigurationError(LLMProviderError):
    """Raised when credentials are missing or the configured model is unsupported."""


class LLMQuotaExhaustedError(LLMProviderError):
    """Raised when Gemini API free-tier or project quota (HTTP 429) is exhausted."""


class LLMTimeoutError(LLMProviderError):
    """Raised when the language-model request exceeds the configured timeout."""


class LLMUpstreamError(LLMProviderError):
    """Raised when the language-model upstream returns a 5xx or unexpected error."""


class LLMInvalidResponseError(LLMProviderError):
    """Raised when the language model returns an empty or unparseable payload."""


@dataclass(slots=True)
class LLMGenerationResult:
    """Normalized result from an LLM structured generation call."""

    raw_text: str
    provider: str
    model: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class LLMExplanationProvider(BaseProvider):
    """Abstract interface for grounded explanation language-model providers.

    Allows substituting a future model or provider without rewriting business logic.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Configured model identifier."""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials and model are valid and ready."""

    @abstractmethod
    async def generate_structured_explanation(
        self,
        system_instruction: str,
        grounded_prompt: str,
        response_schema: dict[str, Any],
    ) -> LLMGenerationResult:
        """Generate a structured JSON explanation constrained by `response_schema`."""


def is_supported_gemini_model(model: str) -> tuple[bool, str | None]:
    """Validate whether a model name is a supported current Gemini/Gemma model."""
    cleaned = model.strip()
    if cleaned.startswith("models/"):
        cleaned = cleaned[len("models/") :]

    if not cleaned:
        return False, "GEMINI_MODEL cannot be empty."

    for prefix in DEPRECATED_GEMINI_PREFIXES:
        if cleaned.startswith(prefix):
            return (
                False,
                f"Model '{cleaned}' is legacy and deprecated. "
                "Please configure a supported current model such as 'gemini-3.5-flash-lite' "
                "or 'gemini-3.8-flash'.",
            )

    if cleaned not in SUPPORTED_GEMINI_MODELS:
        return (
            False,
            f"Model '{cleaned}' is not a supported Gemini explanation model. "
            f"Supported models: {', '.join(sorted(SUPPORTED_GEMINI_MODELS))}.",
        )

    return True, None


class GeminiExplanationProvider(LLMExplanationProvider):
    """Official Google Gemini API explanation provider using `google-genai`."""

    def __init__(
        self,
        api_key: str | None | object = _UNSET,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        genai_client: genai.Client | None = None,
    ) -> None:
        settings = get_settings()
        if api_key is _UNSET:
            resolved_key = (
                settings.GEMINI_API_KEY.get_secret_value().strip()
                if settings.GEMINI_API_KEY
                else None
            )
        else:
            resolved_key = str(api_key).strip() if api_key else None

        self._api_key: str | None = resolved_key or None
        raw_model = (model if model is not None else settings.GEMINI_MODEL).strip()
        if raw_model.startswith("models/"):
            raw_model = raw_model[len("models/") :]
        self._model = raw_model
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.GEMINI_TIMEOUT_SECONDS
        )
        self._max_retries = max_retries if max_retries is not None else settings.GEMINI_MAX_RETRIES
        self._client = genai_client

    @property
    def name(self) -> str:
        return "google_gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        if not self._api_key:
            return False
        supported, _ = is_supported_gemini_model(self._model)
        return supported

    def _validate_configuration(self) -> None:
        """Verify API key presence and model support before making network calls."""
        if not self._api_key:
            raise LLMConfigurationError(
                "Gemini AI explanations are not configured. "
                "Please set a valid GEMINI_API_KEY in the environment."
            )
        supported, reason = is_supported_gemini_model(self._model)
        if not supported:
            raise LLMConfigurationError(reason or f"Unsupported Gemini model: {self._model}")

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client
        timeout_ms = int(max(1.0, self._timeout_seconds) * 1000)
        self._client = genai.Client(
            api_key=self._api_key,
            http_options={"timeout": timeout_ms},
        )
        return self._client

    async def _invoke_gemini_interaction(
        self,
        system_instruction: str,
        grounded_prompt: str,
        response_schema: dict[str, Any],
    ) -> Any:
        """Execute a single non-stored interaction call via the official google-genai SDK."""
        client = self._get_client()
        return await asyncio.wait_for(
            client.aio.interactions.create(
                model=self._model,
                input=grounded_prompt,
                system_instruction=system_instruction,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": response_schema,
                },
                store=False,
            ),
            timeout=self._timeout_seconds,
        )

    @staticmethod
    def _classify_exception(exc: Exception) -> tuple[str, int | None]:
        """Classify SDK / transport exceptions without leaking credentials or internals."""
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
            return "timeout", 504

        status_code: int | None = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        msg_upper = str(exc).upper()

        if (
            status_code == 429
            or "429" in msg_upper
            or "RESOURCE_EXHAUSTED" in msg_upper
            or "QUOTA" in msg_upper
        ):
            return "quota", 429
        if (
            status_code == 504
            or "504" in msg_upper
            or "DEADLINE_EXCEEDED" in msg_upper
            or "TIMED OUT" in msg_upper
        ):
            return "timeout", 504
        if (
            status_code in (401, 403)
            or "API_KEY_INVALID" in msg_upper
            or "UNAUTHENTICATED" in msg_upper
        ):
            return "auth", status_code or 401
        if status_code == 404 or "NOT_FOUND" in msg_upper:
            return "model_not_found", 404
        if status_code in (500, 502, 503) or any(
            code in msg_upper for code in ("500", "502", "503", "UNAVAILABLE", "INTERNAL")
        ):
            return "transient_5xx", status_code or 503

        return "upstream", status_code

    async def generate_structured_explanation(
        self,
        system_instruction: str,
        grounded_prompt: str,
        response_schema: dict[str, Any],
    ) -> LLMGenerationResult:
        """Call Gemini Interactions API with bounded retries and strict error handling."""
        self._validate_configuration()

        attempts = max(1, self._max_retries + 1)
        start_time = time.perf_counter()

        for attempt in range(1, attempts + 1):
            try:
                interaction = await self._invoke_gemini_interaction(
                    system_instruction=system_instruction,
                    grounded_prompt=grounded_prompt,
                    response_schema=response_schema,
                )
                elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

                output_text = getattr(interaction, "output_text", None)
                if not output_text or not str(output_text).strip():
                    raise LLMInvalidResponseError("Gemini returned an empty response payload.")

                usage = getattr(interaction, "usage", None)
                input_tokens = getattr(usage, "total_input_tokens", None) if usage else None
                output_tokens = getattr(usage, "total_output_tokens", None) if usage else None
                total_tokens = getattr(usage, "total_tokens", None) if usage else None

                return LLMGenerationResult(
                    raw_text=str(output_text).strip(),
                    provider=self.name,
                    model=self._model,
                    latency_ms=elapsed_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                )

            except LLMProviderError:
                raise
            except Exception as exc:
                category, status_code = self._classify_exception(exc)
                logger.warning(
                    "Gemini explanation request failed (category=%s, status=%s, attempt=%d/%d)",
                    category,
                    status_code,
                    attempt,
                    attempts,
                )

                if category == "quota":
                    # Never retry quota exhaustion indefinitely or switch to another paid provider
                    raise LLMQuotaExhaustedError(
                        "Gemini AI explanation quota is currently exhausted "
                        "(free-tier or rate limit reached). Please wait a moment and try again. "
                        "Product and ingredient evidence records remain directly accessible "
                        "via the catalog and evidence endpoints."
                    ) from exc

                if category == "auth":
                    raise LLMConfigurationError(
                        "Gemini API authentication failed. "
                        "Please verify the configured GEMINI_API_KEY."
                    ) from exc

                if category == "model_not_found":
                    raise LLMConfigurationError(
                        f"Configured Gemini model '{self._model}' was not found or is unavailable."
                    ) from exc

                # Bounded retry only for transient 5xx or timeout
                if category in ("transient_5xx", "timeout") and attempt < attempts:
                    backoff = 0.4 * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)
                    continue

                if category == "timeout":
                    raise LLMTimeoutError(
                        "The Gemini explanation request timed out before completing. "
                        "Please try again."
                    ) from exc

                raise LLMUpstreamError(
                    "The Gemini AI service encountered a temporary upstream error. "
                    "Please try again later."
                ) from exc

        raise LLMUpstreamError("Gemini explanation generation failed after maximum retry attempts.")

    async def check_health(self) -> tuple[bool, str | None]:
        """Verify provider configuration state without consuming generation quota."""
        if not self._api_key:
            return False, "GEMINI_API_KEY is not configured."
        supported, reason = is_supported_gemini_model(self._model)
        if not supported:
            return False, reason
        return True, f"Configured with model '{self._model}'."
