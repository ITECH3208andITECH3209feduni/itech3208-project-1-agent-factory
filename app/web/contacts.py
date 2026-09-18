"""
app.web.contacts — contacts CRM (PROJ-417, 418, 420) with notification
preferences (PROJ-440) and consent (PROJ-441).

Built on the published contract in contracts/schemas.py (PROJ-404):
ContactCreate / ContactOut / ConsentState / ConsentEvent, with phone numbers
normalised to E.164 by the contract's own normalise_phone.

Two additive fields the contract does not carry, required by PROJ-400/440
("per-contact channel preference and quiet hours"):

    preferred_channel   sms | email | telegram
    quiet_hours_start / quiet_hours_end   local HH:MM, inclusive-exclusive

They are additive rather than a contract change: a consumer reading only the
contract's fields is unaffected. If PROJ-404 later adopts them, delete them
here. Note the contract's contacts are phone-centric (phone_number is the only
required identifier), so `sms` is the default channel and choosing `email`
without an email address is rejected rather than silently unsendable.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, time
from typing import Any

from contracts.schemas import ConsentState, normalise_phone

from app.web.store import DEFAULT_ORG_ID, table

log = logging.getLogger("agent_factory.contacts")

CHANNELS = ("sms", "email", "telegram")
NAME_MAX = 120
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Import caps: a runaway CSV should fail fast rather than fill the disk.
CSV_MAX_ROWS = 5000
CSV_MAX_BYTES = 2 * 1024 * 1024


class ValidationError(ValueError):
    """Per-field messages, so a form can render them beside the inputs."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def contacts_table():
    return table("contacts")


# ── Validation ────────────────────────────────────────────────
def validate(payload: dict[str, Any], *, creating: bool,
             existing: dict[str, Any] | None = None,
             org_id: int = DEFAULT_ORG_ID) -> dict[str, Any]:
    """
    Validate and normalise a contact payload. Collects every error rather than
    stopping at the first.
    """
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    # ── phone_number ─────────────────────────────────────────
    if creating or "phone_number" in payload:
        raw = str(payload.get("phone_number") or "").strip()
        if not raw:
            errors["phone_number"] = "Enter a phone number."
        elif not 6 <= len(raw) <= 20:
            errors["phone_number"] = "Phone number must be 6 to 20 characters."
        else:
            try:
                phone = normalise_phone(raw)
            except ValueError:
                errors["phone_number"] = "That does not look like a phone number."
            else:
                # Normalising first is what makes this check work: 0412345678
                # and +61412345678 are the same person and must not both exist.
                dupe = contacts_table().find(org_id=org_id, phone_number=phone)
                if dupe and (not existing or int(dupe["id"]) != int(existing["id"])):
                    errors["phone_number"] = (
                        f"A contact with this number already exists "
                        f"(#{dupe['id']}{', ' + dupe['name'] if dupe.get('name') else ''})."
                    )
                else:
                    clean["phone_number"] = phone

    # ── name ─────────────────────────────────────────────────
    if "name" in payload:
        name = payload.get("name")
        name = str(name).strip() if name is not None else ""
        if len(name) > NAME_MAX:
            errors["name"] = f"Keep the name under {NAME_MAX} characters."
        else:
            clean["name"] = name or None

    # ── email (needed only for the email channel) ────────────
    if "email" in payload:
        email = str(payload.get("email") or "").strip()
        if email and not EMAIL_RE.match(email):
            errors["email"] = "That does not look like an email address."
        else:
            clean["email"] = email or None

    # ── consent_state ────────────────────────────────────────
    if "consent_state" in payload:
        state = str(payload.get("consent_state") or "").strip().lower()
        valid = [s.value for s in ConsentState]
        if state not in valid:
            errors["consent_state"] = f"Expected one of: {', '.join(valid)}."
        else:
            clean["consent_state"] = state

    # ── preferred_channel (PROJ-440) ─────────────────────────
    if "preferred_channel" in payload:
        ch = str(payload.get("preferred_channel") or "").strip().lower()
        if ch not in CHANNELS:
            errors["preferred_channel"] = f"Expected one of: {', '.join(CHANNELS)}."
        else:
            # Choosing a channel with no address for it produces a contact that
            # can never be reached. Refuse it rather than discover it at send.
            merged_email = clean.get("email", (existing or {}).get("email"))
            if ch == "email" and not merged_email:
                errors["preferred_channel"] = "Add an email address before choosing the email channel."
            else:
                clean["preferred_channel"] = ch

    # ── quiet hours (PROJ-440) ───────────────────────────────
    for key in ("quiet_hours_start", "quiet_hours_end"):
        if key in payload:
            val = payload.get(key)
            if val in (None, ""):
                clean[key] = None
            elif not HHMM_RE.match(str(val)):
                errors[key] = "Use 24-hour HH:MM, e.g. 21:00."
            else:
                clean[key] = str(val)

    # Both ends or neither — one alone is a window with no other edge.
    start = clean.get("quiet_hours_start", (existing or {}).get("quiet_hours_start"))
    end = clean.get("quiet_hours_end", (existing or {}).get("quiet_hours_end"))
    if bool(start) != bool(end):
        errors["quiet_hours_start"] = "Set both a start and an end, or neither."

    allowed = {"phone_number", "name", "email", "consent_state",
               "preferred_channel", "quiet_hours_start", "quiet_hours_end"}
    unknown = set(payload) - allowed
    if unknown:
        errors["_"] = f"Unexpected field(s): {', '.join(sorted(unknown))}."

    if errors:
        raise ValidationError(errors)
    return clean


