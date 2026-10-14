# tests/test_receptionist.py — agent/receptionist.py (PROJ-354, PROJ-209-218)
import json

import pytest

from agent.receptionist import Receptionist


@pytest.fixture
def receptionist(tmp_path, monkeypatch, fake_anthropic_reply):
    """Fresh Receptionist per test: isolated memory DB, isolated FAQ
    file (empty — so FAQ never intercepts the intent-routing tests
    below), isolated escalation log, calendar left unconfigured."""
    import agent.receptionist as receptionist_module
    import agent.memory as memory_module

    faq_path = tmp_path / "empty_faq.json"
    faq_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("agent.faq.FAQ_DATA_PATH", str(faq_path))
    from agent import faq

    faq.reload_faq()

    escalation_log = tmp_path / "escalations.jsonl"
    monkeypatch.setattr(receptionist_module, "ESCALATION_LOG", str(escalation_log))

    r = Receptionist()
    r.memory = memory_module.SessionMemory(db_path=str(tmp_path / "memory.db"))
    return r


def test_escalation_intent_logs_and_replies(receptionist, tmp_path):
    result = receptionist.handle("I'd like to talk to a human please", session_id="alice")
    assert result["intent"] == "escalate"
    assert "flagged" in result["answer"].lower()

    import agent.receptionist as receptionist_module

    with open(receptionist_module.ESCALATION_LOG, encoding="utf-8") as fh:
        lines = fh.readlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["session_id"] == "alice"


def test_appointment_intent_without_calendar_configured(receptionist):
    result = receptionist.handle(
        "book me in for a consultation next Tuesday at 2pm", session_id="alice"
    )
    assert result["intent"] == "appointment"
    assert result["booked"] is False
    assert "isn't set up" in result["answer"] or "not" in result["answer"].lower()


def test_general_conversation_fallback(receptionist, fake_anthropic_reply):
    fake_anthropic_reply("Hi! How can I help you today?")
    result = receptionist.handle("hello there", session_id="alice")
    assert result["intent"] == "general"
    assert result["answer"] == "Hi! How can I help you today?"


def test_faq_takes_priority_over_appointment_keywords(receptionist, tmp_path, monkeypatch):
    """PROJ-214 spec: FAQ lookup happens before skill/intent routing."""
    faq_entries = [
        {
            "question": "How do I book an appointment?",
            "answer": "FAQ ANSWER: just tell me a date and time.",
            "tags": ["book", "appointment", "schedule"],
        }
    ]
    faq_path = tmp_path / "faq_with_booking.json"
    faq_path.write_text(json.dumps(faq_entries), encoding="utf-8")
    monkeypatch.setattr("agent.faq.FAQ_DATA_PATH", str(faq_path))
    from agent import faq

    faq.reload_faq()

    result = receptionist.handle("how do I book an appointment", session_id="alice")
    assert result["intent"] == "faq"
    assert "FAQ ANSWER" in result["answer"]


def test_empty_message_handled_gracefully(receptionist):
    result = receptionist.handle("", session_id="alice")
    assert result["intent"] == "general"
    assert result["answer"]


def test_history_persisted_after_general_reply(receptionist, fake_anthropic_reply):
    fake_anthropic_reply("Sure thing!")
    receptionist.handle("what's up", session_id="alice")
    history = receptionist.memory.get_history(5, session_id="alice")
    assert len(history) == 1
    assert history[0]["query"] == "what's up"


def test_appointment_booking_failure_includes_ics_fallback_link(
    receptionist, fake_anthropic_reply, monkeypatch
):
    """PROJ-294-298: even if Google Calendar booking fails (or a user
    doesn't use Google at all), they should still get an .ics download
    link so they can add the appointment to their own calendar."""
    import agent.receptionist as receptionist_module
    import json as _json

    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "book_appointment",
        lambda summary, start_iso, end_iso, timezone, **kwargs: {
            "ok": False,
            "error": "Calendar API error 403: forbidden",
        },
    )
    fake_anthropic_reply(
        _json.dumps(
            {
                "summary": "Consultation",
                "start": "2026-08-11T14:00:00",
                "end": "2026-08-11T14:30:00",
                "clarify": None,
            }
        )
    )

    result = receptionist.handle(
        "book me in for a consultation next tuesday at 2pm", session_id="alice"
    )
    assert result["intent"] == "appointment"
    assert result["booked"] is False
    assert "/calendar/ics?" in result["answer"]
    assert "summary=Consultation" in result["answer"]


def test_appointment_booking_success_also_includes_ics_link(
    receptionist, fake_anthropic_reply, monkeypatch
):
    import agent.receptionist as receptionist_module
    import json as _json

    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "book_appointment",
        lambda summary, start_iso, end_iso, timezone, **kwargs: {
            "ok": True,
            "event_url": "https://calendar.google.com/event?eid=xyz",
        },
    )
    fake_anthropic_reply(
        _json.dumps(
            {
                "summary": "Consultation",
                "start": "2026-08-11T14:00:00",
                "end": "2026-08-11T14:30:00",
                "clarify": None,
            }
        )
    )

    result = receptionist.handle(
        "book me in for a consultation next tuesday at 2pm", session_id="alice"
    )
    assert result["booked"] is True
    assert "/calendar/ics?" in result["answer"]
    assert "View event" in result["answer"]


