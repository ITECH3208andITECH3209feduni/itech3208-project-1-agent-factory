# agent/bookings.py
# ──────────────────────────────────────────────────────────────
# Appointment bookings made by the AI receptionist.
#
# A booking starts "unconfirmed". The patient gets a text and an email with a
# private link; opening it shows the appointment and a Confirm button, and
# pressing that marks the booking "confirmed". The dashboard Calendar tab
# lists both, so the clinic can see which appointments are locked in.
#
# Stored in SQLite next to the other app databases (on Render that is /data,
# which deploy/persist.py saves to the bucket), so bookings survive restarts.
# This works with or without Google Calendar.
#
# Only a SHA-256 hash of each confirmation token is stored: someone who reads
# the database still cannot confirm other people's appointments.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config.settings import BOOKINGS_DB, TIMEZONE

log = logging.getLogger("agent_factory.bookings")

UNCONFIRMED = "unconfirmed"
CONFIRMED = "confirmed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id        INTEGER,
    summary       TEXT NOT NULL,
    start_local   TEXT NOT NULL,
    end_local     TEXT NOT NULL,
    timezone      TEXT NOT NULL,
    name          TEXT NOT NULL,
    phone         TEXT NOT NULL,
    email         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'unconfirmed',
    token_hash    TEXT NOT NULL UNIQUE,
    channel       TEXT NOT NULL DEFAULT 'web',
    session_id    TEXT,
    created_at    TEXT NOT NULL,
    confirmed_at  TEXT,
    sms_status    TEXT,
    email_status  TEXT
);
CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings (start_local);
CREATE INDEX IF NOT EXISTS idx_bookings_org ON bookings (org_id);
"""

# Bookings made before an organisation could be resolved (org_id NULL) belong
# to the first organisation, the same rule as activity and delivery history.
LEGACY_ORG_ID = 1


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or BOOKINGS_DB
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


# ── Writing ────────────────────────────────────────────────────

def create_booking(
    *,
    summary: str,
    start_local: str,
    end_local: str,
    name: str,
    phone: str,
    email: str = "",
    org_id: int | None = None,
    channel: str = "web",
    session_id: str | None = None,
    tz: str | None = None,
    db_path: str | None = None,
) -> tuple[dict, str]:
    """Save an unconfirmed booking. Returns (booking, token); the token goes
    in the confirmation link and is never stored in plain text."""
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO bookings (org_id, summary, start_local, end_local, timezone,
                   name, phone, email, status, token_hash, channel, session_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (org_id, summary, start_local, end_local, tz or TIMEZONE, name, phone,
             email or "", UNCONFIRMED, _hash(token), channel or "web", session_id, now),
        )
        booking = _row(conn.execute("SELECT * FROM bookings WHERE id = ?", (cur.lastrowid,)).fetchone())
    return booking, token


def get_by_token(token: str, db_path: str | None = None) -> dict | None:
    if not token:
        return None
    with _connect(db_path) as conn:
        return _row(conn.execute(
            "SELECT * FROM bookings WHERE token_hash = ?", (_hash(token),)
        ).fetchone())


def confirm_by_token(token: str, db_path: str | None = None) -> tuple[dict | None, bool]:
    """Mark the booking confirmed. Returns (booking, newly_confirmed); pressing
    Confirm twice is harmless."""
    booking = get_by_token(token, db_path)
    if not booking:
        return None, False
    if booking["status"] == CONFIRMED:
        return booking, False
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE bookings SET status = ?, confirmed_at = ? WHERE id = ? AND status != ?",
            (CONFIRMED, now, booking["id"], CONFIRMED),
        )
        booking = _row(conn.execute("SELECT * FROM bookings WHERE id = ?", (booking["id"],)).fetchone())
    return booking, True


def set_notify_status(booking_id: int, *, sms: str | None = None, email: str | None = None,
                      db_path: str | None = None) -> None:
    with _connect(db_path) as conn:
        if sms is not None:
            conn.execute("UPDATE bookings SET sms_status = ? WHERE id = ?", (sms, booking_id))
        if email is not None:
            conn.execute("UPDATE bookings SET email_status = ? WHERE id = ?", (email, booking_id))


# ── Reading ────────────────────────────────────────────────────

def list_upcoming(org_id: int | None, limit: int = 50, db_path: str | None = None,
                  now: datetime | None = None) -> list[dict]:
    """Bookings from the start of today onwards, earliest first. org_id=None
    means no scoping (internal use); the dashboard always passes one."""
    tz = ZoneInfo(TIMEZONE)
    today = (now or datetime.now(tz)).astimezone(tz).strftime("%Y-%m-%dT00:00:00")
    sql = "SELECT * FROM bookings WHERE start_local >= ?"
    params: list = [today]
    if org_id is not None:
        if org_id == LEGACY_ORG_ID:
            sql += " AND (org_id = ? OR org_id IS NULL)"
        else:
            sql += " AND org_id = ?"
        params.append(org_id)
    sql += " ORDER BY start_local ASC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ── Formatting ─────────────────────────────────────────────────

def when_text(start_local: str) -> str:
    """'Monday 20 October at 10 am' / '... at 2:30 pm'."""
    try:
        dt = datetime.fromisoformat(start_local)
    except ValueError:
        return start_local
    hour = dt.strftime("%I").lstrip("0") or "12"
    minute = "" if dt.minute == 0 else dt.strftime(":%M")
    return f"{dt.strftime('%A')} {dt.day} {dt.strftime('%B')} at {hour}{minute} {dt.strftime('%p').lower()}"


def in_sentence(summary: str) -> str:
    """'Check-up' -> 'check-up' mid-sentence; acronyms like 'MRI scan' stay."""
    if len(summary) > 1 and summary[0].isupper() and summary[1].islower():
        return summary[0].lower() + summary[1:]
    return summary


def phone_text(phone: str) -> str:
    """Australian mobiles read back the way people say them: 0412 345 678."""
    if phone.startswith("+61") and len(phone) == 12:
        local = "0" + phone[3:]
        return f"{local[:4]} {local[4:7]} {local[7:]}"
    return phone


def brand_name() -> str:
    return os.environ.get("BRAND_NAME", "").strip() or "Agent Factory"


def confirm_url(token: str) -> str:
    base = os.getenv("APP_BASE_URL", "").strip().rstrip("/") or "http://localhost:8000"
    return f"{base}/booking/confirm/{token}"


# ── Telling the patient ────────────────────────────────────────

def _sms_text(booking: dict, link: str) -> str:
    first = booking["name"].split()[0]
    return (
        f"Hi {first}, your {in_sentence(booking['summary'])} at {brand_name()} on "
        f"{when_text(booking['start_local'])} is booked but not yet confirmed. "
        f"Please confirm here: {link}"
    )


def _email_text(booking: dict, link: str) -> tuple[str, str]:
    subject = f"Please confirm your appointment at {brand_name()}"
    body = (
        f"Hi {booking['name']},\n\n"
        f"Thanks for booking with {brand_name()}. Here are the details:\n\n"
        f"  Appointment: {booking['summary']}\n"
        f"  When: {when_text(booking['start_local'])}\n"
        f"  Name: {booking['name']}\n"
        f"  Phone: {phone_text(booking['phone'])}\n\n"
        f"Your appointment is not confirmed yet. Please confirm it here:\n{link}\n\n"
        f"If you didn't make this booking, you can ignore this email.\n\n"
        f"{brand_name()}\n"
    )
    return subject, body


def _sms_opted_out(booking: dict) -> bool:
    """Someone who replied STOP never gets another text from us."""
    if booking.get("org_id") is None:
        return False
    try:
        from auth.consent import get_consent_by_phone
        from contracts.schemas import ConsentState

        found = get_consent_by_phone(booking["org_id"], booking["phone"])
        return bool(found) and found[1] == ConsentState.OPTED_OUT
    except Exception:  # noqa: BLE001 - a lookup problem must not block the booking
        return False


def _record(booking: dict, channel: str, recipient: str, result, text: str) -> None:
    """Show the message in Delivery History like any other send."""
    try:
        from app.web_ui.activity_db import log_delivery_event, update_delivery_status

        msg_id = result.provider_id or f"BK-{uuid.uuid4().hex[:12].upper()}"
        log_delivery_event(
            message_id=msg_id, recipient=recipient, channel=channel,
            reminder_type="booking_confirmation", status="sent" if result.ok else "failed",
            metadata={"message": text[:500], "booking_id": booking["id"], "attempts": result.attempts},
            org_id=booking.get("org_id"),
        )
        if not result.ok:
            update_delivery_status(msg_id, "failed", error_message=result.error or "Delivery failed")
    except Exception:  # noqa: BLE001
        log.exception("could not record booking confirmation delivery")


def notify(booking: dict, token: str, *, sms_channel=None, email_channel=None,
           db_path: str | None = None) -> dict:
    """Send the confirmation link by SMS and email. Never raises: a failed
    message is recorded (Delivery History, booking row) and the booking stays."""
    from agent.delivery import EmailChannel, SMSChannel

    link = confirm_url(token)
    outcome = {"sms": "skipped", "email": "skipped"}

    if booking.get("phone"):
        if _sms_opted_out(booking):
            outcome["sms"] = "opted_out"
        else:
            text = _sms_text(booking, link)
            try:
                result = (sms_channel or SMSChannel()).send(booking["phone"], text)
                outcome["sms"] = "sent" if result.ok else f"failed: {result.error or ''}"[:200]
                _record(booking, "sms", booking["phone"], result, text)
            except Exception as exc:  # noqa: BLE001
                outcome["sms"] = f"failed: {exc}"[:200]
                log.exception("booking SMS crashed")

    if booking.get("email"):
        subject, body = _email_text(booking, link)
        try:
            result = (email_channel or EmailChannel()).send(booking["email"], body, subject=subject)
            outcome["email"] = "sent" if result.ok else f"failed: {result.error or ''}"[:200]
            _record(booking, "email", booking["email"], result, body)
        except Exception as exc:  # noqa: BLE001
            outcome["email"] = f"failed: {exc}"[:200]
            log.exception("booking email crashed")

    set_notify_status(booking["id"], sms=outcome["sms"], email=outcome["email"], db_path=db_path)
    return outcome


def notify_in_background(booking: dict, token: str) -> None:
    """SMTP and Twilio can take seconds; a caller on the phone must not wait."""
    threading.Thread(target=notify, args=(booking, token), daemon=True).start()


def schedule_reminder(booking: dict) -> dict:
    """Once confirmed, remind the patient ahead of the appointment."""
    from agent.reminders.booking_hooks import create_reminder_for_booking

    if booking.get("phone"):
        channel, address = "sms", booking["phone"]
    elif booking.get("email"):
        channel, address = "email", booking["email"]
    else:
        return {"ok": False, "error": "no contact details"}
    try:
        start = datetime.fromisoformat(booking["start_local"])
        if start - datetime.now() < timedelta(hours=1):
            return {"ok": False, "error": "appointment is too soon for a reminder"}
    except ValueError:
        pass
    return create_reminder_for_booking(
        summary=booking["summary"], start_iso=booking["start_local"],
        contact_channel=channel, contact_address=address,
        contact_timezone=booking.get("timezone") or TIMEZONE,
        booking_id=f"booking-{booking['id']}",
    )
