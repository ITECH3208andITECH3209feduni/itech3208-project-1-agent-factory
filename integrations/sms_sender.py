# integrations/sms_sender.py
# ──────────────────────────────────────────────────────────────
# Hard send-block for non-opted-in contacts (PROJ-415)
#
# This is the ONLY path for sending an SMS. The consent check is
# inside it, not beside it — there is no parameter to skip the
# check and no lower-level send function exposed, because a check
# a caller can forget isn't a hard block.
#
# Every attempt is recorded in sms_send_log, blocked or not, so
# there is evidence that a message to an opted-out contact was
# refused rather than merely absent.
#
# Fails closed: an unknown contact, an unresolvable org, or any
# state other than opted_in results in no send.
# ──────────────────────────────────────────────────────────────

import logging
import os
import sqlite3

from dotenv import load_dotenv

from auth.consent import get_consent_state
from auth.db import get_conn
from auth.tenancy import get_contact
from contracts.schemas import ConsentState

load_dotenv()

log = logging.getLogger("sms_sender")

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

SEND_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS sms_send_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id      INTEGER NOT NULL,
    contact_id  INTEGER NOT NULL,
    phone_number TEXT,
    body_preview TEXT,
    outcome     TEXT    NOT NULL,
    reason      TEXT,
    consent_state TEXT,
    provider_sid TEXT,
    attempted_at TEXT   NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_send_log_contact
    ON sms_send_log (org_id, contact_id, id);
"""


class SendBlocked(Exception):
    """Raised when consent does not permit sending."""


def init_send_log() -> None:
    with get_conn() as conn:
        conn.executescript(SEND_LOG_SCHEMA)


def credentials_configured() -> bool:
    """
    Whether we have usable Twilio credentials.

    A real account SID always starts with "AC", so anything else is
    a placeholder left in .env rather than a credential. Checking
    only that the values are non-empty would send placeholder text
    to Twilio and fail with an auth error mid-send.
    """
    return bool(
        ACCOUNT_SID.startswith("AC")
        and AUTH_TOKEN
        and not AUTH_TOKEN.startswith("your_")
        and FROM_NUMBER
        and not FROM_NUMBER.startswith("your_")
    )


def _log_attempt(
    org_id: int,
    contact_id: int,
    phone: str | None,
    body: str,
    outcome: str,
    reason: str | None = None,
    consent_state: str | None = None,
    provider_sid: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sms_send_log"
            " (org_id, contact_id, phone_number, body_preview, outcome,"
            "  reason, consent_state, provider_sid)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, contact_id, phone, (body or "")[:120],
             outcome, reason, consent_state, provider_sid),
        )


def _deliver(to_number: str, body: str) -> str | None:
    """
    Hand the message to Twilio. Returns the message SID, or None
    when no credentials are configured (logged instead of sent).
    """
    if not credentials_configured():
        log.warning(
            "No Twilio credentials — would send to %s: %r", to_number, body[:80]
        )
        return None

    from twilio.rest import Client

    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    msg = client.messages.create(to=to_number, from_=FROM_NUMBER, body=body)
    return msg.sid


def send_to_contact(contact_id: int, org_id: int, body: str) -> str | None:
    """
    Send an SMS to a contact, if and only if they are opted in.

    Returns the provider message SID on success, or None when the
    message was accepted but no provider is configured.

    Raises SendBlocked when consent does not permit sending. There
    is deliberately no override argument.
    """
    contact = get_contact(contact_id, org_id)
    if contact is None:
        _log_attempt(org_id, contact_id, None, body, "blocked", "contact not in org")
        raise SendBlocked(f"contact {contact_id} not found in org {org_id}")

    phone = contact["phone_number"]
    state = get_consent_state(contact_id, org_id)

    if state != ConsentState.OPTED_IN:
        _log_attempt(
            org_id, contact_id, phone, body, "blocked",
            reason="not opted in",
            consent_state=state.value if state else "unknown",
        )
        log.warning(
            "send blocked: contact %s (org %s) is %s",
            contact_id, org_id, state.value if state else "unknown",
        )
        raise SendBlocked(
            f"contact {contact_id} is {state.value if state else 'unknown'},"
            " not opted_in"
        )

    try:
        sid = _deliver(phone, body)
    except Exception as exc:
        _log_attempt(
            org_id, contact_id, phone, body, "failed",
            reason=str(exc)[:200], consent_state=state.value,
        )
        log.exception("SMS delivery failed for contact %s", contact_id)
        raise

    _log_attempt(
        org_id, contact_id, phone, body,
        "sent" if sid else "no_provider",
        consent_state=state.value, provider_sid=sid,
    )
    return sid


def send_bulk(org_id: int, contact_ids: list[int], body: str) -> dict:
    """
    Send to many contacts, skipping those who aren't opted in.

    Returns counts and the blocked contact ids. Each send still goes
    through send_to_contact, so the consent check applies per
    contact — a bulk path can't bypass it.
    """
    sent, blocked, failed = [], [], []
    for cid in contact_ids:
        try:
            send_to_contact(cid, org_id, body)
            sent.append(cid)
        except SendBlocked:
            blocked.append(cid)
        except Exception:
            failed.append(cid)

    return {
        "sent": len(sent),
        "blocked": len(blocked),
        "failed": len(failed),
        "blocked_ids": blocked,
    }


def send_history(contact_id: int, org_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM sms_send_log"
            " WHERE org_id = ? AND contact_id = ? ORDER BY id DESC",
            (org_id, contact_id),
        ).fetchall()