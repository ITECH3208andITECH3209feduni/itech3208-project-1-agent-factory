# tests/test_reminders_booking_hooks.py — agent/reminders/booking_hooks.py (PROJ-445, PROJ-446)
from datetime import datetime, timedelta

import pytest

from agent.reminders.booking_hooks import create_reminder_for_booking
from agent.reminders.store import ReminderStore


@pytest.fixture
def store(tmp_path):
    return ReminderStore(db_path=str(tmp_path / "reminders.db"))


def test_creates_reminder_lead_hours_before_appointment(store):
    appointment_start = (datetime.now() + timedelta(days=2)).replace(microsecond=0).isoformat()
    result = create_reminder_for_booking(
        summary="Consultation",
        start_iso=appointment_start,
        contact_channel="sms",
        contact_address="+15551234567",
        store=store,
        lead_hours=24,
        contact_timezone="UTC",
    )
    assert result["ok"] is True
    reminder = store.get(result["reminder_id"])
    assert reminder.contact_address == "+15551234567"
    assert "Consultation" in reminder.message

    expected_local = datetime.fromisoformat(appointment_start) - timedelta(hours=24)
    actual = datetime.fromisoformat(reminder.scheduled_at_utc)
    assert abs((actual.replace(tzinfo=None) - expected_local)) < timedelta(seconds=1)


def test_no_contact_address_fails_gracefully_without_raising(store):
    result = create_reminder_for_booking(
        summary="Consultation",
        start_iso=(datetime.now() + timedelta(days=1)).isoformat(),
        contact_channel="sms",
        contact_address="",
        store=store,
    )
    assert result["ok"] is False
    assert "still confirmed" in result["error"]


def test_bad_start_iso_fails_gracefully(store):
    result = create_reminder_for_booking(
        summary="Consultation",
        start_iso="not-a-date",
        contact_channel="sms",
        contact_address="+1",
        store=store,
    )
    assert result["ok"] is False


def test_booking_id_links_reminder_to_booking(store):
    result = create_reminder_for_booking(
        summary="Consultation",
        start_iso=(datetime.now() + timedelta(days=1)).isoformat(),
        contact_channel="email",
        contact_address="user@example.com",
        store=store,
        booking_id="booking-abc",
    )
    assert result["ok"] is True
    linked = store.list_for_booking("booking-abc")
    assert len(linked) == 1
    assert linked[0].id == result["reminder_id"]
