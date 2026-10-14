"""MyAI answers how-do-I questions about the dashboard from config/dashboard_help.json."""

import json

import pytest
from fastapi.testclient import TestClient

from agent import dashboard_help


@pytest.fixture(autouse=True)
def no_claude(monkeypatch):
    monkeypatch.setattr(dashboard_help, "ANTHROPIC_API_KEY", "")


@pytest.mark.parametrize(
    "question, topic_start",
    [
        ("How do I add a contact?", "How do I add a contact"),
        ("how can I import my patients from a spreadsheet", "How do I import many contacts"),
        ("what does opted out mean", "What do the consent states mean"),
        ("why did my reminder not send", "Why was my reminder blocked"),
        ("why didn't my reminder send", "Why was my reminder blocked"),
        ("how do I make a reminder repeat every week", "How do I make a reminder repeat"),
        ("how do I pause a reminder", "How do I edit, pause"),
        ("what are merge fields in templates", "What are message templates"),
        ("how do I send a message right now", "How do I send a message right now"),
        ("what does bounced mean", "What does Delivery History show"),
        ("why does email say sent but not delivered", "Why does an email say sent"),
        ("what does the escalations tab do", "What are escalations"),
        ("where do I see appointments", "How do I see appointments"),
        ("how do I change the language", "How do I change the language"),
        ("how do I switch to light theme", "How do I change the theme"),
        ("is my data kept after restart", "Where is my data stored"),
    ],
)
def test_common_questions_find_the_right_topic(question, topic_start):
    result = dashboard_help.answer(question)
    assert result["intent"] == "help"
    assert result.get("topic", "").startswith(topic_start), result


def test_every_topic_is_found_by_its_own_question():
    for entry in json.load(open(dashboard_help.HELP_PATH, encoding="utf-8")):
        assert dashboard_help.answer(entry["question"]).get("topic") == entry["question"]


def test_unknown_question_without_a_key_suggests_topics():
    result = dashboard_help.answer("what is the airspeed of a swallow")
    assert "not sure" in result["answer"] and "How is the dashboard laid out" in result["answer"]


def test_unknown_question_uses_claude_when_available():
    class Reply:
        content = [type("T", (), {"text": "Open the Reminders tab."})()]

    class Client:
        class messages:
            @staticmethod
            def create(**kwargs):
                assert "HELP TOPICS" in kwargs["system"]
                return Reply()

    result = dashboard_help.answer("what is the airspeed of a swallow", client=Client())
    assert result["answer"] == "Open the Reminders tab."


def test_claude_failure_falls_back_to_the_topic_list():
    class Client:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("down")

    assert "not sure" in dashboard_help.answer("zzz qqq", client=Client())["answer"]


def test_empty_message_gets_a_prompt():
    assert "How do I add a contact" in dashboard_help.answer("  ")["answer"]


def test_endpoint_requires_login_and_answers():
    from app.web_ui.main import app

    anonymous = TestClient(app)
    anonymous.cookies.clear()
    assert anonymous.post("/myai", json={"message": "hi"}).status_code == 401

    signed_in = TestClient(app)  # conftest gives every client a session
    r = signed_in.post("/myai", json={"message": "How do I add a contact?"})
    assert r.status_code == 200 and "New contact" in r.json()["answer"]
