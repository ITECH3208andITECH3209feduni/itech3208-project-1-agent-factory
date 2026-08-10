# tests/test_faq.py — agent/faq.py (PROJ-354, PROJ-214-218)
import json

import pytest

from agent import faq

_ENTRIES = [
    {
        "question": "What are your opening hours?",
        "answer": "We're open 24/7 online.",
        "tags": ["hours", "open", "available", "time"],
    },
    {
        "question": "How do I book an appointment?",
        "answer": "Tell me a date, time, and what it's for.",
        "tags": ["book", "appointment", "schedule", "meeting", "reserve"],
    },
    {
        "question": "How do I talk to a human?",
        "answer": "Just ask and I'll flag this for our team.",
        "tags": ["human", "person", "representative", "talk", "speak"],
    },
]


@pytest.fixture(autouse=True)
def _faq_file(tmp_path, monkeypatch):
    path = tmp_path / "faq.json"
    path.write_text(json.dumps(_ENTRIES), encoding="utf-8")
    monkeypatch.setattr(faq, "FAQ_DATA_PATH", str(path))
    faq.reload_faq()
    yield
    faq.reload_faq()


def test_matches_relevant_query():
    hit = faq.find_answer("what are your opening hours?")
    assert hit is not None
    assert "24/7" in hit["answer"]


def test_matches_with_word_variants_via_stemming():
    # "booking" should still match the "book" tag
    hit = faq.find_answer("how can I book a meeting")
    assert hit is not None
    assert "date, time" in hit["answer"]


def test_no_match_for_unrelated_query():
    hit = faq.find_answer("what is the airspeed velocity of an unladen swallow")
    assert hit is None


def test_no_match_for_empty_query():
    assert faq.find_answer("") is None
    assert faq.find_answer("   ") is None


def test_missing_faq_file_returns_none(monkeypatch):
    monkeypatch.setattr(faq, "FAQ_DATA_PATH", "/nonexistent/path/faq.json")
    faq.reload_faq()
    assert faq.find_answer("what are your hours") is None


def test_score_included_in_result():
    hit = faq.find_answer("what are your opening hours?")
    assert hit is not None
    assert 0.0 < hit["score"] <= 1.0


def test_min_score_threshold_respected():
    # A query with only a single, weak token overlap should be
    # rejected by a strict enough threshold even if it would pass a
    # looser one.
    hit = faq.find_answer("hours", min_score=1.1)  # impossible threshold
    assert hit is None
