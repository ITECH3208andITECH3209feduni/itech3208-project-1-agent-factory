# agent/delivery/base.py
# ──────────────────────────────────────────────────────────────
# Common channel interface + retry/backoff (PROJ-430) — Dilraj Singh
#
# Every delivery adapter (SMS, voice, email) implements DeliveryChannel
# so the reminder scheduler can send through any of them with the same
# call shape: channel.send(to, message) -> DeliveryResult. Retry policy
# lives here once, not copy-pasted into each adapter.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class DeliveryResult:
    """Outcome of a single send attempt. `ok=False` with `retriable=True`
    tells the caller it's worth trying again (e.g. a transient network
    or 5xx error); `retriable=False` means retrying won't help (e.g. an
    invalid phone number) and PROJ-397's status tracking should mark it
    failed immediately instead of burning through retry attempts."""

    ok: bool
    channel: str
    to: str
    provider_id: str | None = None
    error: str | None = None
    retriable: bool = False
    attempts: int = 1


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0   # seconds
    backoff_factor: float = 2.0
    max_delay: float = 30.0

    def delay_for(self, attempt: int) -> float:
        """attempt is 1-indexed (the attempt that just failed)."""
        delay = self.base_delay * (self.backoff_factor ** (attempt - 1))
        return min(delay, self.max_delay)


class DeliveryChannel(ABC):
    """Base class every delivery adapter implements."""

    name: str

    @abstractmethod
    def _send_once(self, to: str, message: str, **kwargs) -> DeliveryResult:
        """Perform exactly one send attempt. Adapters implement this,
        not send() — send() wraps this with retry/backoff."""
        raise NotImplementedError

    def send(
        self,
        to: str,
        message: str,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        **kwargs,
    ) -> DeliveryResult:
        return send_with_retry(
            lambda: self._send_once(to, message, **kwargs),
            retry_policy or RetryPolicy(),
            sleep=sleep,
        )


def send_with_retry(
    attempt_fn: Callable[[], DeliveryResult],
    policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
) -> DeliveryResult:
    """Runs attempt_fn up to policy.max_attempts times. Stops early on
    success or on a non-retriable failure. Sleeps with exponential
    backoff between retriable failures. `sleep` is injectable so tests
    don't have to burn real wall-clock time."""
    last_result: DeliveryResult | None = None
    for attempt in range(1, policy.max_attempts + 1):
        result = attempt_fn()
        result.attempts = attempt
        if result.ok or not result.retriable:
            return result
        last_result = result
        if attempt < policy.max_attempts:
            sleep(policy.delay_for(attempt))
    return last_result
