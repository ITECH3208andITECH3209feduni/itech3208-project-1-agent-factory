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

PROJ-479 (client brief A4) brings the dashboard up to what the engine in
agent/reminders/store.py already supports:

  - `recurrence`: {"freq": "none"|"daily"|"weekly"|"custom", "interval_days": n}.
    When the bridge sends a recurring reminder it calls
    schedule_next_occurrence(), which adds a new 'scheduled' row for the next
    one — the same series model the engine store uses.
  - 'paused' and 'cancelled' statuses, set only through pause()/resume()/
    cancel(), never through PATCH. 'cancelled' is a person changing their
    mind and is kept so the history shows it; 'blocked' still means consent
    or policy stopped it. Delete still exists for removing a row outright.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.web.store import DEFAULT_ORG_ID, table

log = logging.getLogger("agent_factory.reminders")

STATUSES = ("scheduled", "paused", "sent", "blocked", "failed", "cancelled")
# Only 'scheduled' is client-settable through PATCH. 'sent', 'blocked' and
# 'failed' are outcomes the engine records; accepting them from a client would
# let the UI claim a delivery that never happened. 'paused' and 'cancelled'
# have their own endpoints so each transition can check where it starts from.
CLIENT_SETTABLE_STATUSES = ("scheduled",)
# Statuses a person can still change. Once the engine has acted, or the
# reminder was cancelled, it is history.
EDITABLE_STATUSES = ("scheduled", "paused")

FREQUENCIES = ("none", "daily", "weekly", "custom")
INTERVAL_DAYS_MAX = 365

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


def _clean_recurrence(raw: Any) -> dict[str, Any] | None:
    """Normalise a recurrence payload. Returns None for a one-off reminder;
    raises ValueError with a user-facing message otherwise."""
    if raw in (None, "", "none"):
        return None
    if not isinstance(raw, dict):
        raise ValueError("Recurrence must be an object with a 'freq'.")
    freq = str(raw.get("freq") or "none").strip().lower()
    if freq not in FREQUENCIES:
        raise ValueError(f"Unknown repeat. Expected one of: {', '.join(FREQUENCIES)}.")
    if freq == "none":
        return None
    clean: dict[str, Any] = {"freq": freq}
    if freq == "custom":
        try:
            days = int(raw.get("interval_days"))
        except (TypeError, ValueError):
            raise ValueError("Enter how many days between reminders.") from None
        if not 1 <= days <= INTERVAL_DAYS_MAX:
            raise ValueError(f"Repeat every 1 to {INTERVAL_DAYS_MAX} days.")
        clean["interval_days"] = days
    tz = raw.get("tz")
    if tz:
        try:
            ZoneInfo(str(tz))
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"Unknown timezone: {tz!r}.") from None
        clean["tz"] = str(tz)
    return clean


def next_occurrence(send_at: str, recurrence: dict[str, Any]) -> str:
    """
    The next fire time after send_at. The interval is added to local wall-clock
    time, not to the instant, so "every day at 9am" stays 9am across a daylight
    saving change — the same rule as agent/reminders/store.py. The wall clock
    is the one in recurrence["tz"] (the browser's zone, sent by the form), or
    the server's zone if none was given.
    """
    freq = recurrence.get("freq")
    if freq == "daily":
        step = timedelta(days=1)
    elif freq == "weekly":
        step = timedelta(weeks=1)
    elif freq == "custom":
        step = timedelta(days=int(recurrence.get("interval_days", 1)))
    else:
        raise ValueError(f"not a recurring frequency: {freq!r}")
    tz_name = recurrence.get("tz")
    if tz_name:
        zone = ZoneInfo(tz_name)
        local_wall = parse_dt(send_at).astimezone(zone).replace(tzinfo=None)
        return (local_wall + step).replace(tzinfo=zone).isoformat()
    local_wall = parse_dt(send_at).astimezone().replace(tzinfo=None)
    # A naive datetime's astimezone() reads it in the local zone, picking the
    # offset that applies on that date.
    return (local_wall + step).astimezone().isoformat()


