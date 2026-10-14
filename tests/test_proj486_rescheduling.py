from types import SimpleNamespace
import json

from agent import receptionist as receptionist_module
from agent.receptionist import Receptionist


def make_receptionist(extracted):
    receptionist = Receptionist.__new__(Receptionist)

    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                content=[SimpleNamespace(text=json.dumps(extracted))]
            )

    receptionist.client = SimpleNamespace(messages=FakeMessages())
    receptionist._pending_reschedules = {}
    return receptionist


def example_event(event_id="event-123", summary="Dental review"):
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": "2026-10-20T14:00:00+11:00"},
        "end": {"dateTime": "2026-10-20T14:30:00+11:00"},
    }


def test_reschedule_detects_natural_language_request():
    assert Receptionist._wants_reschedule(
        "I can't do Tuesday, what about Friday morning?"
    )
    assert Receptionist._wants_reschedule("Please reschedule my appointment")
    assert not Receptionist._wants_reschedule("What are your opening hours?")


def test_reschedule_reports_when_no_existing_booking_is_found(monkeypatch):
    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "find_upcoming_appointments",
        lambda channel, address: {"ok": True, "events": []},
    )

    receptionist = make_receptionist(
        {"start": "2026-10-23T10:00:00", "clarify": None}
    )
    result = receptionist._handle_reschedule(
        "Move my appointment to Friday at 10",
        "test-session",
        "sms",
        "+61400000000",
    )

    assert result["intent"] == "reschedule"
    assert result["rescheduled"] is False
    assert "couldn't find" in result["answer"].lower()


def test_reschedule_asks_which_booking_when_multiple_match(monkeypatch):
    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "find_upcoming_appointments",
        lambda channel, address: {
            "ok": True,
            "events": [
                example_event("event-1", "Dental review"),
                example_event("event-2", "General consultation"),
            ],
        },
    )

    receptionist = make_receptionist(
        {"start": "2026-10-23T10:00:00", "clarify": None}
    )
    result = receptionist._handle_reschedule(
        "Please move my appointment to Friday at 10",
        "test-session",
        "sms",
        "+61400000000",
    )

    assert result["rescheduled"] is False
    assert result["needs_info"] is True
    assert "which one" in result["answer"].lower()


def test_reschedule_updates_existing_event_and_linked_reminder(monkeypatch):
    event = example_event()
    calls = {}

    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "find_upcoming_appointments",
        lambda channel, address: {"ok": True, "events": [event]},
    )

    def fake_update(**kwargs):
        calls["calendar"] = kwargs
        return {
            "ok": True,
            "event_id": "event-123",
            "event_url": "https://calendar.google.com/event?id=event-123",
        }

    def fake_reminder(**kwargs):
        calls["reminder"] = kwargs
        return {"ok": True, "updated": 1}

    monkeypatch.setattr(receptionist_module, "update_appointment", fake_update)
    monkeypatch.setattr(
        receptionist_module,
        "reschedule_reminders_for_booking",
        fake_reminder,
    )

    receptionist = make_receptionist(
        {"start": "2026-10-23T10:00:00", "clarify": None}
    )
    result = receptionist._handle_reschedule(
        "Move my dental review to Friday at 10",
        "test-session",
        "sms",
        "+61400000000",
    )

    assert result["rescheduled"] is True
    assert calls["calendar"]["event_id"] == "event-123"
    assert calls["calendar"]["start_iso"] == "2026-10-23T10:00:00"
    assert calls["reminder"]["booking_id"] == "event-123"
    assert result["reminders_updated"] == 1


def test_unclear_reschedule_time_does_not_move_event(monkeypatch):
    event = example_event()
    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "find_upcoming_appointments",
        lambda channel, address: {"ok": True, "events": [event]},
    )

    def must_not_update(**kwargs):
        raise AssertionError("An unclear time must not update the calendar")

    monkeypatch.setattr(receptionist_module, "update_appointment", must_not_update)

    receptionist = make_receptionist(
        {"start": None, "clarify": "What time on Friday would suit you?"}
    )
    result = receptionist._handle_reschedule(
        "Move my appointment to Friday morning",
        "test-session",
        "sms",
        "+61400000000",
    )

    assert result["rescheduled"] is False
    assert result["needs_info"] is True
    assert "what time" in result["answer"].lower()



def test_reschedule_keeps_original_time_request_after_clarification(monkeypatch):
    event = example_event()
    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "find_upcoming_appointments",
        lambda channel, address: {"ok": True, "events": [event]},
    )
    monkeypatch.setattr(
        receptionist_module,
        "update_appointment",
        lambda **kwargs: {"ok": True, "event_id": "event-123"},
    )
    monkeypatch.setattr(
        receptionist_module,
        "reschedule_reminders_for_booking",
        lambda **kwargs: {"ok": True, "updated": 1},
    )

    receptionist = make_receptionist(
        {"start": None, "clarify": "What time on Friday would suit you?"}
    )
    extracted_messages = []

    def fake_extract(message, selected_event):
        extracted_messages.append(message)
        if len(extracted_messages) == 1:
            return {"clarify": "What time on Friday would suit you?"}
        return {"start": "2026-10-23T10:00:00", "clarify": None}

    receptionist._extract_reschedule_start = fake_extract

    first = receptionist._handle_reschedule(
        "Move my dental review to Friday morning",
        "test-session",
        "sms",
        "+61400000000",
    )
    assert first["needs_info"] is True

    second = receptionist._handle_reschedule(
        "10 AM",
        "test-session",
        "sms",
        "+61400000000",
    )

    assert second["rescheduled"] is True
    assert "Friday morning" in extracted_messages[1]
    assert "10 AM" in extracted_messages[1]
