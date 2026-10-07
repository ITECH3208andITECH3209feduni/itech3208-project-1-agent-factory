"""
app.web.store — JSON-backed tables with int ids and org scoping.

The published contract (PROJ-404) uses integer ids and org_id on every row, so
storage has to hand out sequential ints and scope reads by org. This is the one
place that happens; contacts and reminders both sit on it.

Deliberately a JSON file per table, not a database. Dhiman's Accounts work
(PROJ-405/406) brings real persistence and is not merged to master yet, so this
is the layer that gets replaced — not the services above it.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("agent_factory.store")

# There is no tenancy on master yet: PROJ-392/405/406 (Accounts &
# Multi-tenancy) live on an unmerged branch. Everything therefore belongs to
# one implicit org. Scoping is threaded through anyway, so when accounts land
# the only change is where this value comes from.
DEFAULT_ORG_ID = 1


class JsonTable:
    """
    One table in one JSON file.

    Rows are dicts with int `id` and int `org_id`. Ids are assigned
    sequentially from max(existing)+1 — never reused, so a deleted id cannot
    silently come back attached to a different record.
    """

    def __init__(self, path: Path, name: str):
        self.path = path
        self.name = name
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── disk ──────────────────────────────────────────────────
    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # Never silently return empty — that reads as "all your data is
            # gone" and is the worst possible failure for a store.
            log.error("%s store unreadable at %s: %s", self.name, self.path, exc)
            raise RuntimeError(f"{self.name} store is unreadable: {exc}") from exc
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict[str, Any]]) -> None:
        # Temp file + rename: a half-written file loses every row, not one.
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    # ── reads ─────────────────────────────────────────────────
    def all(self, org_id: int = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
        return [r for r in self._read() if int(r.get("org_id", DEFAULT_ORG_ID)) == org_id]

    def get(self, row_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
        # Scoped by org as well as id, so a guessed id from another org is a
        # 404 rather than a cross-tenant read.
        return next((r for r in self.all(org_id) if int(r["id"]) == int(row_id)), None)

    def find(self, org_id: int = DEFAULT_ORG_ID, **match: Any) -> dict[str, Any] | None:
        for row in self.all(org_id):
            if all(row.get(k) == v for k, v in match.items()):
                return row
        return None

    # ── writes ────────────────────────────────────────────────
    def insert(self, fields: dict[str, Any], org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
        with self._lock:
            rows = self._read()
            next_id = max((int(r.get("id", 0)) for r in rows), default=0) + 1
            row = {"id": next_id, "org_id": org_id, **fields}
            rows.append(row)
            self._write(rows)
            return row

    def update(self, row_id: int, fields: dict[str, Any], org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
        with self._lock:
            rows = self._read()
            for i, row in enumerate(rows):
                if int(row.get("id", 0)) == int(row_id) and int(row.get("org_id", DEFAULT_ORG_ID)) == org_id:
                    # id and org_id are not client-writable.
                    row.update({k: v for k, v in fields.items() if k not in ("id", "org_id")})
                    rows[i] = row
                    self._write(rows)
                    return row
        return None

    def delete(self, row_id: int, org_id: int = DEFAULT_ORG_ID) -> bool:
        with self._lock:
            rows = self._read()
            kept = [
                r for r in rows
                if not (int(r.get("id", 0)) == int(row_id)
                        and int(r.get("org_id", DEFAULT_ORG_ID)) == org_id)
            ]
            if len(kept) == len(rows):
                return False
            self._write(kept)
            return True

    def append_only_insert(self, fields: dict[str, Any], org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
        """Insert with no update or delete path — for audit trails (PROJ-413)."""
        return self.insert(fields, org_id=org_id)


# ── Table registry ────────────────────────────────────────────
_tables: dict[str, JsonTable] = {}


def table(name: str) -> JsonTable:
    """Get (or lazily create) a table. Paths resolve from the project root."""
    if name not in _tables:
        from config.settings import PROJECT_ROOT

        _tables[name] = JsonTable(Path(PROJECT_ROOT) / "store" / f"{name}.json", name)
    return _tables[name]


def set_table(name: str, tbl: JsonTable | None) -> None:
    """Override or clear a table. For tests, and for real persistence later."""
    if tbl is None:
        _tables.pop(name, None)
    else:
        _tables[name] = tbl


def reset_tables() -> None:
    _tables.clear()