def _next_future_occurrence(send_at: str, recurrence: dict[str, Any]) -> str:
    """Step forward until the time is in the future. Used when a series was
    paused, or the bridge was down, through one or more due times — those are
    skipped rather than all sent at once."""
    now = _now()
    nxt = next_occurrence(send_at, recurrence)
    while parse_dt(nxt) <= now:
        nxt = next_occurrence(nxt, recurrence)
    return nxt


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
            if target in EDITABLE_STATUSES and when <= _now():
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

    # ── recurrence (PROJ-479) ────────────────────────────────
    if "recurrence" in payload:
        try:
            clean["recurrence"] = _clean_recurrence(payload.get("recurrence"))
        except ValueError as exc:
            errors["recurrence"] = str(exc)

    allowed = {"message", "send_at", "contact_id", "status", "recurrence"}
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
            "recurrence": clean.get("recurrence"),
            "created_at": _now().isoformat(),
            "updated_at": _now().isoformat(),
        },
        org_id=org_id,
    )


class TransitionError(ValueError):
    """The reminder exists but is in a status the action cannot start from.
    Routes turn this into a 409."""


def _require_editable(existing: dict[str, Any], action: str) -> None:
    status = existing.get("status")
    if status not in EDITABLE_STATUSES:
        raise TransitionError(
            f"Cannot {action} a reminder that is {status}. "
            f"Only scheduled or paused reminders can change."
        )


