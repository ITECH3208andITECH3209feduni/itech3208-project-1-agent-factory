# skills/rate_limiter.py
# ──────────────────────────────────────────────────────────────
# Client-side token-bucket rate limiter (PROJ-379)
#
# Semantic Scholar allows 100 requests / 5 minutes on an API key.
# Retrying after a 429 (see LiteratureSkill._retry_get) is reactive —
# we still burn the request and eat the penalty wait. This limiter is
# proactive: it refuses to let us exceed the budget in the first place.
# ──────────────────────────────────────────────────────────────

import threading
import time


class TokenBucket:
    """
    Thread-safe token bucket.

    Starts full, so a cold process can burst up to `capacity` immediately.
    Tokens then refill continuously at `capacity / period` per second — not
    in a lump at the end of each window, which would let a caller fire
    2x capacity across a window boundary.
    """

    def __init__(self, capacity: int, period_sec: float, name: str = "bucket"):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if period_sec <= 0:
            raise ValueError("period_sec must be positive")

        self.capacity   = float(capacity)
        self.period_sec = float(period_sec)
        self.name       = name
        self._rate      = self.capacity / self.period_sec   # tokens per second
        self._tokens    = self.capacity
        self._updated   = time.monotonic()
        self._lock      = threading.Lock()

    # ── Internal ──────────────────────────────────────────────
    def _refill(self) -> None:
        """Add tokens accrued since the last check. Caller must hold the lock."""
        now     = time.monotonic()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self._rate)
            self._updated = now

    # ── Public API ────────────────────────────────────────────
    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        """
        Block until `tokens` are available, then consume them.

        Returns True once consumed. Returns False if `timeout` seconds elapse
        first (nothing is consumed in that case). timeout=None waits forever.
        """
        if tokens > self.capacity:
            raise ValueError(
                f"cannot acquire {tokens} tokens from a bucket of capacity {int(self.capacity)}"
            )

        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                # How long until enough tokens accrue?
                shortfall = tokens - self._tokens
                wait      = shortfall / self._rate

            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait = min(wait, remaining)

            # Sleep outside the lock so other threads can make progress.
            time.sleep(max(wait, 0.01))

    def try_acquire(self, tokens: int = 1) -> bool:
        """Consume `tokens` if available right now. Never blocks."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def available(self) -> float:
        """Tokens currently available (refilled to now). Useful for tests/telemetry."""
        with self._lock:
            self._refill()
            return self._tokens

    def __repr__(self) -> str:
        return (
            f"<TokenBucket {self.name}: {self.available:.1f}/{self.capacity:.0f} "
            f"per {self.period_sec:.0f}s>"
        )
