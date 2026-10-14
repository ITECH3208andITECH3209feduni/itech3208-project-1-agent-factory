"""The receptionist tiles count calls, texts and bookings, not log rows."""

import pytest

from app.web_ui import activity_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_db, "MEMORY_DB", str(tmp_path / "activity.db"))
    monkeypatch.setattr(activity_db, "_db", None)
    yield activity_db
    if activity_db._db is not None:
        activity_db._db.close()
    monkeypatch.setattr(activity_db, "_db", None)


def test_one_call_with_several_turns_is_one_call(db):
    for text in ("hours?", "services?", "goodbye"):
        db.log_activity("voice", "CAabc123", "faq", text)
    db.log_activity("voice", "CAdef456", "general", "another caller")
    assert db.get_stats_today()["calls"] == 2


def test_our_own_reminders_and_delivery_notes_are_not_customer_texts(db):
    db.log_activity("sms", "+15551234567", "faq", "customer text")
    db.log_activity("sms", "+15559876543", "reminder_appointment", "Sent reminder")
    db.log_activity("sms", "+18020000000", "delivery_failure", "Delivery failed")
    db.log_activity("sms", "+15550001111", "delivery_retry", "Retried")
    db.log_activity("email", "a@example.com", "email_bounce", "Bounce")
    s = db.get_stats_today()
    assert s["sms"] == 1


def test_a_failed_delivery_on_a_voice_row_is_not_a_call(db):
    db.log_activity("voice", "+15551230000", "delivery_failure", "Delivery failed for CA1")
    assert db.get_stats_today()["calls"] == 0


def test_only_a_successful_booking_counts_as_booked(db):
    db.log_activity("sms", "+15551234567", "appointment", "what date would you like?")      # a question
    db.log_activity("sms", "+15551234567", "appointment_booked", "Booked: check-up Tuesday") # the booking
    db.log_activity("sms", "+15559876543", "reminder_appointment", "Sent reminder")         # our reminder
    assert db.get_stats_today()["appointments"] == 1


def test_stats_are_still_per_organisation(db):
    db.log_activity("voice", "CA-1", "faq", "x", org_id=2)
    db.log_activity("voice", "CA-1", "faq", "y", org_id=2)
    db.log_activity("voice", "CA-2", "faq", "z", org_id=3)
    assert db.get_stats_today(org_id=2)["calls"] == 1
    assert db.get_stats_today(org_id=3)["calls"] == 1


def test_twilio_routes_log_a_real_booking_with_its_own_intent():
    from app.web_ui.twilio_routes import _activity_intent

    assert _activity_intent({"intent": "appointment", "booked": True}) == "appointment_booked"
    assert _activity_intent({"intent": "appointment", "booked": False}) == "appointment"
    assert _activity_intent({"intent": "faq"}) == "faq"
    assert _activity_intent({}) == ""
