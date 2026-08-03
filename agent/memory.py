# agent/memory.py
# ──────────────────────────────────────────────────────────────
# SessionMemory: SQLite-backed session memory (replaces memory.json)
#
# Schema
#   queries(id, timestamp, query, skill, summary, session_id)
#   meta(key, value)   — total_queries, db_created_at, migrated_from_json
#
# On first run, any existing memory.json is migrated automatically
# and renamed to memory.json.migrated so it is never re-imported.
# ──────────────────────────────────────────────────────────────

import json
import os
import sqlite3
import uuid
from datetime import datetime

from config.settings import MEMORY_DB, MEMORY_FILE, MAX_HISTORY_ITEMS


_SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT    NOT NULL,
    query      TEXT    NOT NULL,
    skill      TEXT    NOT NULL,
    summary    TEXT    NOT NULL DEFAULT '',
    session_id TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_queries_session
    ON queries (session_id);
"""


class SessionMemory:
    """
    SQLite-backed session memory.
    Drop-in replacement for the legacy Memory class — same public API.
    """

    def __init__(self, db_path: str = None):
        self._path      = db_path or MEMORY_DB
        self._session   = str(uuid.uuid4())
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL mode: readers don't block writers; safe for web + CLI sharing one file
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._apply_schema()
        self._migrate_from_json()

    # ── Public API ─────────────────────────────────────────────

    def add(self, query: str, skill_used: str, result_summary: str) -> None:
        """Record a completed query in the current session."""
        self._conn.execute(
            "INSERT INTO queries (timestamp, query, skill, summary, session_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                query,
                skill_used,
                (result_summary or "")[:200],
                self._session,
            ),
        )
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES ('total_queries', '1')"
            " ON CONFLICT(key)"
            " DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)"
        )
        self._conn.commit()

    def save_context(self, query: str, skill: str, summary: str) -> None:
        """Spec-compliant entry point used by the orchestrator (PROJ-33)."""
        self.add(query=query, skill_used=skill, result_summary=summary)

    def get_last_context(self) -> dict | None:
        """Return the most recently saved context entry, or None."""
        row = self._conn.execute(
            "SELECT timestamp, query, skill, summary"
            " FROM queries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_history(self, last_n: int = 5) -> list[dict]:
        """Return the last N query records across all sessions, oldest first."""
        rows = self._conn.execute(
            "SELECT timestamp, query, skill, summary"
            " FROM queries ORDER BY id DESC LIMIT ?",
            (last_n,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_context_string(self, last_n: int = 3) -> str:
        """Return recent history formatted for the orchestrator routing prompt."""
        history = self.get_history(last_n)
        if not history:
            return "No previous queries."
        lines = []
        for h in history:
            ts = h["timestamp"][:16].replace("T", " ")
            lines.append(f"[{ts}] ({h['skill']}) '{h['query']}' → {h['summary']}")
        return "\n".join(lines)

    def stats(self) -> dict:
        total   = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'total_queries'"
        ).fetchone()
        created = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'db_created_at'"
        ).fetchone()
        count   = self._conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
        return {
            "total_queries":   int(total["value"]) if total else count,
            "history_count":   count,
            "session_started": created["value"] if created else "unknown",
            "current_session": self._session,
        }

    def clear(self) -> None:
        """Wipe all history and reset counters."""
        self._conn.execute("DELETE FROM queries")
        self._conn.execute("DELETE FROM meta")
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES ('db_created_at', ?)",
            (datetime.now().isoformat(),),
        )
        self._conn.commit()

    # ── Internal ───────────────────────────────────────────────

    def _apply_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('db_created_at', ?)",
            (datetime.now().isoformat(),),
        )
        self._conn.commit()

    def _migrate_from_json(self) -> None:
        """
        One-shot migration from memory.json → SQLite.

        Runs only when:
          - memory.json exists, AND
          - the 'migrated_from_json' sentinel is absent from meta

        After a successful import the JSON file is renamed to
        memory.json.migrated so it is never re-processed.
        """
        if not os.path.exists(MEMORY_FILE):
            return

        already_done = self._conn.execute(
            "SELECT 1 FROM meta WHERE key = 'migrated_from_json'"
        ).fetchone()
        if already_done:
            return

        try:
            with open(MEMORY_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return

        history = data.get("history", [])
        migrated = 0
        for entry in history:
            q = entry.get("query", "").strip()
            if not q:
                continue
            self._conn.execute(
                "INSERT INTO queries (timestamp, query, skill, summary, session_id)"
                " VALUES (?, ?, ?, ?, 'migrated')",
                (
                    entry.get("timestamp", datetime.now().isoformat()),
                    q,
                    entry.get("skill", "unknown"),
                    (entry.get("summary") or "")[:200],
                ),
            )
            migrated += 1

        # Preserve original total_queries count from JSON
        json_total = data.get("total_queries", migrated)
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('total_queries', ?)",
            (str(json_total),),
        )
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES ('migrated_from_json', ?)",
            (datetime.now().isoformat(),),
        )
        self._conn.commit()

        # Rename so it is never re-imported; keep as a backup
        try:
            os.rename(MEMORY_FILE, MEMORY_FILE + ".migrated")
        except OSError:
            pass  # migration succeeded even if rename fails


# ── Legacy class (kept for any direct imports) ─────────────────
class Memory:
    """Deprecated — use SessionMemory. Kept to avoid import errors."""

    def __init__(self):
        self._path = MEMORY_FILE
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data = self._load()

    def add(self, query: str, skill_used: str, result_summary: str):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "query":     query,
            "skill":     skill_used,
            "summary":   result_summary,
        }
        self._data["history"].append(entry)
        self._data["history"] = self._data["history"][-MAX_HISTORY_ITEMS:]
        self._data["total_queries"] = self._data.get("total_queries", 0) + 1
        self._save()

    def save_context(self, query: str, skill: str, summary: str):
        self.add(query=query, skill_used=skill, result_summary=(summary or "")[:200])

    def get_last_context(self) -> dict | None:
        if not self._data["history"]:
            return None
        return self._data["history"][-1]

    def get_history(self, last_n: int = 5) -> list[dict]:
        return self._data["history"][-last_n:]

    def get_context_string(self, last_n: int = 3) -> str:
        history = self.get_history(last_n)
        if not history:
            return "No previous queries."
        lines = []
        for h in history:
            ts = h["timestamp"][:16].replace("T", " ")
            lines.append(f"[{ts}] ({h['skill']}) '{h['query']}' → {h['summary']}")
        return "\n".join(lines)

    def stats(self) -> dict:
        return {
            "total_queries":   self._data.get("total_queries", 0),
            "history_count":   len(self._data["history"]),
            "session_started": self._data.get("session_started", "unknown"),
        }

    def clear(self):
        self._data = self._blank()
        self._save()

    def _blank(self) -> dict:
        return {"session_started": datetime.now().isoformat(), "total_queries": 0, "history": []}

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                pass
        return self._blank()

    def _save(self):
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)
