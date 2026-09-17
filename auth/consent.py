# auth/consent.py
# ──────────────────────────────────────────────────────────────
# Consent state model per contact (PROJ-412)
# Audit trail on every change (PROJ-413)
#
# States (from contracts.schemas.ConsentState):
#   unknown   — never asked
#   pending   — invited, no reply yet
#   opted_in  — explicit yes
#   opted_out — replied STOP or equivalent
#
# Transition rules:
#   - opted_out -> opted_in is allowed, but only from an explicit
#     source (web_form / manual). A bulk import or an inbound SMS
#     must never resurrect someone who opted out — that's the
#     realistic way a bug re-subscribes people against their wishes.
#   - Every read and write takes org_id, so consent state cannot
#     be read or changed across tenants.
#   - Every accepted change appends a row to consent_events.
# ──────────────────────────────────────────────────────────────

import sqlite3

from auth.db import get_conn
from contracts.schemas import ConsentState

# Sources that count as explicit, first-party consent.
EXPLICIT_SOURCES = {"web_form", "manual"}

# Sources allowed to move a contact OUT of opted_out.
RESUBSCRIBE_SOURCES = EXPLICIT_SOURCES


class ConsentTransitionError(Exception):
    """Raised when a state change isn't permitted."""


CONSENT_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_contacts_consent
    ON contacts (org_id, consent_state);
"""


def init_consent() -> None:
    """Add consent_state to contacts. Idempotent."""
    with get_conn() as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(contacts)")}
        if "consent_state" not in cols:
            conn.execute(
                "ALTER TABLE contacts ADD COLUMN consent_state TEXT"
                " NOT NULL DEFAULT 'unknown'"
            )
        if "consent_updated_at" not in cols:
            conn.execute("ALTER TABLE contacts ADD COLUMN consent_updated_at TEXT")
        conn.executescript(CONSENT_SCHEMA)


def get_consent_state(contact_id: int, org_id: int) -> ConsentState | None:
    """Return a contact's consent state, or None if not found in this org."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT consent_state FROM contacts WHERE id = ? AND org_id = ?",
            (contact_id, org_id),
        ).fetchone()
    if row is None:
        return None
    return ConsentState(row["consent_state"])


def get_consent_by_phone(org_id: int, phone_number: str) -> tuple[int, ConsentState] | None:
    """
    Look up a contact by phone within an org.
    Returns (contact_id, state) or None. Used by the STOP handler.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, consent_state FROM contacts"
            " WHERE org_id = ? AND phone_number = ?",
            (org_id, phone_number.strip()),
        ).fetchone()
    if row is None:
        return None
    return row["id"], ConsentState(row["consent_state"])


def can_transition(old: ConsentState, new: ConsentState, source: str) -> bool:
    """Whether a state change is permitted from this source."""
    if old == new:
        return True
    # Opting out is always allowed, from any source.
    if new == ConsentState.OPTED_OUT:
        return True
    # Coming back from opted_out needs explicit, first-party consent.
    if old == ConsentState.OPTED_OUT:
        return source in RESUBSCRIBE_SOURCES
    # opted_in must come from an explicit source, not an import.
    if new == ConsentState.OPTED_IN:
        return source in EXPLICIT_SOURCES
    return True


def set_consent_state(
    contact_id: int,
    org_id: int,
    new_state: ConsentState,
    source: str,
    detail: str | None = None,
    actor_user_id: int | None = None,
) -> ConsentState:
    """
    Change a contact's consent state after checking the transition
    is allowed, and append an audit event (PROJ-413).

    Raises ConsentTransitionError if the contact isn't in this org
    or the transition isn't permitted from this source.
    """
    # Imported here rather than at module level: consent_audit reads
    # the ConsentState enum and this module, so a top-level import
    # would be circular.
    from auth import consent_audit

    current = get_consent_state(contact_id, org_id)
    if current is None:
        raise ConsentTransitionError(
            f"contact {contact_id} not found in org {org_id}"
        )

    if not can_transition(current, new_state, source):
        raise ConsentTransitionError(
            f"cannot move contact {contact_id} from {current.value} to "
            f"{new_state.value} via source '{source}'"
        )

    if current == new_state:
        return current

    with get_conn() as conn:
        conn.execute(
            "UPDATE contacts SET consent_state = ?,"
            " consent_updated_at = datetime('now')"
            " WHERE id = ? AND org_id = ?",
            (new_state.value, contact_id, org_id),
        )

    consent_audit.record_event(
        contact_id=contact_id,
        org_id=org_id,
        new_state=new_state,
        source=source,
        old_state=current,
        detail=detail,
        actor_user_id=actor_user_id,
    )
    return new_state


def is_opted_in(contact_id: int, org_id: int) -> bool:
    """The check the send-block in PROJ-415 uses. Fails closed."""
    return get_consent_state(contact_id, org_id) == ConsentState.OPTED_IN


def list_by_state(org_id: int, state: ConsentState) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM contacts WHERE org_id = ? AND consent_state = ?"
            " ORDER BY consent_updated_at DESC",
            (org_id, state.value),
        ).fetchall()