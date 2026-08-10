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
        lambda summary, start_iso, end_iso, timezone: {
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
        lambda summary, start_iso, end_iso, timezone: {
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
