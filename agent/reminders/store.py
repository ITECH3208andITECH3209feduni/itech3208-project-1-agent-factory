# agent/reminders/store.py
# ──────────────────────────────────────────────────────────────
# Reminders store (PROJ-422), timezone-correct scheduling (PROJ-424),
# recurring reminders (PROJ-425), edit/pause/cancel/reschedule
# (PROJ-426) — Dilraj Singh
#
# SQLite-backed, mirroring agent/memory.py's pattern (WAL mode, one
# shared connection). Reminders are always stored with an absolute UTC
# fire time (scheduled_at_utc) plus the IANA timezone the contact is
# in — the scheduler only ever compares against UTC "now", and the
# timezone is used solely to compute correct local wall-clock times
# (creation input, and the next occurrence of a recurring reminder)
# without drifting across DST transitions.
#
# NOTE ON THE DATA CONTRACT: PROJ-404 (Dhiman's contacts/accounts
# schema) isn't merged into this branch yet, so this store references
# contacts by plain (channel, address) pairs rather than a contact_id
# foreign key. See config/settings.py's REMINDERS_DB comment.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from config.settings import REMINDERS_DB

VALID_STATUSES = {"pending", "sending", "sent", "failed", "cancelled", "paused"}
VALID_CHANNELS = {"sms", "voice", "email"}
VALID_FREQUENCIES = {"none", "daily", "weekly", "custom"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id                TEXT    PRIMARY KEY,
    contact_channel   TEXT    NOT NULL,
    contact_address   TEXT    NOT NULL,
    message           TEXT    NOT NULL,
    subject           TEXT    NOT NULL DEFAULT 'Reminder',
    scheduled_at_utc  TEXT    NOT NULL,
    contact_timezone  TEXT    NOT NULL,
    recurrence        TEXT,
    status            TEXT    NOT NULL DEFAULT 'pending',
    booking_id        TEXT,
    provider_id       TEXT,
    last_error        TEXT,
    send_attempts     INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders (status, scheduled_at_utc);

CREATE INDEX IF NOT EXISTS idx_reminders_booking
    ON reminders (booking_id);
"""


@dataclass
class Reminder:
    id: str
    contact_channel: str
    contact_address: str
    message: str
    subject: str
    scheduled_at_utc: str
    contact_timezone: str
    recurrence: dict | None
    status: str
    booking_id: str | None
    provider_id: str | None
    last_error: str | None
    send_attempts: int
    created_at: str
    updated_at: str

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> "Reminder":
        d = dict(row)
        d["recurrence"] = json.loads(d["recurrence"]) if d["recurrence"] else None
        return cls(**d)


def _utc_now_iso() -> str:
    return datetime.now(dt_timezone.utc).isoformat()


def local_to_utc_iso(local_naive_iso: str, tz_name: str) -> str:
    """Interpret local_naive_iso (e.g. '2026-08-10T09:00:00', no offset)
    as wall-clock time in tz_name, and return the equivalent UTC ISO
    string. This is the one place local-time input gets converted —
    everything else in the store deals only in UTC."""
    local_dt = datetime.fromisoformat(local_naive_iso)
    if local_dt.tzinfo is not None:
        # Already timezone-aware — trust it and just normalize to UTC.
        return local_dt.astimezone(dt_timezone.utc).isoformat()
    aware = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    return aware.astimezone(dt_timezone.utc).isoformat()


def _next_occurrence_utc(scheduled_at_utc: str, tz_name: str, recurrence: dict) -> str:
    """Compute the next fire time for a recurring reminder. Adds the
    interval to the LOCAL wall-clock time (not to the UTC instant) so
    "every day at 9am" stays 9am local through a DST transition —
    adding 24h in UTC would drift by an hour when the clocks change."""
    freq = recurrence.get("freq", "none")
    utc_dt = datetime.fromisoformat(scheduled_at_utc)
    local_dt = utc_dt.astimezone(ZoneInfo(tz_name))

    if freq == "daily":
        next_local = local_dt + timedelta(days=1)
    elif freq == "weekly":
        next_local = local_dt + timedelta(weeks=1)
    elif freq == "custom":
        interval_days = int(recurrence.get("interval_days", 1))
        if interval_days < 1:
            raise ValueError("custom recurrence needs interval_days >= 1")
        next_local = local_dt + timedelta(days=interval_days)
    else:
        raise ValueError(f"not a recurring frequency: {freq!r}")

    return next_local.astimezone(dt_timezone.utc).isoformat()


class ReminderStore:
    def __init__(self, db_path: str | None = None):
        self._path = db_path or REMINDERS_DB
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._apply_schema()

    def _apply_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Create (PROJ-422) ────────────────────────────────────────

    def create(
        self,
        contact_channel: str,
        contact_address: str,
        message: str,
        scheduled_at_utc: str,
        contact_timezone: str,
        subject: str = "Reminder",
        recurrence: dict | None = None,
        booking_id: str | None = None,
    ) -> Reminder:
        if contact_channel not in VALID_CHANNELS:
            raise ValueError(f"invalid contact_channel: {contact_channel!r}")
        if recurrence is not None and recurrence.get("freq") not in VALID_FREQUENCIES:
            raise ValueError(f"invalid recurrence.freq: {recurrence.get('freq')!r}")
        # Validates it's a real IANA name up front rather than failing
        # later inside the scheduler.
        ZoneInfo(contact_timezone)

        now = _utc_now_iso()
        reminder_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO reminders (id, contact_channel, contact_address, message,"
            " subject, scheduled_at_utc, contact_timezone, recurrence, status,"
            " booking_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
            (
                reminder_id,
                contact_channel,
                contact_address,
                message,
                subject,
                scheduled_at_utc,
                contact_timezone,
                json.dumps(recurrence) if recurrence else None,
                booking_id,
                now,
                now,
            ),
        )
        self._conn.commit()
        return self.get(reminder_id)

    # ── Read ──────────────────────────────────────────────────────

    def get(self, reminder_id: str) -> Reminder | None:
        row = self._conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        return Reminder._from_row(row) if row else None

    def list_due(self, now_utc: str | None = None, limit: int = 100) -> list[Reminder]:
        """Reminders that are pending and whose fire time has arrived.
        Used by the scheduler's poll loop (PROJ-423)."""
        now_utc = now_utc or _utc_now_iso()
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND scheduled_at_utc <= ?"
            " ORDER BY scheduled_at_utc ASC LIMIT ?",
            (now_utc, limit),
        ).fetchall()
        return [Reminder._from_row(r) for r in rows]

    def list_for_booking(self, booking_id: str) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE booking_id = ? ORDER BY scheduled_at_utc ASC",
            (booking_id,),
        ).fetchall()
        return [Reminder._from_row(r) for r in rows]

    # ── Scheduler hand-off (PROJ-423: claim so two ticks/processes ──
    # ── never both send the same reminder) ───────────────────────

    def claim(self, reminder_id: str) -> bool:
        """Atomically moves a reminder from pending -> sending. Returns
        True only if THIS call performed the transition — the WHERE
        clause means a second, concurrent claim() on the same id
        matches zero rows and returns False, so a reminder is sent
        at most once even if the scheduler restarts mid-tick (the row
        it already claimed either finished as 'sent'/'failed', or is
        still 'sending' and gets picked up by the stale-claim sweep,
        never re-claimed by a fresh 'pending' scan)."""
        now = _utc_now_iso()
        cur = self._conn.execute(
            "UPDATE reminders SET status = 'sending', updated_at = ?"
            " WHERE id = ? AND status = 'pending'",
            (now, reminder_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def mark_sent(self, reminder_id: str, provider_id: str | None) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            "UPDATE reminders SET status = 'sent', provider_id = ?, updated_at = ?,"
            " send_attempts = send_attempts + 1 WHERE id = ?",
            (provider_id, now, reminder_id),
        )
        self._conn.commit()

    def mark_failed(self, reminder_id: str, error: str) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            "UPDATE reminders SET status = 'failed', last_error = ?, updated_at = ?,"
            " send_attempts = send_attempts + 1 WHERE id = ?",
            (error[:500], now, reminder_id),
        )
        self._conn.commit()

    def reclaim_stale_sending(self, older_than_minutes: int = 10) -> int:
        """If the scheduler process dies mid-send, a reminder can be
        stuck in 'sending' forever. Anything that's been 'sending' for
        longer than a normal send should ever take gets bounced back
        to 'pending' so the next tick retries it — restart-safety for
        PROJ-423 without needing a separate crash-recovery process."""
        cutoff = (datetime.now(dt_timezone.utc) - timedelta(minutes=older_than_minutes)).isoformat()
        cur = self._conn.execute(
            "UPDATE reminders SET status = 'pending', updated_at = ?"
            " WHERE status = 'sending' AND updated_at < ?",
            (_utc_now_iso(), cutoff),
        )
        self._conn.commit()
        return cur.rowcount

    # ── Recurrence (PROJ-425) ────────────────────────────────────

    def schedule_next_occurrence(self, sent_reminder: Reminder) -> Reminder | None:
        """After a recurring reminder is sent, create the next one in
        the series. Returns None for a one-off reminder (recurrence is
        None or freq == 'none')."""
        if not sent_reminder.recurrence or sent_reminder.recurrence.get("freq") == "none":
            return None
        next_utc = _next_occurrence_utc(
            sent_reminder.scheduled_at_utc, sent_reminder.contact_timezone, sent_reminder.recurrence
        )
        return self.create(
            contact_channel=sent_reminder.contact_channel,
            contact_address=sent_reminder.contact_address,
            message=sent_reminder.message,
            subject=sent_reminder.subject,
            scheduled_at_utc=next_utc,
            contact_timezone=sent_reminder.contact_timezone,
            recurrence=sent_reminder.recurrence,
            booking_id=sent_reminder.booking_id,
        )

    # ── Edit / pause / cancel / reschedule (PROJ-426) ────────────

    def _touch_pending_only(self, reminder_id: str, **fields) -> bool:
        """Shared guard: only 'pending' or 'paused' reminders can be
        edited/rescheduled — one that's already 'sending'/'sent' is
        too late to change, and a 'cancelled' one stays cancelled."""
        reminder = self.get(reminder_id)
        if reminder is None or reminder.status not in ("pending", "paused"):
            return False
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [_utc_now_iso(), reminder_id]
        self._conn.execute(
            f"UPDATE reminders SET {set_clause}, updated_at = ? WHERE id = ?", values
        )
        self._conn.commit()
        return True

    def update_message(self, reminder_id: str, message: str, subject: str | None = None) -> bool:
        fields = {"message": message}
        if subject is not None:
            fields["subject"] = subject
        return self._touch_pending_only(reminder_id, **fields)

    def reschedule(self, reminder_id: str, new_scheduled_at_utc: str) -> bool:
        return self._touch_pending_only(reminder_id, scheduled_at_utc=new_scheduled_at_utc)

    def pause(self, reminder_id: str) -> bool:
        reminder = self.get(reminder_id)
        if reminder is None or reminder.status != "pending":
            return False
        self._conn.execute(
            "UPDATE reminders SET status = 'paused', updated_at = ? WHERE id = ?",
            (_utc_now_iso(), reminder_id),
        )
        self._conn.commit()
        return True

    def resume(self, reminder_id: str) -> bool:
        reminder = self.get(reminder_id)
        if reminder is None or reminder.status != "paused":
            return False
        self._conn.execute(
            "UPDATE reminders SET status = 'pending', updated_at = ? WHERE id = ?",
            (_utc_now_iso(), reminder_id),
        )
        self._conn.commit()
        return True

    def cancel(self, reminder_id: str) -> bool:
        reminder = self.get(reminder_id)
        if reminder is None or reminder.status in ("sent", "cancelled"):
            return False
        self._conn.execute(
            "UPDATE reminders SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (_utc_now_iso(), reminder_id),
        )
        self._conn.commit()
        return True
