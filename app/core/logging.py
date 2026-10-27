"""Structured logging configuration for ToneTrace AI.

Provides JSON-formatted or structured log records with contextual request IDs,
environment metadata, and automatic secret redaction.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from typing import Any

# Context variable to hold request_id across async coroutines
request_id_ctx: ContextVar[str | None] = ContextVar("request_id_ctx", default=None)

# Patterns for sensitive keys whose values must be masked if logged in dictionaries
SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|secret|token|api_key|apikey|authorization|jwt|credential|bearer)",
    re.IGNORECASE,
)


def mask_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive values from dictionaries or strings."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if SENSITIVE_KEY_PATTERNS.search(str(k)):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = mask_sensitive_data(v)
        return sanitized
    if isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


class StructuredLogFormatter(logging.Formatter):
    """Custom formatter rendering logs as JSON or key-value with request context."""

    def __init__(self, json_output: bool = True) -> None:
        super().__init__()
        self.json_output = json_output

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()

        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if req_id:
            log_data["request_id"] = req_id

        # Include custom extra attributes if passed
        extra_attrs = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "id",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            )
        }
        if extra_attrs:
            log_data["extra"] = mask_sensitive_data(extra_attrs)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if self.json_output:
            return json.dumps(log_data, default=str)

        req_str = f" [{req_id}]" if req_id else ""
        return (
            f"{log_data['timestamp']} [{record.levelname}]{req_str} "
            f"{record.name}: {record.getMessage()}"
        )


def setup_logging(debug: bool = False, json_logs: bool = True) -> None:
    """Configure root and application loggers."""
    log_level = logging.DEBUG if debug else logging.INFO

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(StructuredLogFormatter(json_output=json_logs))
    root_logger.addHandler(handler)

    # Tone down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
