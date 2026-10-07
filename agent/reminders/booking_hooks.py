# agent/reminders/booking_hooks.py
# ──────────────────────────────────────────────────────────────
# Booking tie-in (PROJ-445, PROJ-446) — Dilraj Singh
#
# Links the AI Receptionist's existing calendar-booking flow
# (agent/calendar_client.book_appointment, wired into
# agent/receptionist.py's _handle_appointment) to the reminders
# engine: a successful booking automatically schedules a reminder
# ahead of the appointment, on whichever channel the caller reached
# the receptionist through.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from agent.reminders.store import ReminderStore, local_to_utc_iso
from config.settings import REMINDER_DEFAULT_LEAD_HOURS, TIMEZONE


def create_reminder_for_booking(
    summary: str,
    start_iso: str,
    contact_channel: str,
    contact_address: str,
    store: ReminderStore | None = None,
    lead_hours: int | None = None,
    contact_timezone: str | None = None,
    booking_id: str | None = None,
) -> dict:
    """Schedules a "your appointment is coming up" reminder to fire
    `lead_hours` before the appointment's start time (PROJ-445). Returns
    {"ok": True, "reminder_id": ...} or {"ok": False, "error": ...} —
    never raises, so a reminder-scheduling hiccup can't take down the
    booking confirmation itself (PROJ-446: the booking still succeeds
    even if this fails; the caller decides how to phrase that to the
    user)."""
    if not contact_address:
        return {"ok": False, "error": "no contact address to remind — booking still confirmed"}

    store = store or ReminderStore()
    lead_hours = lead_hours if lead_hours is not None else REMINDER_DEFAULT_LEAD_HOURS
    tz_name = contact_timezone or TIMEZONE

    try:
        appointment_local = datetime.fromisoformat(start_iso)
        remind_at_local = appointment_local - timedelta(hours=lead_hours)
        remind_at_utc = local_to_utc_iso(remind_at_local.isoformat(), tz_name)
    except ValueError as exc:
        return {"ok": False, "error": f"couldn't parse appointment time: {exc}"}

    message = (
        f"Reminder: you have '{summary}' coming up "
        f"at {appointment_local.strftime('%A %d %B, %I:%M %p').replace(' 0', ' ')}."
    )

    try:
        reminder = store.create(
            contact_channel=contact_channel,
            contact_address=contact_address,
            message=message,
            subject=f"Reminder: {summary}",
            scheduled_at_utc=remind_at_utc,
            contact_timezone=tz_name,
            booking_id=booking_id or str(uuid.uuid4()),
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "reminder_id": reminder.id, "fires_at_utc": reminder.scheduled_at_utc}
