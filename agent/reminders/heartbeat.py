# agent/reminders/heartbeat.py
# Liveness signal for the reminder loops (PROJ-468). Each loop touches a file
# every tick; GET /status/scheduler reports how stale it is.

from __future__ import annotations

import os
import time

from config.settings import OUTPUT_DIR, REMINDER_POLL_INTERVAL_SECONDS

HEARTBEAT_PATH = os.environ.get("SCHEDULER_HEARTBEAT") or os.path.join(OUTPUT_DIR, "scheduler.heartbeat")


def beat(path: str | None = None) -> None:
    path = path or HEARTBEAT_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(str(time.time()))


def age_seconds(path: str | None = None) -> float | None:
    path = path or HEARTBEAT_PATH
    try:
        return time.time() - float(open(path).read().strip())
    except (OSError, ValueError):
        return None


def max_age_seconds() -> float:
    return max(REMINDER_POLL_INTERVAL_SECONDS * 3, 60)