# ── CRUD (PROJ-418) ───────────────────────────────────────────
def list_contacts(org_id: int = DEFAULT_ORG_ID, *, q: str | None = None,
                  consent_state: str | None = None) -> list[dict[str, Any]]:
    rows = contacts_table().all(org_id)

    if q:
        needle = q.strip().lower()
        rows = [
            r for r in rows
            if needle in (r.get("name") or "").lower()
            or needle in (r.get("phone_number") or "").lower()
            or needle in (r.get("email") or "").lower()
        ]

    if consent_state:
        wanted = {s.strip().lower() for s in consent_state.split(",") if s.strip()}
        valid = {s.value for s in ConsentState}
        unknown = wanted - valid
        if unknown:
            raise ValidationError(
                {"consent_state": f"Unknown: {', '.join(sorted(unknown))}. "
                                  f"Expected one of: {', '.join(sorted(valid))}."}
            )
        rows = [r for r in rows if r.get("consent_state") in wanted]

    rows.sort(key=lambda r: ((r.get("name") or "~").lower(), r.get("phone_number", "")))
    return rows


def get_contact(contact_id: int, org_id: int = DEFAULT_ORG_ID) -> dict[str, Any] | None:
    return contacts_table().get(contact_id, org_id)


def create_contact(payload: dict[str, Any], org_id: int = DEFAULT_ORG_ID,
                   *, source: str = "manual") -> dict[str, Any]:
    clean = validate(payload, creating=True, org_id=org_id)
    row = contacts_table().insert(
        {
            "phone_number": clean["phone_number"],
            "name": clean.get("name"),
            "email": clean.get("email"),
            # A new contact has not been asked yet — never assume opted in.
            "consent_state": clean.get("consent_state", ConsentState.UNKNOWN.value),
            "preferred_channel": clean.get("preferred_channel", "sms"),
            "quiet_hours_start": clean.get("quiet_hours_start"),
            "quiet_hours_end": clean.get("quiet_hours_end"),
            "created_at": _now_iso(),
        },
        org_id=org_id,
    )

    from app.web import consent

    consent.record(
        contact_id=int(row["id"]), org_id=org_id,
        old_state=None, new_state=row["consent_state"],
        source=source, detail="contact created",
    )
    return row


def update_contact(contact_id: int, payload: dict[str, Any],
                   org_id: int = DEFAULT_ORG_ID, *, source: str = "manual") -> dict[str, Any] | None:
    existing = get_contact(contact_id, org_id)
    if existing is None:
        return None

    clean = validate(payload, creating=False, existing=existing, org_id=org_id)
    updated = contacts_table().update(contact_id, clean, org_id=org_id)

    # A consent change is an auditable event, not just a field edit (PROJ-413).
    if updated and "consent_state" in clean and clean["consent_state"] != existing.get("consent_state"):
        from app.web import consent

        consent.record(
            contact_id=int(contact_id), org_id=org_id,
            old_state=existing.get("consent_state"), new_state=clean["consent_state"],
            source=source, detail="updated via contact edit",
        )
    return updated


def delete_contact(contact_id: int, org_id: int = DEFAULT_ORG_ID) -> bool:
    return contacts_table().delete(contact_id, org_id)


# ── Quiet hours (PROJ-440) ────────────────────────────────────
def in_quiet_hours(contact: dict[str, Any], when: datetime | None = None) -> bool:
    """
    Is `when` inside this contact's quiet hours?

    Windows that cross midnight (21:00–07:00) are the normal case, so the
    comparison handles wrapping rather than assuming start < end.
    """
    start_s, end_s = contact.get("quiet_hours_start"), contact.get("quiet_hours_end")
    if not start_s or not end_s:
        return False

    when = when or datetime.now().astimezone()
    now_t = when.timetz().replace(tzinfo=None)
    sh, sm = (int(x) for x in start_s.split(":"))
    eh, em = (int(x) for x in end_s.split(":"))
    start, end = time(sh, sm), time(eh, em)

    if start == end:
        return False
    if start < end:
        return start <= now_t < end
    # Wraps midnight.
    return now_t >= start or now_t < end


