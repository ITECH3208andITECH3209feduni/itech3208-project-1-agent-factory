"""
app.web.reminders — reminder model, validation, and store (PROJ-439).

The form needs a backend. Dilraj's reminders store is PROJ-422 and the shape
it codes against is PROJ-404, neither of which has landed. So:

  - The shape is written down in docs/contracts/reminder.provisional.schema.json
    rather than invented inline, so the diff against Dhiman's real contract is
    mechanical.
  - Storage sits behind ReminderStore. JsonFileStore is a deliberately small
    local implementation; when PROJ-422 lands, implement the same interface and
    swap get_store(). Nothing above this module changes.

Validation is the part of this ticket that survives the swap unchanged, so it
is where the care went.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("agent_factory.reminders")

CHANNELS = ("telegram", "email", "sms")
STATUSES = ("scheduled", "sent", "cancelled", "failed")

# Only these two are reachable from the UI. 'sent' and 'failed' belong to the
# Reminders Engine (PROJ-395), which does not exist — accepting them from a
# client would let the UI fake a delivery that never happened.
CLIENT_SETTABLE_STATUSES = ("scheduled", "cancelled")

TITLE_MAX = 200
NOTES_MAX = 2000


class ValidationError(ValueError):
    """Carries per-field messages so the form can show them next to the inputs."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


# ── Model ─────────────────────────────────────────────────────
@dataclass
class Reminder:
    id:         str
    title:      str
    due_at:     str                       # ISO 8601 with offset
    channel:    str
    status:     str
    created_at: str
    updated_at: str
    notes:      str = ""
    org_id:     str | None = None         # until PROJ-392
    contact_id: str | None = None         # until PROJ-417

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def due_datetime(self) -> datetime:
        return parse_due(self.due_at)


def _now() -> datetime:
    # Local zone, not naive. A naive timestamp is how reminders end up firing
    # hours off once anything crosses a timezone.
    return datetime.now().astimezone()


