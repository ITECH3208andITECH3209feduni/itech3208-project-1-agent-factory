"""Post-call summary, sentiment and priority (PROJ-477, brief Part D3)."""

import json
from types import SimpleNamespace

import pytest

from agent import call_summary
from agent.memory import SessionMemory


class StubClient:
    """Stands in for anthropic.Anthropic; returns canned text or raises."""

    def __init__(self, text=None, error=None):
        self._text, self._error, self.calls = text, error, 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        if self._error:
            raise self._error
        return SimpleNamespace(content=[SimpleNamespace(text=self._text)])


def turn(query, skill="receptionist_general", reply="ok"):
    return {"query": query, "skill": skill, "summary": reply}


# ── Model path ─────────────────────────────────────────────────

def test_model_result_is_used_and_cleaned():
    client = StubClient(json.dumps({"summary": "Caller booked a check-up.", "sentiment": "positive", "priority": "normal"}))
    out = call_summary.summarise_call([turn("book me in thursday")], client=client)
    assert out == {"summary": "Caller booked a check-up.", "sentiment": "positive", "priority": "normal"}


def test_model_json_in_code_fence_is_accepted():
    body = '```json\n{"summary": "Asked about parking.", "sentiment": "neutral", "priority": "low"}\n```'
    out = call_summary.summarise_call([turn("where do I park")], client=StubClient(body))
    assert out["priority"] == "low" and out["summary"] == "Asked about parking."


def test_invalid_labels_fall_back_to_heuristic_values():
    client = StubClient(json.dumps({"summary": "x", "sentiment": "ecstatic", "priority": "p0"}))
    out = call_summary.summarise_call([turn("hello")], client=client)
    assert out["sentiment"] in call_summary.SENTIMENTS and out["priority"] in call_summary.PRIORITIES


def test_model_error_falls_back_to_heuristic():
    out = call_summary.summarise_call([turn("this is a terrible service, I want a refund")], client=StubClient(error=RuntimeError("down")))
    assert out["sentiment"] == "negative" and out["priority"] == "high"


def test_garbage_model_output_falls_back():
    out = call_summary.summarise_call([turn("thanks, that's great")], client=StubClient("not json at all"))
    assert out["sentiment"] == "positive"


def test_escalation_forces_high_priority_even_if_model_says_low():
    client = StubClient(json.dumps({"summary": "Wanted a person.", "sentiment": "neutral", "priority": "low"}))
    out = call_summary.summarise_call([turn("let me talk to a person", skill="receptionist_escalate")], client=client)
    assert out["priority"] == "high"


# ── Heuristic ──────────────────────────────────────────────────

def test_heuristic_simple_faq_is_low_priority_neutral():
    out = call_summary.heuristic_summary([turn("what are your hours", skill="receptionist_faq")])
    assert (out["sentiment"], out["priority"]) == ("neutral", "low")


def test_heuristic_urgent_is_high():
    assert call_summary.heuristic_summary([turn("it's an emergency, I need to be seen today")])["priority"] == "high"


def test_no_turns_gives_a_safe_default():
    out = call_summary.summarise_call([], client=StubClient("{}"))
    assert out["summary"] and out["sentiment"] == "neutral"


# ── Storage and dashboard feed ─────────────────────────────────

@pytest.fixture
def stores(tmp_path, monkeypatch):
    from app.web_ui import activity_db

    monkeypatch.setattr(activity_db, "MEMORY_DB", str(tmp_path / "activity.db"))
    monkeypatch.setattr(activity_db, "_db", None)
    memory = SessionMemory(db_path=str(tmp_path / "memory.db"))
    yield activity_db, memory
    if activity_db._db is not None:
        activity_db._db.close()
    monkeypatch.setattr(activity_db, "_db", None)


def test_finalize_call_stores_once(stores):
    activity_db, memory = stores
    memory.save_context("book me in", "receptionist_appointment", "Booked.", session_id="CA1")
    client = StubClient(json.dumps({"summary": "Booked an appointment.", "sentiment": "positive", "priority": "normal"}))

    first = call_summary.finalize_call("CA1", "+15555550101", memory, client=client)
    second = call_summary.finalize_call("CA1", "+15555550101", memory, client=client)

    assert first["priority"] == "normal"
    assert second is None and client.calls == 1
    assert activity_db.get_call_summary("CA1")["summary"] == "Booked an appointment."


def test_finalize_call_with_no_transcript_does_nothing(stores):
    _, memory = stores
    assert call_summary.finalize_call("CA404", "x", memory, client=StubClient("{}")) is None


def test_feed_collapses_a_summarised_call_into_one_tagged_row(stores):
    activity_db, _ = stores
    for text in ("turn one", "turn two", "turn three"):
        activity_db.log_activity("voice", "CA9", "faq", text)
    activity_db.log_activity("sms", "+15555550102", "general", "a text")
    activity_db.save_call_summary("CA9", "+15555550101", "Caller asked about hours.", "positive", "low", 3)

    feed = activity_db.get_recent(10)
    calls = [r for r in feed if r["channel"] == "voice"]

    assert len(calls) == 1
    assert calls[0]["summary"] == "Caller asked about hours."
    assert (calls[0]["sentiment"], calls[0]["priority"], calls[0]["call_summary"]) == ("positive", "low", True)
    assert any(r["channel"] == "sms" for r in feed)


def test_feed_keeps_turn_rows_for_calls_still_in_progress(stores):
    activity_db, _ = stores
    activity_db.log_activity("voice", "CA_LIVE", "faq", "turn one")
    activity_db.log_activity("voice", "CA_LIVE", "faq", "turn two")
    rows = [r for r in activity_db.get_recent(10) if r["channel"] == "voice"]
    assert len(rows) == 2 and not any(r.get("call_summary") for r in rows)
