# auth/consent_audit.py
# ──────────────────────────────────────────────────────────────
# Opt-in capture and audit trail (PROJ-413)
#
# Every consent change is written to consent_events as a new row.
# The table is append-only by design: no update or delete helpers
# exist here, because an audit trail you can edit is not evidence.
# If a regulator or a complaint asks "when did this person agree
# and how", the answer has to be a record nobody could revise.
#
# Rows capture the old and new state, the source, and optional
# detail (the SMS body that triggered a STOP, the form URL, the
# user who made a manual change).
# ──────────────────────────────────────────────────────────────

import sqlite3

from auth.db import get_conn
from contracts.schemas import ConsentState

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS consent_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER NOT NULL,
    org_id      INTEGER NOT NULL,
    old_state   TEXT,
    new_state   TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    detail      TEXT,
    actor_user_id INTEGER,
    occurred_at TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (org_id)     REFERENCES organisations(id)
);

CREATE INDEX IF NOT EXISTS idx_consent_events_contact
    ON consent_events (org_id, contact_id, id);
"""


def init_consent_audit() -> None:
    with get_conn() as conn:
        conn.executescript(AUDIT_SCHEMA)


def record_event(
    contact_id: int,
    org_id: int,
    new_state: ConsentState,
    source: str,
    old_state: ConsentState | None = None,
    detail: str | None = None,
    actor_user_id: int | None = None,
) -> int:
    """Append one consent event. Returns the event id."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO consent_events"
            " (contact_id, org_id, old_state, new_state, source, detail, actor_user_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                contact_id,
                org_id,
                old_state.value if old_state else None,
                new_state.value,
                source,
                detail[:500] if detail else None,
                actor_user_id,
            ),
        )
        return cur.lastrowid


def get_history(contact_id: int, org_id: int) -> list[sqlite3.Row]:
    """Full consent history for one contact, oldest first."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM consent_events"
            " WHERE org_id = ? AND contact_id = ?"
            " ORDER BY id ASC",
            (org_id, contact_id),
        ).fetchall()


def get_opt_in_proof(contact_id: int, org_id: int) -> sqlite3.Row | None:
    """
    The most recent opt_in event for this contact — the record you
    produce when asked to show consent was given.
    """
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM consent_events"
            " WHERE org_id = ? AND contact_id = ? AND new_state = 'opted_in'"
            " ORDER BY id DESC LIMIT 1",
            (org_id, contact_id),
        ).fetchone()


def recent_events(org_id: int, limit: int = 50) -> list[sqlite3.Row]:
    """Recent consent activity across an org, newest first."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM consent_events WHERE org_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (org_id, limit),
        ).fetchall()