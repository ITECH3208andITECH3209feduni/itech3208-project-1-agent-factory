# tests/test_orchestrator.py — agent/orchestrator.py (PROJ-354)
import pytest

from agent.orchestrator import Orchestrator
from agent.memory import SessionMemory


@pytest.fixture
def orchestrator(tmp_path, fake_anthropic_reply):
    o = Orchestrator()
    o.memory = SessionMemory(db_path=str(tmp_path / "memory.db"))
    return o


def test_quick_route_amazon_keywords(orchestrator):
    assert orchestrator._quick_route("what's the best price for wireless earbuds") == "amazon"


def test_quick_route_literature_keywords(orchestrator):
    assert orchestrator._quick_route("find me a research paper on arxiv about transformers") == "literature"


def test_quick_route_ambiguous_falls_through_to_none(orchestrator):
    assert orchestrator._quick_route("hello") is None


def test_route_uses_quick_route_before_calling_claude(orchestrator, monkeypatch):
    """If the keyword pre-check resolves the intent, Claude shouldn't
    even be called — saves an API call for obvious queries."""
    called = {"count": 0}

    def _should_not_be_called(**kwargs):
        called["count"] += 1
        raise AssertionError("Claude should not have been called")

    monkeypatch.setattr(orchestrator.client.messages, "create", _should_not_be_called)
    result = orchestrator._route("best cheap deal on a laptop")
    assert result == "amazon"
    assert called["count"] == 0


def test_route_falls_back_to_claude_for_ambiguous_query(orchestrator, fake_anthropic_reply):
    fake_anthropic_reply("SKILL: literature")
    result = orchestrator._route("tell me about quantum entanglement")
    assert result == "literature"


def test_route_passes_through_clarification(orchestrator, fake_anthropic_reply):
    fake_anthropic_reply("CLARIFY: Could you be more specific about what you're looking for?")
    result = orchestrator._route("something")
    assert result.startswith("CLARIFY:")


def test_run_persists_to_memory_scoped_by_session(orchestrator, fake_anthropic_reply, monkeypatch):
    # Force routing to a known skill and stub the skill itself so we're
    # only testing the orchestrator's persistence wiring, not the real
    # Amazon scraper.
    from skills.base_skill import SkillResult

    def _fake_run(query):
        return SkillResult(skill_name="amazon", query=query, success=True, results=[], summary="Test summary")

    # Patch .run(), not .__call__ — Python resolves the () operator via
    # the class's __call__ (BaseSkill.__call__), which internally does
    # `self.run(query)`; that's a normal attribute lookup and picks up
    # an instance-level monkeypatch, but the special-method () lookup
    # itself would NOT see an instance-level __call__ override.
    monkeypatch.setattr(orchestrator.skills["amazon"], "run", _fake_run)
    orchestrator.run("best cheap laptop deal", session_id="alice")

    history = orchestrator.memory.get_history(5, session_id="alice")
    assert len(history) == 1
    assert history[0]["query"] == "best cheap laptop deal"
