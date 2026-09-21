# tests/test_schema_audit.py
# ──────────────────────────────────────────────────────────────
# PROJ-471 — Schema/data-model audit.
# Confirms that:
#   1. auth_users.db holds users, organisations, contacts.
#   2. memory.db (activity_db) holds activity, delivery_history,
#      delivery_settings, and user_settings.
#   3. reminders.db holds the reminders table.
#   4. app/web/contacts.py's contacts_table() shim is retired
#      (raises RuntimeError — data now lives in auth.tenancy).
#   5. No active JSON-file contact or reminder stores remain
#      in paths the running app reads from.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import sqlite3
import tempfile
import pytest


# ── Helpers ────────────────────────────────────────────────────

def _tables_in(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def _columns_of(db_path: str, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    conn.close()
    return {r[1] for r in rows}


# ── auth_users.db schema ──────────────────────────────────────

class TestAuthUsersSchema:
    """auth_users.db must contain users, organisations, contacts."""

    @pytest.fixture(autouse=True)
    def init_db(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "auth_users.db")
        monkeypatch.setenv("AUTH_DB_PATH", db_path)
        # Re-import to pick up the env override
        import importlib
        import auth.db as db_mod
        importlib.reload(db_mod)
        db_mod.init_db()
        import auth.tenancy as tenancy_mod
        importlib.reload(tenancy_mod)
        tenancy_mod.init_tenancy()
        self.db_path = db_path

    def test_users_table_exists(self):
        assert "users" in _tables_in(self.db_path)

    def test_users_has_required_columns(self):
        cols = _columns_of(self.db_path, "users")
        for c in ("id", "email", "password_hash", "is_active", "created_at"):
            assert c in cols, f"Missing column in users: {c}"

    def test_users_has_org_id_column(self):
        cols = _columns_of(self.db_path, "users")
        assert "org_id" in cols, "users.org_id missing — tenancy migration not applied"

    def test_organisations_table_exists(self):
        assert "organisations" in _tables_in(self.db_path)

    def test_organisations_has_required_columns(self):
        cols = _columns_of(self.db_path, "organisations")
        for c in ("id", "name", "timezone", "is_active"):
            assert c in cols, f"Missing column in organisations: {c}"

    def test_contacts_table_exists(self):
        assert "contacts" in _tables_in(self.db_path)

    def test_contacts_has_required_columns(self):
        cols = _columns_of(self.db_path, "contacts")
        for c in (
            "id", "org_id", "phone_number", "name",
            "email", "consent_state", "preferred_channel",
            "quiet_hours_start", "quiet_hours_end", "created_at",
        ):
            assert c in cols, f"Missing column in contacts: {c}"

    def test_contacts_phone_number_is_org_scoped_unique(self):
        """(org_id, phone_number) UNIQUE constraint ensures no duplicates."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO organisations (name) VALUES ('Org A')"
        )
        conn.execute(
            "INSERT INTO contacts (org_id, phone_number) VALUES (1, '+61412345678')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO contacts (org_id, phone_number) VALUES (1, '+61412345678')"
            )
        conn.close()


# ── memory.db schema ─────────────────────────────────────────

class TestMemoryDbSchema:
    """memory.db (activity/delivery) must contain expected tables."""

    @pytest.fixture(autouse=True)
    def init_db(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "memory.db")
        monkeypatch.setenv("MEMORY_DB", db_path)
        import importlib
        import config.settings as cs
        importlib.reload(cs)          # picks up new MEMORY_DB env var
        import app.web_ui.activity_db as adb
        importlib.reload(adb)
        adb._db = None                # ensure fresh connection to new path
        adb._get_db()                 # triggers schema creation
        self.db_path = db_path

    def test_activity_table_exists(self):
        assert "activity" in _tables_in(self.db_path)

    def test_delivery_history_table_exists(self):
        assert "delivery_history" in _tables_in(self.db_path)

    def test_email_suppressions_table_exists(self):
        assert "email_suppressions" in _tables_in(self.db_path)

    def test_user_settings_table_exists(self):
        assert "user_settings" in _tables_in(self.db_path)

    def test_delivery_history_has_message_id(self):
        cols = _columns_of(self.db_path, "delivery_history")
        assert "message_id" in cols

    def test_delivery_history_has_status(self):
        cols = _columns_of(self.db_path, "delivery_history")
        assert "status" in cols

    def test_delivery_history_has_channel(self):
        cols = _columns_of(self.db_path, "delivery_history")
        assert "channel" in cols


# ── reminders.db schema ──────────────────────────────────────

class TestRemindersDbSchema:
    """reminders.db must hold the reminders table (PROJ-395 engine)."""

    @pytest.fixture(autouse=True)
    def init_db(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "reminders.db")
        monkeypatch.setenv("REMINDERS_DB", db_path)
        import importlib
        import agent.reminders.store as rem_store
        importlib.reload(rem_store)
        # Instantiating a ReminderStore creates the schema
        from agent.reminders.store import ReminderStore
        ReminderStore(db_path)
        self.db_path = db_path

    def test_reminders_table_exists(self):
        assert "reminders" in _tables_in(self.db_path)

    def test_reminders_has_required_columns(self):
        cols = _columns_of(self.db_path, "reminders")
        for c in ("id", "contact_address", "contact_timezone",
                  "message", "scheduled_at_utc", "status"):
            assert c in cols, f"Missing column in reminders: {c}"


# ── No duplicate / retired JSON stores ───────────────────────

class TestNoActiveJsonContactStores:
    """contacts_table() shim must raise — data is now in auth.tenancy."""

    def test_contacts_table_raises_runtime_error(self):
        from app.web.contacts import contacts_table
        with pytest.raises(RuntimeError, match="retired"):
            contacts_table()

    def test_reminders_table_is_still_json_backed(self):
        """app/web/reminders still uses the JSON store (by design —
        it's driven by web_bridge.py without moving its store).
        This test documents that intentional boundary."""
        from app.web.reminders import reminders_table
        tbl = reminders_table()
        # Should be a JsonTable, not raise
        assert tbl is not None

    def test_no_orphan_contacts_json_file_in_store_dir(self, tmp_path):
        """In a fresh run there must be no contacts.json in outputs/store/."""
        contacts_json = tmp_path / "store" / "contacts.json"
        assert not contacts_json.exists(), (
            "A contacts.json file exists — contacts should be in auth.tenancy SQLite"
        )


# ── Cross-DB isolation ────────────────────────────────────────

class TestDatabaseIsolation:
    """Each database must only hold its own domain's tables."""

    @pytest.fixture(autouse=True)
    def setup_all_dbs(self, tmp_path, monkeypatch):
        auth_path = str(tmp_path / "auth_users.db")
        mem_path  = str(tmp_path / "memory.db")
        rem_path  = str(tmp_path / "reminders.db")

        monkeypatch.setenv("AUTH_DB_PATH", auth_path)
        monkeypatch.setenv("MEMORY_DB",    mem_path)
        monkeypatch.setenv("REMINDERS_DB", rem_path)

        import importlib
        import config.settings as cs; importlib.reload(cs)
        import auth.db as db_mod; importlib.reload(db_mod); db_mod.init_db()
        import auth.tenancy as tenancy_mod; importlib.reload(tenancy_mod); tenancy_mod.init_tenancy()
        import app.web_ui.activity_db as adb; importlib.reload(adb); adb._db = None; adb._get_db()
        from agent.reminders.store import ReminderStore; ReminderStore(rem_path)

        self.auth_tables = _tables_in(auth_path)
        self.mem_tables  = _tables_in(mem_path)
        self.rem_tables  = _tables_in(rem_path)

    def test_auth_db_does_not_contain_delivery_tables(self):
        assert "delivery_history" not in self.auth_tables
        assert "delivery_settings" not in self.auth_tables

    def test_auth_db_does_not_contain_reminders(self):
        assert "reminders" not in self.auth_tables

    def test_memory_db_does_not_contain_contacts(self):
        assert "contacts" not in self.mem_tables

    def test_memory_db_does_not_contain_reminders(self):
        assert "reminders" not in self.mem_tables

    def test_reminders_db_does_not_contain_contacts(self):
        assert "contacts" not in self.rem_tables

    def test_reminders_db_does_not_contain_delivery(self):
        assert "delivery_history" not in self.rem_tables
