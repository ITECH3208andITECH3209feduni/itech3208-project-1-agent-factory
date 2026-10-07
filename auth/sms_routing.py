# auth/sms_routing.py
# ──────────────────────────────────────────────────────────────
# Map an inbound Twilio number to an organisation (PROJ-414)
#
# An inbound SMS carries From (the contact) and To (our Twilio
# number). Consent lookups need an org_id, so the To number is
# what identifies the tenant. Resolving by the sender's number
# instead would mean searching every org for that contact, which
# is the cross-tenant read that PROJ-410 exists to prevent.
#
# No ticket in this batch defined this mapping — it's added here
# because the STOP handler cannot be written without it.
# ──────────────────────────────────────────────────────────────

import os
import sqlite3

from dotenv import load_dotenv

from auth.db import get_conn

load_dotenv()

# Single-tenant fallback: when only one org uses the project's own
# Twilio number, unmatched inbound messages belong to it.
DEFAULT_TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")


def init_sms_routing() -> None:
    """Add organisations.twilio_number. Idempotent."""
    with get_conn() as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(organisations)")}
        if "twilio_number" not in cols:
            conn.execute("ALTER TABLE organisations ADD COLUMN twilio_number TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orgs_twilio"
            " ON organisations (twilio_number)"
        )


def set_org_twilio_number(org_id: int, number: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE organisations SET twilio_number = ? WHERE id = ?",
            (number.strip(), org_id),
        )


def resolve_org_by_twilio_number(to_number: str) -> int | None:
    """
    Which org owns this inbound number? Returns org_id or None.

    Returns None rather than guessing when nothing matches — a
    wrong org here would write consent state into the wrong
    tenant's data.
    """
    if not to_number:
        return None

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM organisations WHERE twilio_number = ? AND is_active = 1",
            (to_number.strip(),),
        ).fetchone()
        if row:
            return row["id"]

        # Fallback: if the number is the project's shared Twilio
        # number and exactly one active org exists, it's that one.
        if DEFAULT_TWILIO_NUMBER and to_number.strip() == DEFAULT_TWILIO_NUMBER.strip():
            rows = conn.execute(
                "SELECT id FROM organisations WHERE is_active = 1 LIMIT 2"
            ).fetchall()
            if len(rows) == 1:
                return rows[0]["id"]

    return None