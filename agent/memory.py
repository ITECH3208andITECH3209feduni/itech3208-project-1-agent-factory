# agent/memory.py
# ──────────────────────────────────────────────────────────────
# Lightweight JSON-based memory for session continuity (PROJ-33)
# Stores: query history, skill usage, saved results
# ──────────────────────────────────────────────────────────────

import json
import os
from datetime import datetime
from config.settings import MEMORY_FILE, MAX_HISTORY_ITEMS


class Memory:
    def __init__(self):
        self._path = MEMORY_FILE
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data = self._load()

    # ── Public API ─────────────────────────────────────────────
    def add(self, query: str, skill_used: str, result_summary: str):
        """Record a completed query."""
        entry = {
            "timestamp":     datetime.now().isoformat(),
            "query":         query,
            "skill":         skill_used,
            "summary":       result_summary,
        }
        self._data["history"].append(entry)
        # Trim to keep only the most recent N items
        self._data["history"] = self._data["history"][-MAX_HISTORY_ITEMS:]
        self._data["total_queries"] = self._data.get("total_queries", 0) + 1
        self._save()

    def save_context(self, query: str, skill: str, summary: str):
        """
        PROJ-33: Save query context with timestamp, query, skill name,
        and first 200 chars of the result summary.

        This is the spec-compliant entry point for the orchestrator to
        persist context after a successful agent.run(). Internally it
        delegates to add() so behavior stays consistent with the rest
        of the Memory API.
        """
        truncated = (summary or "")[:200]
        self.add(query=query, skill_used=skill, result_summary=truncated)

    def get_last_context(self) -> dict | None:
        """
        PROJ-33: Return the most recently saved context entry,
        or None if no history exists yet.
        """
        if not self._data["history"]:
            return None
        return self._data["history"][-1]

    def get_history(self, last_n: int = 5) -> list[dict]:
        """Return the last N queries."""
        return self._data["history"][-last_n:]

    def get_context_string(self, last_n: int = 3) -> str:
        """Return recent history as a string for the orchestrator prompt."""
        history = self.get_history(last_n)
        if not history:
            return "No previous queries."
        lines = []
        for h in history:
            ts   = h["timestamp"][:16].replace("T", " ")
            lines.append(f"[{ts}] ({h['skill']}) '{h['query']}' → {h['summary']}")
        return "\n".join(lines)

    def stats(self) -> dict:
        return {
            "total_queries":   self._data.get("total_queries", 0),
            "history_count":   len(self._data["history"]),
            "session_started": self._data.get("session_started", "unknown"),
        }

    def clear(self):
        """Wipe all history."""
        self._data = self._blank()
        self._save()

    # ── Internal ───────────────────────────────────────────────
    def _blank(self) -> dict:
        return {
            "session_started": datetime.now().isoformat(),
            "total_queries":   0,
            "history":         [],
        }

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