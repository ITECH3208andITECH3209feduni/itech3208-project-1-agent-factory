"""
app.web.consent — consent capture and enforcement at send time (PROJ-441).

Reads consent state from the contract's ConsentState (PROJ-412) and keeps an
append-only audit trail of ConsentEvent rows (PROJ-413).

The rule enforced here: a send is allowed only to a contact who has explicitly
opted in. `unknown` and `pending` both block. That is deliberately stricter
than "not opted out" — under Australian spam rules the absence of a refusal is
not consent, and a contact who was never asked has not agreed to anything.

Nothing actually sends yet: the Reminders Engine is PROJ-395. This module is
the gate that engine must call, plus the decision record explaining why a
reminder did or did not go out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from contracts.schemas import ConsentState

from app.web.store import DEFAULT_ORG_ID, table

log = logging.getLogger("agent_factory.consent")

# The only state that permits a send.
SENDABLE = (ConsentState.OPTED_IN.value,)

VALID_SOURCES = ("sms_stop", "web_form", "import", "manual", "api", "system")


def events_table():
    return table("consent_events")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


# ── Audit trail (PROJ-413) ────────────────────────────────────
def record(*, contact_id: int, new_state: str, source: str,
           old_state: str | None = None, detail: str | None = None,
           org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
    """
    Append one consent event. Append-only: there is no update or delete path,
    because an audit trail you can edit is not evidence of anything.
    """
    if source not in VALID_SOURCES:
        # Not fatal — losing the audit entry would be worse than an odd label.
        log.warning("unknown consent source %r, recording anyway", source)

    return events_table().append_only_insert(
        {
            "contact_id": int(contact_id),
            "old_state": old_state,
            "new_state": new_state,
            "source": source,
            "detail": (detail or "")[:500] or None,
            "occurred_at": _now_iso(),
        },
        org_id=org_id,
    )


def history(contact_id: int, org_id: int = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    """Consent events for a contact, most recent first."""
    rows = [r for r in events_table().all(org_id) if int(r["contact_id"]) == int(contact_id)]
    rows.sort(key=lambda r: r.get("occurred_at", ""), reverse=True)
    return rows


# ── Capture ───────────────────────────────────────────────────
def set_state(contact_id: int, new_state: str, *, source: str,
              detail: str | None = None, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """
    Change a contact's consent state and record the event atomically enough
    for this store: the contact row is written first, then the event. If the
    event write failed we would rather have the state change than neither.
    """
    valid = [s.value for s in ConsentState]
    if new_state not in valid:
        raise ValueError(f"unknown consent state {new_state!r}; expected one of {valid}")

    from app.web import contacts

    contact = contacts.get_contact(contact_id, org_id)
    if contact is None:
        return None

    old = contact.get("consent_state")
    if old == new_state:
        # Still worth recording — a repeated STOP is a real signal about how
        # the contact feels, and silently dropping it loses that.
        record(contact_id=contact_id, old_state=old, new_state=new_state,
               source=source, detail=(detail or "no change"), org_id=org_id)
        return contact

    updated = contacts.contacts_table().update(
        contact_id, {"consent_state": new_state}, org_id=org_id
    )
    record(contact_id=contact_id, old_state=old, new_state=new_state,
           source=source, detail=detail, org_id=org_id)
    return updated


def opt_out(contact_id: int, *, source: str = "sms_stop",
            detail: str | None = None, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """Honour a STOP. Always permitted, from any state, no confirmation."""
    return set_state(contact_id, ConsentState.OPTED_OUT.value,
                     source=source, detail=detail or "opt-out received", org_id=org_id)


def opt_in(contact_id: int, *, source: str = "web_form",
           detail: str | None = None, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """
    Record an explicit opt-in.

    Refuses to re-opt-in a contact who has opted out: reversing a STOP needs a
    fresh, separately evidenced action, not a flag flip from whatever code
    happens to be running. Use set_state directly with an explicit source and
    detail if that genuinely happened.
    """
    from app.web import contacts

    contact = contacts.get_contact(contact_id, org_id)
    if contact is None:
        return None
    if contact.get("consent_state") == ConsentState.OPTED_OUT.value:
        raise PermissionError(
            "This contact has opted out. Re-opting them in requires explicit "
            "evidence — record it with set_state() and a source and detail."
        )
    return set_state(contact_id, ConsentState.OPTED_IN.value,
                     source=source, detail=detail, org_id=org_id)


# ── Enforcement at send time (PROJ-441) ───────────────────────
@dataclass
class SendDecision:
    allowed: bool
    reason: str
    code: str               # ok | no_contact | no_consent | quiet_hours | no_address
    contact_id: int | None = None
    consent_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "reason": self.reason, "code": self.code,
            "contact_id": self.contact_id, "consent_state": self.consent_state,
        }


def check_send(contact_id: int | None, *, when: datetime | None = None,
               org_id: int = DEFAULT_ORG_ID) -> SendDecision:
    """
    The gate every send must pass through.

    Order matters: consent is checked before quiet hours, because a quiet-hours
    block is "try later" whereas a consent block is "never". Reporting the
    weaker reason would imply a retry will succeed.
    """
    from app.web import contacts

    if contact_id is None:
        return SendDecision(
            False, "No contact attached, so there is nobody to get consent from.",
            "no_contact",
        )

    contact = contacts.get_contact(int(contact_id), org_id)
    if contact is None:
        return SendDecision(False, f"Contact #{contact_id} does not exist.", "no_contact",
                            contact_id=int(contact_id))

    state = contact.get("consent_state", ConsentState.UNKNOWN.value)
    if state not in SENDABLE:
        explain = {
            ConsentState.UNKNOWN.value: "has never been asked for consent",
            ConsentState.PENDING.value: "was invited but has not replied yet",
            ConsentState.OPTED_OUT.value: "has opted out",
        }.get(state, f"is in state '{state}'")
        return SendDecision(
            False,
            f"Blocked: this contact {explain}. Only an explicit opt-in permits a send.",
            "no_consent", contact_id=int(contact_id), consent_state=state,
        )

    channel = contact.get("preferred_channel", "sms")
    if channel == "email" and not contact.get("email"):
        return SendDecision(False, "Prefers email but has no email address on file.",
                            "no_address", contact_id=int(contact_id), consent_state=state)
    if channel in ("sms", "telegram") and not contact.get("phone_number"):
        return SendDecision(False, f"Prefers {channel} but has no phone number on file.",
                            "no_address", contact_id=int(contact_id), consent_state=state)

    if contacts.in_quiet_hours(contact, when):
        return SendDecision(
            False,
            f"Inside this contact's quiet hours "
            f"({contact.get('quiet_hours_start')}–{contact.get('quiet_hours_end')}). "
            f"Retry after the window.",
            "quiet_hours", contact_id=int(contact_id), consent_state=state,
        )

    return SendDecision(True, "Opted in and outside quiet hours.", "ok",
                        contact_id=int(contact_id), consent_state=state)