def test_appointment_booking_success_schedules_reminder_when_contact_known(
    receptionist, fake_anthropic_reply, monkeypatch, tmp_path
):
    """PROJ-445/446: when the caller passes contact_channel/contact_address
    (Twilio always knows the caller's number), a successful booking
    also schedules a reminder ahead of the appointment."""
    import agent.receptionist as receptionist_module
    from agent.reminders.store import ReminderStore
    import json as _json

    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "book_appointment",
        lambda summary, start_iso, end_iso, timezone, **kwargs: {
            "ok": True,
            "event_url": "https://calendar.google.com/event?eid=xyz",
        },
    )
    test_store = ReminderStore(db_path=str(tmp_path / "reminders.db"))
    monkeypatch.setattr(
        "agent.reminders.booking_hooks.ReminderStore", lambda: test_store
    )
    fake_anthropic_reply(
        _json.dumps(
            {
                "summary": "Consultation",
                "start": "2026-08-11T14:00:00",
                "end": "2026-08-11T14:30:00",
                "clarify": None,
            }
        )
    )

    result = receptionist.handle(
        "book me in for a consultation next tuesday at 2pm",
        session_id="alice",
        contact_channel="sms",
        contact_address="+15551234567",
    )
    assert result["booked"] is True
    assert "reminder" in result["answer"].lower()

    due = test_store._conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
    assert due == 1


def test_appointment_booking_success_without_contact_info_skips_reminder(
    receptionist, fake_anthropic_reply, monkeypatch
):
    """No contact_channel/contact_address passed (e.g. the web chat
    tab, which has no phone/email on hand) — booking still succeeds,
    just without an auto-reminder."""
    import agent.receptionist as receptionist_module
    import json as _json

    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(
        receptionist_module,
        "book_appointment",
        lambda summary, start_iso, end_iso, timezone, **kwargs: {"ok": True, "event_url": None},
    )
    fake_anthropic_reply(
        _json.dumps(
            {
                "summary": "Consultation",
                "start": "2026-08-11T14:00:00",
                "end": "2026-08-11T14:30:00",
                "clarify": None,
            }
        )
    )

    result = receptionist.handle(
        "book me in for a consultation next tuesday at 2pm", session_id="alice"
    )
    assert result["booked"] is True
    assert "reminder" not in result["answer"].lower()


def _log(receptionist_module):
    with open(receptionist_module.ESCALATION_LOG, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def test_emergency_is_flagged_urgent_even_with_a_faq_present(receptionist, tmp_path, monkeypatch):
    import agent.receptionist as module
    from agent import faq

    path = tmp_path / "faq.json"
    path.write_text(json.dumps([{"question": "Do you handle dental emergencies?", "answer": "faq text",
                                 "tags": ["emergency", "urgent", "toothache"]}]), encoding="utf-8")
    monkeypatch.setattr("agent.faq.FAQ_DATA_PATH", str(path))
    faq.reload_faq()

    result = receptionist.handle("I have a terrible toothache", session_id="bob")
    assert result["intent"] == "escalate" and result["urgent"] is True
    assert "000" in result["answer"]
    row = _log(module)[0]
    assert row["priority"] == "high" and row["reason"].startswith("URGENT:")


def test_emergency_booking_still_tries_to_book_and_is_flagged(receptionist):
    import agent.receptionist as module

    result = receptionist.handle("create me an emergency booking for today at 3pm", session_id="bob")
    assert result["intent"] == "appointment" and result["urgent"] is True
    assert result["answer"].startswith("I'm sorry")
    assert _log(module)[0]["priority"] == "high"


def test_not_urgent_is_not_flagged(receptionist):
    import agent.receptionist as module

    receptionist.handle("it's not urgent, just a check-up", session_id="bob")
    assert not _log_exists(module)


def _log_exists(module):
    import os

    return os.path.exists(module.ESCALATION_LOG)


def test_callback_by_text_uses_the_callers_own_number(receptionist):
    import agent.receptionist as module

    result = receptionist.handle(
        "can you book me a call back", session_id="s1", contact_channel="sms", contact_address="+15551234567"
    )
    assert result["intent"] == "escalate" and "+15551234567" in result["answer"]
    row = _log(module)[0]
    assert row["reason"].startswith("CALL BACK:") and row["contact"] == "+15551234567"


def test_callback_in_web_chat_asks_for_a_number_then_logs_it(receptionist):
    import agent.receptionist as module

    first = receptionist.handle("please call me back", session_id="web1")
    assert first["intent"] == "escalate" and "what number" in first["answer"].lower()
    assert not _log_exists(module)

    second = receptionist.handle("0412 345 678", session_id="web1")
    assert second["intent"] == "escalate" and "0412 345 678" in second["answer"]
    assert _log(module)[0]["contact"] == "0412 345 678"


def test_clinic_mode_uses_a_dental_prompt(monkeypatch):
    from agent.receptionist import _system_prompt

    monkeypatch.setenv("BRAND_MODE", "clinic")
    monkeypatch.setenv("BRAND_NAME", "Bright Smile Dental")
    prompt = _system_prompt()
    assert "Bright Smile Dental" in prompt and "Amazon" not in prompt and "never diagnose" in prompt

    monkeypatch.delenv("BRAND_MODE")
    assert "Agent Factory" in _system_prompt()