def parse_due(value: str) -> datetime:
    """
    Parse an ISO 8601 datetime.

    A naive value — which is exactly what <input type="datetime-local"> sends —
    is interpreted in the server's local zone rather than silently assumed UTC.
    'Z' is accepted since fromisoformat rejects it before Python 3.11.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("due_at is required")

    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"not a valid ISO 8601 datetime: {value!r}") from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_now().tzinfo)
    return dt


# ── Validation ────────────────────────────────────────────────
def validate(payload: dict[str, Any], *, creating: bool, existing: Reminder | None = None) -> dict[str, Any]:
    """
    Validate and normalise an incoming payload.

    Returns the cleaned field values. Raises ValidationError with per-field
    messages, collecting every problem rather than stopping at the first — one
    round trip per mistake makes a form miserable to use.
    """
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}

    # ── title ────────────────────────────────────────────────
    if creating or "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not title:
            errors["title"] = "Enter a title."
        elif len(title) > TITLE_MAX:
            errors["title"] = f"Keep the title under {TITLE_MAX} characters ({len(title)} given)."
        else:
            clean["title"] = title

    # ── due_at ───────────────────────────────────────────────
    if creating or "due_at" in payload:
        try:
            due = parse_due(str(payload.get("due_at") or ""))
        except ValueError as exc:
            errors["due_at"] = str(exc) if "required" in str(exc) else "Enter a valid date and time."
        else:
            # A reminder scheduled in the past will never fire, so refuse it
            # rather than accept something that silently cannot work. Editing a
            # reminder that has already been sent or cancelled is fine — its
            # due date is history at that point.
            target_status = str(payload.get("status") or (existing.status if existing else "scheduled"))
            if target_status == "scheduled" and due <= _now():
                errors["due_at"] = "Pick a time in the future — a past reminder will never send."
            else:
                clean["due_at"] = due.isoformat()

    # ── channel ──────────────────────────────────────────────
    if creating or "channel" in payload:
        channel = str(payload.get("channel") or "").strip().lower()
        if not channel:
            errors["channel"] = "Choose a channel."
        elif channel not in CHANNELS:
            errors["channel"] = f"Choose one of: {', '.join(CHANNELS)}."
        else:
            clean["channel"] = channel

    # ── status ───────────────────────────────────────────────
    if "status" in payload:
        status = str(payload.get("status") or "").strip().lower()
        if status not in STATUSES:
            errors["status"] = f"Unknown status. Expected one of: {', '.join(STATUSES)}."
        elif status not in CLIENT_SETTABLE_STATUSES:
            # Otherwise the UI could mark something 'sent' that was never sent.
            errors["status"] = (
                f"'{status}' is set by the Reminders Engine (PROJ-395), not the client. "
                f"You can set: {', '.join(CLIENT_SETTABLE_STATUSES)}."
            )
        else:
            clean["status"] = status

    # ── notes ────────────────────────────────────────────────
    if "notes" in payload:
        notes = str(payload.get("notes") or "")
        if len(notes) > NOTES_MAX:
            errors["notes"] = f"Keep notes under {NOTES_MAX} characters ({len(notes)} given)."
        else:
            clean["notes"] = notes

    # ── contact_id ───────────────────────────────────────────
    # Accepted but NOT checked against a contact: the contacts store is
    # PROJ-417 and there is nothing to check against. Pretending to validate
    # would be worse than not validating.
    if "contact_id" in payload:
        contact = payload.get("contact_id")
        clean["contact_id"] = str(contact).strip() or None if contact else None

    # Reject unknown fields rather than dropping them silently — a typo'd field
    # name should not look like it was saved.
    allowed = {"title", "due_at", "channel", "status", "notes", "contact_id", "org_id"}
    unknown = set(payload) - allowed
    if unknown:
        errors["_"] = f"Unexpected field(s): {', '.join(sorted(unknown))}."

    if errors:
        raise ValidationError(errors)
    return clean


# ── Store ─────────────────────────────────────────────────────
class ReminderStore(ABC):
    """
    The seam PROJ-422 replaces. Keep this interface small.

    Note the absence of an org parameter: there is no tenancy model until
    PROJ-392, so every read here is unscoped. That is a known gap, not an
    oversight — add org scoping to this interface when accounts land.
    """

    @abstractmethod
    def list(self) -> list[Reminder]: ...

    @abstractmethod
    def get(self, reminder_id: str) -> Reminder | None: ...

    @abstractmethod
    def create(self, fields: dict[str, Any]) -> Reminder: ...

    @abstractmethod
    def update(self, reminder_id: str, fields: dict[str, Any]) -> Reminder | None: ...

    @abstractmethod
    def delete(self, reminder_id: str) -> bool: ...


class JsonFileStore(ReminderStore):
    """
    Provisional local store — one JSON file under store/ (gitignored).

    Not a database and not trying to be: PROJ-422 owns the real one. Writes are
    atomic via a temp file and rename, because a half-written JSON file loses
    every reminder rather than one.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── disk ──────────────────────────────────────────────
    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # Surface it rather than silently starting from empty, which would
            # look like "all your reminders vanished".
            log.error("reminders store unreadable at %s: %s", self.path, exc)
            raise RuntimeError(f"reminders store is unreadable: {exc}") from exc
        return data if isinstance(data, list) else []

    def _write_all(self, rows: Iterable[dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(list(rows), indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ── interface ─────────────────────────────────────────
    def list(self) -> list[Reminder]:
        rows = self._read_all()
        out = []
        for row in rows:
            try:
                out.append(Reminder(**row))
            except TypeError as exc:
                # A row that does not match the current shape is skipped loudly
                # — likely a leftover from before a contract change.
                log.warning("skipping malformed reminder row: %s", exc)
        # Soonest first, which is what both the dashboard and PROJ-438 want.
        out.sort(key=lambda r: r.due_at)
        return out

    def get(self, reminder_id: str) -> Reminder | None:
        return next((r for r in self.list() if r.id == reminder_id), None)

    def create(self, fields: dict[str, Any]) -> Reminder:
        now = _now().isoformat()
        reminder = Reminder(
            id=str(uuid.uuid4()),
            title=fields["title"],
            due_at=fields["due_at"],
            channel=fields["channel"],
            status=fields.get("status", "scheduled"),
            notes=fields.get("notes", ""),
            org_id=fields.get("org_id"),
            contact_id=fields.get("contact_id"),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            rows = self._read_all()
            rows.append(reminder.to_dict())
            self._write_all(rows)
        return reminder

    def update(self, reminder_id: str, fields: dict[str, Any]) -> Reminder | None:
        with self._lock:
            rows = self._read_all()
            for i, row in enumerate(rows):
                if row.get("id") == reminder_id:
                    row.update({k: v for k, v in fields.items()})
                    row["updated_at"] = _now().isoformat()
                    rows[i] = row
                    self._write_all(rows)
                    return Reminder(**row)
        return None

    def delete(self, reminder_id: str) -> bool:
        with self._lock:
            rows = self._read_all()
            kept = [r for r in rows if r.get("id") != reminder_id]
            if len(kept) == len(rows):
                return False
            self._write_all(kept)
            return True


_store: ReminderStore | None = None


def get_store() -> ReminderStore:
    """
    The single place to swap in PROJ-422's store.

    Path comes from settings.PROJECT_ROOT so it resolves the same regardless of
    the process's working directory.
    """
    global _store
    if _store is None:
        from config.settings import PROJECT_ROOT

        _store = JsonFileStore(Path(PROJECT_ROOT) / "store" / "reminders.json")
    return _store


def set_store(store: ReminderStore | None) -> None:
    """Override the store. For tests, and for PROJ-422 to install its own."""
    global _store
    _store = store


# ── Helpers used by the dashboard ─────────────────────────────
def upcoming_count() -> int:
    """Scheduled reminders still in the future."""
    now = _now()
    return sum(
        1 for r in get_store().list()
        if r.status == "scheduled" and r.due_datetime > now
    )


def sent_count() -> int:
    return sum(1 for r in get_store().list() if r.status == "sent")
