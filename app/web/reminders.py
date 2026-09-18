"""
app.web.reminders — reminders on the published contract (PROJ-438, PROJ-439).

Rewritten onto contracts/schemas.py (PROJ-404). What changed from the earlier
provisional shape, and why it matters if you are reading old code or tickets:

    provisional            contract (now)
    ──────────────────     ─────────────────────────────
    id: UUID string        id: int
    title + notes          message (1..1600)
    due_at                 send_at
    —                      sent_at
    channel per reminder   (none — channel is a per-contact preference)
    status 'cancelled'     status 'blocked'
    contact_id optional    contact_id required

Three consequences worth knowing:

  - Channel moved to the contact (PROJ-440). The contract's contacts are
    phone-centric, so a reminder no longer decides how it is delivered; the
    contact's preferred_channel does.
  - There is no 'cancelled' status. 'blocked' in the contract means consent or
    policy stopped it, which is not the same as a user changing their mind, so
    cancelling is a delete rather than a status change.
  - contact_id is required. Every reminder goes to someone, and PROJ-441 needs
    a contact to check consent against — a reminder with nobody attached could
    never pass the gate anyway.

Nothing sends: the Reminders Engine is PROJ-395. mark_sent/mark_blocked are the
transitions that engine will drive.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.web.store import DEFAULT_ORG_ID, table

log = logging.getLogger("agent_factory.reminders")

STATUSES = ("scheduled", "sent", "blocked", "failed")
# Only 'scheduled' is client-settable. 'sent', 'blocked' and 'failed' are
# outcomes the engine records; accepting them from a client would let the UI
# claim a delivery that never happened.
CLIENT_SETTABLE_STATUSES = ("scheduled",)

MESSAGE_MAX = 1600          # per the contract — one SMS segment budget
SORTS = ("send_at_asc", "send_at_desc", "created_desc", "message_asc")
MAX_LIMIT = 500


class ValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def reminders_table():
    return table("reminders")


def _now() -> datetime:
    return datetime.now().astimezone()


def parse_dt(value: str) -> datetime:
    """
    Parse ISO 8601. A naive value — what <input type="datetime-local"> sends —
    is read in the server's local zone, not silently assumed UTC. Storing naive
    timestamps is how reminders fire hours off.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("send_at is required")
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"not a valid ISO 8601 datetime: {value!r}") from exc
    return dt.replace(tzinfo=_now().tzinfo) if dt.tzinfo is None else dt


