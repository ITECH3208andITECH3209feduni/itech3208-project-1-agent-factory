# auth/tenancy.py
# ──────────────────────────────────────────────────────────────
# Organisation + tenant isolation schema (PROJ-405)
#
# Design decisions (no spec was given on the ticket):
#   - One user belongs to exactly one organisation. Simpler to
#     enforce than a many-to-many, and nothing in this epic
#     needs a user in two orgs.
#   - A "contact" is someone the org sends SMS to, not a login
#     user. Contacts are org-scoped and carry consent state.
#   - Every tenant-owned table carries org_id, so scoping is one
#     consistent rule rather than a per-table special case.
#   - Existing users predate organisations, so the migration
#     moves them into a single default org rather than orphaning
#     them.
# ──────────────────────────────────────────────────────────────

import sqlite3

from auth.db import get_conn

DEFAULT_ORG_NAME = "Default Organisation"

TENANCY_SCHEMA = """
CREATE TABLE IF NOT EXISTS organisations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    contact_email TEXT,
    timezone   TEXT    NOT NULL DEFAULT 'Australia/Melbourne',
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Contacts are SMS recipients owned by an org, not login users.
CREATE TABLE IF NOT EXISTS contacts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id             INTEGER NOT NULL,
    phone_number       TEXT    NOT NULL,
    name               TEXT,
    email              TEXT,
    consent_state      TEXT    NOT NULL DEFAULT 'unknown',
    preferred_channel  TEXT    NOT NULL DEFAULT 'sms',
    quiet_hours_start  TEXT,
    quiet_hours_end    TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (org_id) REFERENCES organisations(id),
    UNIQUE (org_id, phone_number)
);

CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(org_id);
CREATE INDEX IF NOT EXISTS idx_users_org    ON users(org_id);
"""


def init_tenancy() -> None:
    """Create org/contact tables and migrate existing users. Idempotent."""
    with get_conn() as conn:
        # users.org_id must exist before the index in TENANCY_SCHEMA
        # references it, so add the column first.
        _add_org_id_to_users(conn)
        conn.executescript(TENANCY_SCHEMA)
        _backfill_default_org(conn)
        _add_contact_profile_fields(conn)


def _add_contact_profile_fields(conn: sqlite3.Connection) -> None:
    """
    Add email/consent_state/preferred_channel/quiet_hours_* to contacts
    for databases created before app/web/contacts.py (PROJ-417-421,
    440-441) was pointed at this table instead of its own JSON store.
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(contacts)")}
    additions = {
        "email": "TEXT",
        "consent_state": "TEXT NOT NULL DEFAULT 'unknown'",
        "preferred_channel": "TEXT NOT NULL DEFAULT 'sms'",
        "quiet_hours_start": "TEXT",
        "quiet_hours_end": "TEXT",
    }
    for col, decl in additions.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE contacts ADD COLUMN {col} {decl}")


def _add_org_id_to_users(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "org_id" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN org_id INTEGER REFERENCES organisations(id)")
    if "role" not in cols:
        # 'owner' created the org; 'member' was invited into it.
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'member'")


def _backfill_default_org(conn: sqlite3.Connection) -> None:
    """Put any pre-existing user into a default org so nothing is orphaned."""
    orphans = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE org_id IS NULL"
    ).fetchone()["n"]
    if not orphans:
        return

    row = conn.execute(
        "SELECT id FROM organisations WHERE name = ?", (DEFAULT_ORG_NAME,)
    ).fetchone()
    if row:
        org_id = row["id"]
    else:
        cur = conn.execute(
            "INSERT INTO organisations (name) VALUES (?)", (DEFAULT_ORG_NAME,)
        )
        org_id = cur.lastrowid

    conn.execute("UPDATE users SET org_id = ? WHERE org_id IS NULL", (org_id,))


# ── Organisations ──────────────────────────────────────────────
def create_org(name: str, contact_email: str | None = None,
               timezone: str = "Australia/Melbourne") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO organisations (name, contact_email, timezone) VALUES (?, ?, ?)",
            (name.strip(), contact_email, timezone),
        )
        return cur.lastrowid


def get_org(org_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM organisations WHERE id = ?", (org_id,)
        ).fetchone()


def update_org(org_id: int, name: str | None = None,
               contact_email: str | None = None,
               timezone: str | None = None) -> None:
    """Update only the fields that were supplied (PROJ-409)."""
    sets, params = [], []
    if name is not None:
        sets.append("name = ?")
        params.append(name.strip())
    if contact_email is not None:
        sets.append("contact_email = ?")
        params.append(contact_email)
    if timezone is not None:
        sets.append("timezone = ?")
        params.append(timezone)
    if not sets:
        return
    params.append(org_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE organisations SET {', '.join(sets)} WHERE id = ?", params)


def assign_user_to_org(user_id: int, org_id: int, role: str = "member") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET org_id = ?, role = ? WHERE id = ?",
            (org_id, role, user_id),
        )


def get_user_org_id(user_id: int) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT org_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["org_id"] if row else None


# ── Contacts (org-scoped) ──────────────────────────────────────
def create_contact(
    org_id: int,
    phone_number: str,
    name: str | None = None,
    *,
    email: str | None = None,
    consent_state: str = "unknown",
    preferred_channel: str = "sms",
    quiet_hours_start: str | None = None,
    quiet_hours_end: str | None = None,
) -> int:
    """The keyword-only fields are additive (PROJ-417/440/441) — the two
    existing callers (PROJ-406 org registration, PROJ-414 STOP-handler
    auto-created contacts) only ever pass the first three and are
    unaffected."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO contacts (org_id, phone_number, name, email,"
            " consent_state, preferred_channel, quiet_hours_start, quiet_hours_end)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                org_id, phone_number.strip(), name, email,
                consent_state, preferred_channel, quiet_hours_start, quiet_hours_end,
            ),
        )
        return cur.lastrowid


def update_contact_fields(contact_id: int, org_id: int, fields: dict) -> sqlite3.Row | None:
    """Patch-style update — only columns present in `fields` are touched.
    org_id is required so a contact can't be edited across tenants."""
    if not fields:
        return get_contact(contact_id, org_id)
    allowed = {
        "phone_number", "name", "email", "consent_state",
        "preferred_channel", "quiet_hours_start", "quiet_hours_end",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_contact(contact_id, org_id)

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE contacts SET {set_clause} WHERE id = ? AND org_id = ?",
            (*updates.values(), contact_id, org_id),
        )
        return conn.execute(
            "SELECT * FROM contacts WHERE id = ? AND org_id = ?", (contact_id, org_id)
        ).fetchone()


def delete_contact(contact_id: int, org_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM contacts WHERE id = ? AND org_id = ?", (contact_id, org_id)
        )
        return cur.rowcount > 0


def get_contact(contact_id: int, org_id: int) -> sqlite3.Row | None:
    """org_id is required, not optional — that's the isolation guarantee."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE id = ? AND org_id = ?",
            (contact_id, org_id),
        ).fetchone()


def get_contact_by_phone(org_id: int, phone_number: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE org_id = ? AND phone_number = ?",
            (org_id, phone_number.strip()),
        ).fetchone()


def list_contacts(org_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE org_id = ? ORDER BY created_at DESC",
            (org_id,),
        ).fetchall()