def update_reminder(reminder_id: int, payload: dict[str, Any],
                    org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    existing = get_reminder(reminder_id, org_id)
    if existing is None:
        return None
    _require_editable(existing, "edit")
    clean = validate(payload, creating=False, existing=existing, org_id=org_id)
    clean["updated_at"] = _now().isoformat()
    return reminders_table().update(reminder_id, clean, org_id=org_id)


def delete_reminder(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> bool:
    return reminders_table().delete(reminder_id, org_id)


# ── Pause / resume / cancel / reschedule (PROJ-479) ───────────
def _set_status(reminder_id: int, status: str, org_id: int,
                **extra: Any) -> dict[str, Any] | None:
    return reminders_table().update(
        reminder_id, {"status": status, "updated_at": _now().isoformat(), **extra}, org_id=org_id,
    )


def pause_reminder(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """scheduled -> paused. The bridge only sends 'scheduled', so a paused
    reminder simply stops being picked up."""
    existing = get_reminder(reminder_id, org_id)
    if existing is None:
        return None
    if existing.get("status") != "scheduled":
        raise TransitionError(f"Only a scheduled reminder can be paused (this one is {existing.get('status')}).")
    return _set_status(reminder_id, "paused", org_id)


def resume_reminder(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """
    paused -> scheduled. If the send time passed while it was paused, a
    recurring reminder moves on to its next future occurrence; a one-off cannot
    guess a new time, so it has to be rescheduled — resuming it as-is would
    fire it the moment the bridge next ticks.
    """
    existing = get_reminder(reminder_id, org_id)
    if existing is None:
        return None
    if existing.get("status") != "paused":
        raise TransitionError(f"Only a paused reminder can be resumed (this one is {existing.get('status')}).")
    extra: dict[str, Any] = {}
    if parse_dt(existing["send_at"]) <= _now():
        if not existing.get("recurrence"):
            raise ValidationError({"send_at": "Its send time passed while paused. Reschedule it to resume."})
        extra["send_at"] = _next_future_occurrence(existing["send_at"], existing["recurrence"])
    return _set_status(reminder_id, "scheduled", org_id, **extra)


def cancel_reminder(reminder_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """scheduled|paused -> cancelled. Kept rather than deleted so the history
    shows that someone stopped it, and when."""
    existing = get_reminder(reminder_id, org_id)
    if existing is None:
        return None
    _require_editable(existing, "cancel")
    return _set_status(reminder_id, "cancelled", org_id)


def reschedule_reminder(reminder_id: int, send_at: Any,
                        org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """Move the send time. Works on paused reminders too, and keeps the status
    — rescheduling a paused reminder does not quietly resume it."""
    existing = get_reminder(reminder_id, org_id)
    if existing is None:
        return None
    _require_editable(existing, "reschedule")
    clean = validate({"send_at": send_at}, creating=False, existing=existing, org_id=org_id)
    return reminders_table().update(
        reminder_id, {"send_at": clean["send_at"], "updated_at": _now().isoformat()}, org_id=org_id,
    )


def schedule_next_occurrence(reminder: dict[str, Any],
                             org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """
    After a recurring reminder is handled, add the next one in the series as a
    new row, so each send keeps its own sent/blocked/failed record. Returns
    None for a one-off. Mirrors ReminderStore.schedule_next_occurrence.
    """
    recurrence = reminder.get("recurrence")
    if not recurrence or recurrence.get("freq") in (None, "none"):
        return None
    now = _now().isoformat()
    return reminders_table().insert(
        {
            "contact_id": reminder["contact_id"],
            "message": reminder["message"],
            "send_at": _next_future_occurrence(reminder["send_at"], recurrence),
            "sent_at": None,
            "status": "scheduled",
            "recurrence": recurrence,
            "series_of": reminder.get("series_of") or reminder["id"],
            "created_at": now,
            "updated_at": now,
        },
        org_id=org_id,
    )


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


def mark_failed(reminder_id: int, reason: str, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    """The send was attempted and allowed (consent/quiet-hours passed) but
    the delivery itself failed — a Twilio/SMTP error, not a policy block.
    Distinct from mark_blocked: 'blocked' means it was never attempted."""
    return reminders_table().update(
        reminder_id,
        {"status": "failed", "failed_reason": reason[:500], "updated_at": _now().isoformat()},
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


# ── CSV export (PROJ-492) ──────────────────────────────────────
EXPORT_COLUMNS = ("id", "contact_name", "contact_phone", "message", "status",
                   "send_at", "sent_at", "blocked_reason", "failed_reason",
                   "created_at", "updated_at")


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_PHONE_LIKE = re.compile(r"\+?[\d\s().-]+")


def csv_safe(value: Any) -> str:
    """Make a cell safe to open in a spreadsheet (PROJ-492).

    Excel and Sheets run a cell that starts with = + - or @ as a formula, so a
    reminder message like =HYPERLINK(...) in an export could execute when
    someone opens it. Prefix such text with an apostrophe. Phone numbers also
    start with + and must stay intact, so a plain phone-shaped value is left alone.
    """
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_START) and not _PHONE_LIKE.fullmatch(text):
        return "'" + text
    return text


def history_csv(org_id: int = DEFAULT_ORG_ID) -> str:
    """Every reminder something has happened to (sent, blocked, or failed), as
    CSV — newest update first. Mirrors recent_history's status filter but with
    no count cap, since an export should be the full record, not a preview."""
    from app.web import contacts

    rows = [r for r in list_reminders(org_id) if r.get("status") in ("sent", "blocked", "failed")]
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        contact = contacts.get_contact(r["contact_id"], org_id=org_id) if r.get("contact_id") else None
        writer.writerow({
            "id": r.get("id"),
            "contact_name": csv_safe((contact or {}).get("name")),
            "contact_phone": csv_safe((contact or {}).get("phone_number")),
            "message": csv_safe(r.get("message", "")),
            "status": r.get("status", ""),
            "send_at": r.get("send_at", ""),
            "sent_at": r.get("sent_at") or "",
            "blocked_reason": csv_safe(r.get("blocked_reason", "")),
            "failed_reason": csv_safe(r.get("failed_reason", "")),
            "created_at": r.get("created_at", ""),
            "updated_at": r.get("updated_at", ""),
        })
    return buf.getvalue()
