# app/web_ui/activity_db.py
# ──────────────────────────────────────────────────────────────
# SQLite activity table for receptionist interactions.
# Shares memory.db with the session memory module (separate table).
# PROJ-387 (Prabhjot Singh) · PROJ-390 (Saifur Rahman Bhuiyan)
# ──────────────────────────────────────────────────────────────

import os
import sqlite3
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config.settings import MEMORY_DB

_SCHEMA = """
CREATE TABLE IF NOT EXISTS activity (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    channel   TEXT    NOT NULL,
    caller    TEXT    NOT NULL DEFAULT '',
    intent    TEXT    NOT NULL DEFAULT '',
    summary   TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity (timestamp);
"""

_db: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(os.path.abspath(MEMORY_DB)), exist_ok=True)
        _db = sqlite3.connect(MEMORY_DB, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.executescript(_SCHEMA)
    return _db


def log_activity(channel: str, caller: str, intent: str = "", summary: str = "") -> None:
    """Insert one interaction row into the activity table."""
    db = _get_db()
    db.execute(
        "INSERT INTO activity (timestamp, channel, caller, intent, summary)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            channel,
            caller,
            (intent or "")[:100],
            (summary or "")[:300],
        ),
    )
    db.commit()


def get_recent(limit: int = 50) -> list[dict]:
    """Return the last `limit` interactions, newest first, with human time."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["time"] = _time_ago(d["timestamp"])
        result.append(d)
    return result


def get_stats_today() -> dict:
    """Return today's call / SMS / booked counts."""
    db = _get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT channel, intent FROM activity WHERE timestamp >= ?", (today,)
    ).fetchall()
    calls   = sum(1 for r in rows if r["channel"] == "voice")
    sms     = sum(1 for r in rows if r["channel"] == "sms")
    booked  = sum(
        1 for r in rows
        if any(kw in (r["intent"] or "").lower() for kw in ("book", "appoint", "schedul"))
    )
    return {"calls": calls, "sms": sms, "appointments": booked}


def _time_ago(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        s = int((datetime.now(timezone.utc) - dt).total_seconds())
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return dt.strftime("%b %d")
    except Exception:
        return (ts or "")[:16]
