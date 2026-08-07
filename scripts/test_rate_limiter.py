#!/usr/bin/env python3
# scripts/test_rate_limiter.py
# ──────────────────────────────────────────────────────────────
# Smoke test for the Semantic Scholar token bucket (PROJ-379).
# Run: python scripts/test_rate_limiter.py
#
# Uses a small, fast bucket rather than the real 100/300s budget so the
# whole suite finishes in about a second.
# ──────────────────────────────────────────────────────────────

import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.rate_limiter import TokenBucket

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


def main() -> int:
    print("Token bucket — Semantic Scholar rate limiter (PROJ-379)\n")

    # 5 tokens per second, so refill is 5 tokens/sec.
    b = TokenBucket(capacity=5, period_sec=1.0, name="test")

    check("starts full", b.available == 5, f"got {b.available}")

    # A cold process should be able to burst the full capacity.
    burst = all(b.try_acquire() for _ in range(5))
    check("bursts up to capacity", burst)
    check("refuses once drained", not b.try_acquire())

    # Continuous refill, not a lump at the window edge.
    time.sleep(0.4)
    avail = b.available
    check("refills continuously", 1.5 < avail < 3.0, f"expected ~2 after 0.4s, got {avail:.2f}")

    # Blocking acquire succeeds once a token accrues.
    t0 = time.monotonic()
    got = b.acquire(timeout=2.0)
    check("acquire() blocks then succeeds", got, f"waited {time.monotonic() - t0:.3f}s")

    # Timeout path consumes nothing.
    while b.try_acquire():
        pass
    t0 = time.monotonic()
    timed_out = b.acquire(tokens=5, timeout=0.2) is False
    elapsed = time.monotonic() - t0
    check("acquire() honours timeout", timed_out and 0.15 < elapsed < 0.6, f"elapsed {elapsed:.2f}s")

    # Asking for more than the bucket can ever hold is a programming error.
    try:
        b.acquire(tokens=99)
        check("rejects over-capacity request", False, "no ValueError raised")
    except ValueError:
        check("rejects over-capacity request", True)

    # Concurrency: 20 threads racing for 10 tokens must hand out exactly 10.
    b2 = TokenBucket(capacity=10, period_sec=600.0, name="race")
    granted = []
    lock = threading.Lock()

    def worker():
        if b2.try_acquire():
            with lock:
                granted.append(1)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("thread-safe under contention", len(granted) == 10, f"granted {len(granted)}, expected 10")

    # Constructor validation.
    for bad_args in ((0, 1.0), (-1, 1.0), (1, 0.0), (1, -5.0)):
        try:
            TokenBucket(capacity=bad_args[0], period_sec=bad_args[1])
            check(f"rejects {bad_args}", False, "no ValueError raised")
            break
        except ValueError:
            pass
    else:
        check("rejects invalid constructor args", True)

    # The real configured bucket should be importable and sanely sized.
    from config.settings import S2_RATE_LIMIT_REQUESTS, S2_RATE_LIMIT_PERIOD
    check(
        "configured S2 budget is sane",
        S2_RATE_LIMIT_REQUESTS > 0 and S2_RATE_LIMIT_PERIOD > 0,
        f"{S2_RATE_LIMIT_REQUESTS} per {S2_RATE_LIMIT_PERIOD}s",
    )
    print(f"\n  (configured: {S2_RATE_LIMIT_REQUESTS} requests per {S2_RATE_LIMIT_PERIOD:.0f}s)")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
