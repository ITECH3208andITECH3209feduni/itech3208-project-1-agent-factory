# tests/conftest.py
# ──────────────────────────────────────────────────────────────
# Shared pytest fixtures (PROJ-354-363).
#
# IMPORTANT: env vars here are set at module import time, BEFORE any
# `agent.*` / `app.*` module is imported anywhere in the test session.
# config/settings.py reads MEMORY_DB, AUTH_DB, FAQ_DATA_PATH, and
# ESCALATION_LOG from the environment (falling back to real
# outputs/... paths otherwise) specifically so tests can redirect them
# here — without this, importing app.web_ui.routes (which constructs a
# module-level Orchestrator() on import) would write straight into
# your real outputs/memory.db and outputs/auth.db.
# ──────────────────────────────────────────────────────────────

import json
import os
import tempfile

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="agent_factory_test_")

os.environ.setdefault("MEMORY_DB", os.path.join(_TEST_DATA_DIR, "memory.db"))
os.environ.setdefault("AUTH_DB", os.path.join(_TEST_DATA_DIR, "auth.db"))
os.environ.setdefault("FAQ_DATA_PATH", os.path.join(_TEST_DATA_DIR, "faq_seed.json"))
os.environ.setdefault("ESCALATION_LOG", os.path.join(_TEST_DATA_DIR, "escalations.jsonl"))
os.environ.setdefault("KB_DB", os.path.join(_TEST_DATA_DIR, "kb.db"))
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-a-real-key")
# Empty by default so calendar_client.is_configured() is False unless a
# specific test opts in via the google_calendar_configured fixture.
os.environ.setdefault("GOOGLE_CALENDAR_KEY_PATH", "")
os.environ.setdefault("GOOGLE_CALENDAR_ID", "")

_SEED_FAQ = [
    {
        "question": "What are your hours?",
        "answer": "We're open 24/7 online.",
        "tags": ["hours", "open", "available"],
    },
    {
        "question": "How do I book an appointment?",
        "answer": "Tell me a date, time, and what it's for.",
        "tags": ["book", "appointment", "schedule"],
    },
]
with open(os.environ["FAQ_DATA_PATH"], "w", encoding="utf-8") as _fh:
    json.dump(_SEED_FAQ, _fh)


import pytest  # noqa: E402  (import after env setup is intentional)


@pytest.fixture(autouse=True)
def _isolate_faq_cache():
    """agent/faq.py caches the parsed JSON in a module-level variable.
    Reset it around every test so tests that write a different FAQ
    file (via monkeypatching FAQ_DATA_PATH) don't see stale results
    from a previous test."""
    from agent import faq

    faq.reload_faq()
    yield
    faq.reload_faq()


@pytest.fixture
def fake_anthropic_reply(monkeypatch):
    """Patch anthropic.Anthropic so any code that calls
    self.client.messages.create(...) gets a canned text response
    instead of hitting the real API. Returns a setter you call with
    the text you want back; defaults to a generic reply."""
    import anthropic

    class _FakeContent:
        def __init__(self, text):
            self.text = text

    class _FakeMessage:
        def __init__(self, text):
            self.content = [_FakeContent(text)]

    class _FakeMessages:
        def __init__(self, holder):
            self._holder = holder

        def create(self, **kwargs):
            return _FakeMessage(self._holder["text"])

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _FakeMessages(holder)

    holder = {"text": "This is a test reply."}
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)

    def _set_reply(text):
        holder["text"] = text

    _set_reply.holder = holder
    return _set_reply
