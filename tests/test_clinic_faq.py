"""The clinic demo answers like a dental clinic, including the four quick-prompt buttons."""

import json
import os

import pytest

from agent import faq

_CLINIC = os.path.join(os.path.dirname(__file__), "..", "config", "faq_clinic.json")


@pytest.fixture(autouse=True)
def clinic_file(monkeypatch):
    monkeypatch.setattr(faq, "FAQ_DATA_PATH", _CLINIC)
    faq.reload_faq()
    yield
    faq.reload_faq()


@pytest.mark.parametrize(
    "question, expected",
    [
        ("What are your opening hours?", "Saturday"),
        ("What services do you offer?", "whitening"),
        ("How do I get in touch?", "number on your reminder"),
        ("I have a toothache, what do I do?", "000"),
        ("Do you see kids?", "children"),
        ("how much does a check up cost", "private health"),
        ("how do I reschedule my appointment", "reschedule my appointment"),
    ],
)
def test_clinic_questions_get_clinic_answers(question, expected):
    answer = faq.find_answer(question)
    assert answer and expected.lower() in (answer if isinstance(answer, str) else json.dumps(answer)).lower()


def test_no_trace_of_the_research_product_in_clinic_answers():
    text = open(_CLINIC, encoding="utf-8").read().lower()
    assert "agent factory" not in text and "amazon" not in text and "literature" not in text
