"""PROJ-478 (brief Part D1): answer side questions without losing the booking."""

import time
from pathlib import Path

import pytest

import agent.memory as memory_module
import agent.receptionist as receptionist_module
from agent import faq
from agent.receptionist import Receptionist

CLARIFY = "What date and time would you like, and what's the appointment for?"


@pytest.fixture
def receptionist(tmp_path, monkeypatch, fake_anthropic_reply):
    """Real seed FAQ, stubbed calendar and extractor, isolated memory."""
    seed = Path(__file__).resolve().parent.parent / "config" / "faq_seed.json"
    monkeypatch.setattr("agent.faq.FAQ_DATA_PATH", str(seed))
    faq.reload_faq()

    monkeypatch.setattr(receptionist_module, "ESCALATION_LOG", str(tmp_path / "esc.jsonl"))
    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    booked = []

    def fake_book(summary, start_iso, end_iso, timezone):
        booked.append((summary, start_iso))
        return {"ok": True, "event_url": None}

    monkeypatch.setattr(receptionist_module, "book_appointment", fake_book)
    monkeypatch.setattr(receptionist_module, "create_reminder_for_booking", lambda **kw: {"ok": True})

    r = Receptionist()
    r.memory = memory_module.SessionMemory(db_path=str(tmp_path / "memory.db"))
    r.booked = booked
    r.extract_inputs = []

    def fake_extract(message):
        r.extract_inputs.append(message)
        if "friday" in message.lower():
            return {"summary": "Consultation", "start": "2026-10-16T10:00:00", "end": "2026-10-16T10:30:00", "clarify": None}
        return {"clarify": CLARIFY}

    r._extract_appointment = fake_extract
    yield r
    faq.reload_faq()


def test_three_side_questions_then_the_booking_completes(receptionist):
    sid = "caller-1"

    first = receptionist.handle("I'd like to book a consultation", session_id=sid)
    assert first["intent"] == "appointment" and first["needs_info"] is True

    parking = receptionist.handle("where can I park?", session_id=sid)
    cost = receptionist.handle("is it free?", session_id=sid)
    prep = receptionist.handle("what should I bring?", session_id=sid)

    answers = [parking, cost, prep]
    assert all(a["intent"] == "faq" for a in answers)
    assert len({a["answer"].split("\n")[0] for a in answers}) == 3, "three distinct FAQ answers"
    assert all(a["booking_pending"] for a in answers)
    assert all(CLARIFY in a["answer"] for a in answers), "each answer steers back to the booking"
    assert receptionist.booked == [], "no booking yet"

    done = receptionist.handle("Friday at 10am for the consultation", session_id=sid)
    assert done["intent"] == "appointment" and done["booked"] is True
    assert receptionist.booked == [("Consultation", "2026-10-16T10:00:00")]
    # the earlier request and the new details were extracted together
    assert "book a consultation" in receptionist.extract_inputs[-1]
    assert "Friday at 10am" in receptionist.extract_inputs[-1]


def test_faq_without_a_booking_in_progress_is_unchanged(receptionist):
    out = receptionist.handle("where can I park?", session_id="x")
    assert out["intent"] == "faq" and "booking_pending" not in out
    assert "finish your booking" not in out["answer"]


def test_never_mind_drops_the_pending_booking(receptionist):
    sid = "caller-2"
    receptionist.handle("I'd like to book a consultation", session_id=sid)
    out = receptionist.handle("actually never mind", session_id=sid)
    assert "dropped that booking" in out["answer"]
    assert receptionist._get_pending(sid) is None
    after = receptionist.handle("where can I park?", session_id=sid)
    assert "booking_pending" not in after


def test_pending_booking_expires(receptionist, monkeypatch):
    sid = "caller-3"
    receptionist.handle("I'd like to book a consultation", session_id=sid)
    receptionist._pending_bookings[sid]["ts"] = time.time() - 60 * 60
    assert receptionist._get_pending(sid) is None


def test_bookings_are_per_session(receptionist):
    receptionist.handle("I'd like to book a consultation", session_id="a")
    assert receptionist._get_pending("b") is None
    out = receptionist.handle("where can I park?", session_id="b")
    assert "booking_pending" not in out


def test_asking_for_a_human_clears_the_pending_booking(receptionist):
    sid = "caller-4"
    receptionist.handle("I'd like to book a consultation", session_id=sid)
    out = receptionist.handle("I want to talk to a person", session_id=sid)
    assert out["intent"] == "escalate"
    assert receptionist._get_pending(sid) is None
