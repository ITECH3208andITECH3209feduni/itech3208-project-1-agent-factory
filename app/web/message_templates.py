"""
app.web.message_templates — reusable reminder messages with merge fields
(PROJ-480, with the minimum of PROJ-484/485 it depends on).

A template is a named message body with placeholders such as
"Hi {first_name}, see you {date} at {time}. — {org}". The reminder form can
start a message from one and preview it against the chosen contact; the
web reminder bridge renders the placeholders again at send time, so a
recurring reminder says the right date on every occurrence.

Storage is the same org-scoped JSON table layer as contacts and reminders
(app/web/store.py), so it is replaced along with them when real persistence
lands.

Rendering rules, kept deliberately small:
  - Only the names in MERGE_FIELDS are placeholders. Anything else in braces
    is left exactly as written, so a message that happens to contain "{x}"
    is not mangled at send time.
  - Saving a template with an unknown placeholder is a validation error —
    it is almost always a typo ("{frist_name}") that would otherwise go out
    to a customer verbatim.
  - A field with no value (a contact with no name) renders as a neutral
    fallback rather than an empty gap, e.g. "Hi there,".
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.web.store import DEFAULT_ORG_ID, table

NAME_MAX = 80
BODY_MAX = 1600     # same budget as a reminder message
SUBJECT_MAX = 200
VALID_CHANNELS = {"sms", "email", "voice"}

# name -> (description shown in the UI, fallback when the value is missing)
MERGE_FIELDS: dict[str, tuple[str, str]] = {
    "name": ("Contact's full name", "there"),
    "first_name": ("Contact's first name", "there"),
    "date": ("Send date, e.g. Monday 3 November", ""),
    "time": ("Send time, e.g. 9:30am", ""),
    "org": ("Your organisation's name", "us"),
    "org_name": ("Your organisation's name", "us"),
    "appointment_date": ("Appointment date", ""),
}

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def templates_table():
    return table("message_templates")


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def placeholders(body: str) -> list[str]:
    return _PLACEHOLDER.findall(body or "")


def unknown_placeholders(body: str) -> list[str]:
    return sorted({p for p in placeholders(body) if p not in MERGE_FIELDS})


# ── Rendering (the PROJ-485 part) ─────────────────────────────
def _fmt_date(dt: datetime) -> str:
    return f"{dt.strftime('%A')} {dt.day} {dt.strftime('%B')}"


def _fmt_time(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    suffix = "am" if dt.hour < 12 else "pm"
    return f"{hour}{suffix}" if dt.minute == 0 else f"{hour}:{dt.minute:02d}{suffix}"


def merge_values(contact: dict[str, Any] | None, send_at: datetime | None,
                 org_name: str | None, tz_name: str | None = None,
                 appointment_date: datetime | None = None) -> dict[str, str]:
    """The value of every merge field for one send. `send_at` is shown in
    tz_name when given (the zone the reminder was scheduled in), otherwise
    in the offset it carries."""
    name = ((contact or {}).get("name") or "").strip()
    values = {
        "name": name,
        "first_name": name.split()[0] if name else "",
        "org": (org_name or "").strip(),
        "org_name": (org_name or "").strip(),
        "date": "",
        "appointment_date": "",
        "time": "",
    }
    if send_at is not None:
        local = send_at
        if tz_name:
            zone = ZoneInfo(tz_name)
            if local.tzinfo is None:
                local = local.replace(tzinfo=zone)
            else:
                local = local.astimezone(zone)
        values["date"] = _fmt_date(local)
        values["time"] = _fmt_time(local)

    if appointment_date is not None:
        local_appointment = appointment_date
        if tz_name:
            if local_appointment.tzinfo is None:
                local_appointment = local_appointment.replace(
                    tzinfo=ZoneInfo(tz_name)
                )
            else:
                local_appointment = local_appointment.astimezone(
                    ZoneInfo(tz_name)
                )
        values["appointment_date"] = _fmt_date(local_appointment)

    return {k: (v or MERGE_FIELDS[k][1]) for k, v in values.items()}


def render(body: str, values: dict[str, str]) -> str:
    """Render merge fields safely; double braces escape placeholders."""
    open_token = "\\x00AF_OPEN_BRACE\\x00"
    close_token = "\\x00AF_CLOSE_BRACE\\x00"
    text = (body or "").replace("{{", open_token).replace("}}", close_token)

    def replace_field(match):
        field = match.group(1)
        if field not in MERGE_FIELDS:
            return match.group(0)
        fallback = MERGE_FIELDS[field][1]
        return values.get(field) or fallback

    text = _PLACEHOLDER.sub(replace_field, text)
    return text.replace(close_token, "}").replace(open_token, "{")


def org_name(org_id: int = DEFAULT_ORG_ID) -> str | None:
    try:
        from auth import tenancy

        row = tenancy.get_org(org_id)
    except Exception:  # noqa: BLE001 — a missing org table must not stop a send
        return None
    return row["name"] if row else None


def render_for(body: str, contact: dict[str, Any] | None, send_at: datetime | None,
               org_id: int = DEFAULT_ORG_ID, tz_name: str | None = None,
               appointment_date: datetime | None = None) -> str:
    return render(
        body,
        merge_values(
            contact, send_at, org_name(org_id), tz_name, appointment_date
        ),
    )


# ── Store and CRUD (the PROJ-484 part) ────────────────────────
def validate(payload: dict[str, Any], *, creating: bool, current_id: int | None = None,
             org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    if creating or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            errors["name"] = "Give the template a name."
        elif len(name) > NAME_MAX:
            errors["name"] = f"Keep the name under {NAME_MAX} characters."
        elif any(t["name"].lower() == name.lower() and t["id"] != current_id
                 for t in list_templates(org_id)):
            errors["name"] = "A template with this name already exists."
        else:
            clean["name"] = name

    if creating or "body" in payload:
        body = str(payload.get("body") or "").strip()
        unknown = unknown_placeholders(body)
        if not body:
            errors["body"] = "Enter the message text."
        elif len(body) > BODY_MAX:
            errors["body"] = f"Keep the message under {BODY_MAX} characters ({len(body)} given)."
        elif unknown:
            known = ", ".join("{" + k + "}" for k in MERGE_FIELDS)
            errors["body"] = (f"Unknown merge field {', '.join('{' + u + '}' for u in unknown)}. "
                              f"Available: {known}.")
        else:
            clean["body"] = body

    if creating or "channel" in payload:
        channel = str(payload.get("channel") or ("sms" if creating else "")).strip().lower()
        if channel not in VALID_CHANNELS:
            errors["channel"] = f"Choose one of: {', '.join(sorted(VALID_CHANNELS))}."
        else:
            clean["channel"] = channel

    if creating or "subject" in payload:
        default_subject = "Reminder" if creating else ""
        subject = str(payload.get("subject") or default_subject).strip()
        if len(subject) > SUBJECT_MAX:
            errors["subject"] = f"Keep the subject under {SUBJECT_MAX} characters."
        else:
            clean["subject"] = subject

    unexpected = set(payload) - {"name", "body", "channel", "subject"}
    if unexpected:
        errors["_"] = f"Unexpected field(s): {', '.join(sorted(unexpected))}."

    if errors:
        raise ValidationError(errors)
    return clean


def list_templates(org_id: int = DEFAULT_ORG_ID) -> list[dict[str, Any]]:
    rows = templates_table().all(org_id)
    rows.sort(key=lambda r: r.get("name", "").lower())
    return rows


def get_template(template_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    return templates_table().get(template_id, org_id)


def create_template(payload: dict[str, Any], org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
    clean = validate(payload, creating=True, org_id=org_id)
    now = _now()
    return templates_table().insert({**clean, "created_at": now, "updated_at": now}, org_id=org_id)


def update_template(template_id: int, payload: dict[str, Any],
                    org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    if get_template(template_id, org_id) is None:
        return None
    clean = validate(payload, creating=False, current_id=int(template_id), org_id=org_id)
    clean["updated_at"] = _now()
    return templates_table().update(template_id, clean, org_id=org_id)


def delete_template(template_id: int, org_id: int = DEFAULT_ORG_ID) -> bool:
    # Reminders keep their own copy of the text, so deleting a template never
    # changes a reminder that was started from it.
    return templates_table().delete(template_id, org_id)
