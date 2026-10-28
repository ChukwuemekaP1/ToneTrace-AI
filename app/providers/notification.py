"""Notification provider abstraction and local development recording adapter.

Phase 10 rules:
- Provide a replaceable notification-provider interface (`BaseNotificationProvider`).
- For local development and automated tests, use `LocalRecordingNotificationAdapter`
  which records the intended notification in memory and database audit records
  WITHOUT transmitting it externally.
- The local notification adapter MUST be clearly distinguished from actual delivery
  (`is_simulated=True`, `actual_external_delivery=False`,
  `delivery_status="recorded_local_not_sent"`).
- Add a real email or push provider only after its credentials and delivery contract
  are confirmed.
"""

import uuid
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any, Literal

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.providers.base import BaseProvider


class NotificationProviderError(Exception):
    """Base exception for notification provider errors."""


class NotificationDeliveryError(NotificationProviderError):
    """Raised when a notification provider fails to deliver or record a reminder."""


@dataclass(slots=True)
class NotificationMessage:
    """Normalized outbound reminder notification payload."""

    idempotency_key: str
    user_id: uuid.UUID
    channel: Literal["in_app", "email", "push"]
    title: str
    body: str
    scheduled_for_utc: datetime
    user_timezone: str
    user_local_time: str
    routine_id: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NotificationReceipt:
    """Normalized receipt returned by a notification provider."""

    provider: str
    channel: str
    idempotency_key: str
    delivery_status: Literal["recorded_local_not_sent", "delivered_external", "failed"]
    is_simulated: bool
    actual_external_delivery: bool
    provider_message_id: str | None
    recorded_at: datetime
    delivery_disclosure: str
    error_message: str | None = None


class BaseNotificationProvider(BaseProvider):
    """Abstract interface for routine reminder and alert notification providers."""

    @property
    @abstractmethod
    def is_simulated_delivery(self) -> bool:
        """Return True if this adapter only records notifications locally without sending."""

    @abstractmethod
    async def send_notification(self, message: NotificationMessage) -> NotificationReceipt:
        """Process or transmit a notification message and return a normalized receipt."""


class LocalRecordingNotificationAdapter(BaseNotificationProvider):
    """Local development and test adapter that records notifications without external transmission.

    Explicitly marks all receipts with `is_simulated=True`,
    `actual_external_delivery=False`, and `delivery_status="recorded_local_not_sent"`
    so callers and operators never confuse local recording with live push/email delivery.
    """

    def __init__(self, simulate_failure_reason: str | None = None) -> None:
        self._recorded: list[tuple[NotificationMessage, NotificationReceipt]] = []
        self._simulate_failure_reason = simulate_failure_reason

    @property
    def name(self) -> str:
        return "local_test_recorder"

    @property
    def is_simulated_delivery(self) -> bool:
        return True

    @property
    def recorded_messages(self) -> list[tuple[NotificationMessage, NotificationReceipt]]:
        """Return a copy of all messages recorded by this adapter instance."""
        return list(self._recorded)

    def clear_recorded(self) -> None:
        """Clear in-memory recorded messages (useful between tests)."""
        self._recorded.clear()

    def set_simulated_failure(self, reason: str | None) -> None:
        """Configure or clear a simulated delivery failure for testing error handling."""
        self._simulate_failure_reason = reason

    async def check_health(self) -> tuple[bool, str | None]:
        """Verify local recording adapter readiness."""
        if self._simulate_failure_reason:
            return False, f"Simulated failure active: {self._simulate_failure_reason}"
        return (
            True,
            "Local recording notification adapter active (simulated; no external transmission).",
        )

    async def send_notification(self, message: NotificationMessage) -> NotificationReceipt:
        """Record the intended notification in memory without sending externally."""
        if self._simulate_failure_reason:
            raise NotificationDeliveryError(self._simulate_failure_reason)

        now = datetime.now(UTC)
        receipt = NotificationReceipt(
            provider=self.name,
            channel=message.channel,
            idempotency_key=message.idempotency_key,
            delivery_status="recorded_local_not_sent",
            is_simulated=True,
            actual_external_delivery=False,
            provider_message_id=f"local-sim-{uuid.uuid4()}",
            recorded_at=now,
            delivery_disclosure=(
                "SIMULATED LOCAL RECORDING ONLY: This notification was captured by the "
                "local test adapter and was NOT transmitted via an external email or push "
                "service."
            ),
            error_message=None,
        )
        self._recorded.append((message, receipt))
        return receipt


@lru_cache(maxsize=1)
def _get_default_local_adapter() -> LocalRecordingNotificationAdapter:
    return LocalRecordingNotificationAdapter()


def get_notification_provider(
    settings: Annotated[Settings | None, Depends(get_settings)] = None,
) -> BaseNotificationProvider:
    """Resolve the active notification provider adapter."""
    _ = settings or get_settings()
    return _get_default_local_adapter()