# ── Validation ────────────────────────────────────────────────
def validate(payload: dict[str, Any], *, creating: bool,
             existing: dict[str, Any] | None = None,
             org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    # ── message ──────────────────────────────────────────────
    if creating or "message" in payload:
        message = str(payload.get("message") or "").strip()
        if not message:
            errors["message"] = "Enter a message."
        elif len(message) > MESSAGE_MAX:
            errors["message"] = f"Keep the message under {MESSAGE_MAX} characters ({len(message)} given)."
        else:
            clean["message"] = message

    # ── send_at ──────────────────────────────────────────────
    if creating or "send_at" in payload:
        try:
            when = parse_dt(str(payload.get("send_at") or ""))
        except ValueError as exc:
            errors["send_at"] = str(exc) if "required" in str(exc) else "Enter a valid date and time."
        else:
            target = str(payload.get("status") or (existing or {}).get("status") or "scheduled")
            if target == "scheduled" and when <= _now():
                errors["send_at"] = "Pick a time in the future — a past reminder will never send."
            else:
                clean["send_at"] = when.isoformat()

    # ── contact_id (required by the contract) ────────────────
    if creating or "contact_id" in payload:
        raw = payload.get("contact_id")
        if raw in (None, ""):
            errors["contact_id"] = "Choose a contact."
        else:
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                errors["contact_id"] = "Contact must be a numeric id."
            else:
                from app.web import contacts

                if contacts.get_contact(cid, org_id) is None:
                    # Now checkable, unlike the provisional version — the
                    # contacts store exists.
                    errors["contact_id"] = f"Contact #{cid} does not exist."
                else:
                    clean["contact_id"] = cid

    # ── status ───────────────────────────────────────────────
    if "status" in payload:
        status = str(payload.get("status") or "").strip().lower()
        if status not in STATUSES:
            errors["status"] = f"Unknown status. Expected one of: {', '.join(STATUSES)}."
        elif status not in CLIENT_SETTABLE_STATUSES:
            errors["status"] = (
                f"'{status}' is recorded by the Reminders Engine (PROJ-395), not the client. "
                f"To stop a scheduled reminder, delete it."
            )
        else:
            clean["status"] = status

    allowed = {"message", "send_at", "contact_id", "status"}
    unknown = set(payload) - allowed
    if unknown:
        errors["_"] = f"Unexpected field(s): {', '.join(sorted(unknown))}."

    if errors:
        raise ValidationError(errors)
    return clean


# ── CRUD ──────────────────────────────────────────────────────
def list_reminders(org_id: int = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    rows = reminders_table().all(org_id)
    rows.sort(key=lambda r: r.get("send_at", ""))
    return rows


def get_reminder(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    return reminders_table().get(reminder_id, org_id)


def create_reminder(payload: dict[str, Any], org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
    clean = validate(payload, creating=True, org_id=org_id)
    return reminders_table().insert(
        {
            "contact_id": clean["contact_id"],
            "message": clean["message"],
            "send_at": clean["send_at"],
            "sent_at": None,
            "status": clean.get("status", "scheduled"),
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
        },
        org_id=org_id,
    )


def update_reminder(reminder_id: int, payload: dict[str, Any],
                    org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    existing = get_reminder(reminder_id, org_id)
    if existing is None:
        return None
    clean = validate(payload, creating=False, existing=existing, org_id=org_id)
    clean["updated_at"] = _now().isoformat()
    return reminders_table().update(reminder_id, clean, org_id=org_id)


def delete_reminder(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> bool:
    return reminders_table().delete(reminder_id, org_id)


# ── Engine transitions (PROJ-395 will drive these) ────────────
def mark_sent(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    return reminders_table().update(
        reminder_id,
        {"status": "sent", "sent_at": _now().isoformat(), "updated_at": _now().isoformat()},
        org_id=org_id,
    )


def mark_blocked(reminder_id: int, reason: str, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """Consent or policy stopped this. The reason is kept — a bare 'blocked'
    tells whoever looks later nothing about why."""
    return reminders_table().update(
        reminder_id,
        {"status": "blocked", "blocked_reason": reason[:500], "updated_at": _now().isoformat()},
        org_id=org_id,
    )


def dispatch_check(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
    """
    Would this reminder be allowed to send right now? (PROJ-441)

    The engine calls this before sending. Exposed to the UI too, so someone can
    see that a scheduled reminder will be blocked *before* its send time
    arrives rather than discovering it afterwards.
    """
    from app.web import consent

    reminder = get_reminder(reminder_id, org_id)
    if reminder is None:
        return {"allowed": False, "code": "no_reminder", "reason": "Reminder does not exist."}

    decision = consent.check_send(reminder.get("contact_id"), org_id=org_id)
    out = decision.to_dict()
    out["reminder_id"] = int(reminder_id)
    return out


# ── Query (PROJ-438) ──────────────────────────────────────────
def query(items: list[dict[str, Any]], *, q: str | None = None, status: str | None = None,
          contact_id: int | None = None, sort: str = "send_at_asc",
          limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """
    Filter, search, sort and page. Above the store on purpose, so the storage
    layer stays replaceable. Pure over its input — does not mutate `items`.
    """
    errors: dict[str, str] = {}
    rows = list(items)

    if q:
        needle = q.strip().lower()
        if needle:
            rows = [r for r in rows if needle in (r.get("message") or "").lower()]

    if status:
        wanted = {s.strip().lower() for s in status.split(",") if s.strip()}
        unknown = wanted - set(STATUSES)
        if unknown:
            errors["status"] = (f"Unknown status: {', '.join(sorted(unknown))}. "
                                f"Expected one of: {', '.join(STATUSES)}.")
        else:
            rows = [r for r in rows if r.get("status") in wanted]

    if contact_id is not None:
        rows = [r for r in rows if int(r.get("contact_id", 0)) == int(contact_id)]

    if sort not in SORTS:
        errors["sort"] = f"Unknown sort. Expected one of: {', '.join(SORTS)}."
    if limit is not None and (limit < 1 or limit > MAX_LIMIT):
        errors["limit"] = f"limit must be between 1 and {MAX_LIMIT}."
    if offset < 0:
        errors["offset"] = "offset cannot be negative."

    if errors:
        raise ValidationError(errors)

    if sort == "send_at_asc":
        rows.sort(key=lambda r: r.get("send_at", ""))
    elif sort == "send_at_desc":
        rows.sort(key=lambda r: r.get("send_at", ""), reverse=True)
    elif sort == "created_desc":
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    elif sort == "message_asc":
        rows.sort(key=lambda r: (r.get("message") or "").lower())

    total = len(rows)
    if offset:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]
    return rows, total


# ── Dashboard helpers ─────────────────────────────────────────
def next_upcoming(count: int = 5, org_id: int = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    now = _now()
    rows = [
        r for r in list_reminders(org_id)
        if r.get("status") == "scheduled" and parse_dt(r["send_at"]) > now
    ]
    rows.sort(key=lambda r: r["send_at"])
    return rows[:count]


def recent_history(count: int = 5, org_id: int = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    """Reminders something actually happened to — sent, blocked, or failed."""
    rows = [r for r in list_reminders(org_id) if r.get("status") in ("sent", "blocked", "failed")]
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return rows[:count]


def upcoming_count(org_id: int = DEFAULT_ORG_ID) -> int:
    return len(next_upcoming(10_000, org_id))


def sent_count(org_id: int = DEFAULT_ORG_ID) -> int:
    return sum(1 for r in list_reminders(org_id) if r.get("status") == "sent")


def blocked_count(org_id: int = DEFAULT_ORG_ID) -> int:
    return sum(1 for r in list_reminders(org_id) if r.get("status") == "blocked")