# ── CSV import (PROJ-420) ─────────────────────────────────────
CSV_COLUMNS = ("phone_number", "name", "email", "preferred_channel",
               "quiet_hours_start", "quiet_hours_end", "consent_state")


def import_csv(raw: bytes | str, org_id: int = DEFAULT_ORG_ID,
               *, dry_run: bool = False) -> dict[str, Any]:
    """
    Import contacts from CSV.

    Every row is reported individually: a valid row is not rejected because
    another row is broken, and a rejected row says which line and why. Partial
    success with a per-row report beats all-or-nothing on a 500-row file where
    one number is malformed.

    dry_run validates and reports without writing — so someone can check a file
    before committing to it.
    """
    if isinstance(raw, bytes):
        if len(raw) > CSV_MAX_BYTES:
            raise ValidationError({"file": f"File is larger than {CSV_MAX_BYTES // 1024 // 1024} MB."})
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Excel on Windows commonly exports cp1252.
            try:
                text = raw.decode("cp1252")
            except UnicodeDecodeError:
                raise ValidationError({"file": "Could not decode the file as UTF-8 or Windows-1252."}) from None
    else:
        text = raw

    if not text.strip():
        raise ValidationError({"file": "The file is empty."})

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError({"file": "No header row found."})

    headers = [(h or "").strip().lower() for h in reader.fieldnames]
    if "phone_number" not in headers:
        raise ValidationError(
            {"file": f"A 'phone_number' column is required. Found: {', '.join(headers) or '(none)'}."}
        )

    unknown_cols = [h for h in headers if h and h not in CSV_COLUMNS]

    created: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_in_file: dict[str, int] = {}

    for index, row in enumerate(reader, start=2):   # line 1 is the header
        if len(created) + len(failed) + len(skipped) >= CSV_MAX_ROWS:
            failed.append({"line": index, "error": f"Stopped at the {CSV_MAX_ROWS}-row limit."})
            break

        payload = {}
        for col in CSV_COLUMNS:
            val = row.get(col)
            if val is None:
                # DictReader keys are the original header casing.
                for k, v in row.items():
                    if (k or "").strip().lower() == col:
                        val = v
                        break
            if val is not None and str(val).strip() != "":
                payload[col] = str(val).strip()

        if not payload.get("phone_number"):
            failed.append({"line": index, "error": "phone_number is empty."})
            continue

        # Catch duplicates within the file itself, which the store cannot see
        # until the first one is written.
        try:
            canonical = normalise_phone(payload["phone_number"])
        except ValueError:
            failed.append({"line": index, "phone_number": payload["phone_number"],
                           "error": "That does not look like a phone number."})
            continue

        if canonical in seen_in_file:
            skipped.append({
                "line": index, "phone_number": canonical,
                "reason": f"Duplicate of line {seen_in_file[canonical]} in this file.",
            })
            continue
        seen_in_file[canonical] = index

        if dry_run:
            dupe = contacts_table().find(org_id=org_id, phone_number=canonical)
            if dupe:
                skipped.append({"line": index, "phone_number": canonical,
                                "reason": f"Already exists as #{dupe['id']}."})
                continue
            try:
                validate(payload, creating=True, org_id=org_id)
            except ValidationError as exc:
                failed.append({"line": index, "phone_number": canonical,
                               "error": "; ".join(exc.errors.values())})
                continue
            created.append({"line": index, "phone_number": canonical, "name": payload.get("name")})
            continue

        try:
            row_out = create_contact(payload, org_id=org_id, source="import")
        except ValidationError as exc:
            # An existing-contact clash is a skip, not a failure — re-importing
            # a file should be idempotent rather than a wall of errors.
            if "already exists" in exc.errors.get("phone_number", ""):
                skipped.append({"line": index, "phone_number": canonical,
                                "reason": exc.errors["phone_number"]})
            else:
                failed.append({"line": index, "phone_number": canonical,
                               "error": "; ".join(exc.errors.values())})
            continue

        created.append({"line": index, "id": row_out["id"],
                        "phone_number": row_out["phone_number"], "name": row_out.get("name")})

    return {
        "dry_run": dry_run,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "unknown_columns": unknown_cols,
    }


def csv_template() -> str:
    """A header row plus one example, so people do not guess the format."""
    return (
        ",".join(CSV_COLUMNS) + "\n"
        "+61412345678,Jane Citizen,jane@example.com,sms,21:00,07:00,unknown\n"
    )
