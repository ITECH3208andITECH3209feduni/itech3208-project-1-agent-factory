# tests/test_memory.py — agent/memory.py (PROJ-354, PROJ-349 isolation)
import os
import tempfile

import pytest

from agent.memory import SessionMemory


@pytest.fixture
def mem():
    path = os.path.join(tempfile.mkdtemp(), "test_memory.db")
    return SessionMemory(db_path=path)


def test_add_and_get_history_own_session(mem):
    mem.add("best yoga mat", "amazon", "Found 3 great options", session_id="alice")
    history = mem.get_history(10, session_id="alice")
    assert len(history) == 1
    assert history[0]["query"] == "best yoga mat"
    assert history[0]["skill"] == "amazon"


def test_per_user_isolation(mem):
    mem.add("best yoga mat", "amazon", "Found 3 options", session_id="alice")
    mem.add("arxiv papers on transformers", "literature", "Found 5 papers", session_id="bob")
    mem.add("cheap headphones", "amazon", "Found budget picks", session_id="alice")

    alice_hist = mem.get_history(10, session_id="alice")
    bob_hist = mem.get_history(10, session_id="bob")

    assert len(alice_hist) == 2
    assert len(bob_hist) == 1
    assert all(h["query"] != "arxiv papers on transformers" for h in alice_hist)
    assert bob_hist[0]["query"] == "arxiv papers on transformers"


def test_context_string_does_not_leak_across_sessions(mem):
    mem.add("arxiv papers on transformers", "literature", "Found 5 papers", session_id="bob")
    ctx = mem.get_context_string(last_n=3, session_id="alice")
    assert "transformers" not in ctx
    assert ctx == "No previous queries."


def test_stats_scoped_to_session(mem):
    mem.add("q1", "amazon", "s1", session_id="alice")
    mem.add("q2", "amazon", "s2", session_id="alice")
    mem.add("q3", "amazon", "s3", session_id="bob")

    stats = mem.stats(session_id="alice")
    assert stats["history_count"] == 2


def test_all_sessions_true_returns_everything(mem):
    mem.add("q1", "amazon", "s1", session_id="alice")
    mem.add("q2", "literature", "s2", session_id="bob")

    all_hist = mem.get_history(10, all_sessions=True)
    assert len(all_hist) == 2


def test_get_last_context_scoped(mem):
    mem.add("first", "amazon", "sum1", session_id="alice")
    mem.add("second", "amazon", "sum2", session_id="alice")
    mem.add("other user", "amazon", "sum3", session_id="bob")

    last = mem.get_last_context(session_id="alice")
    assert last["query"] == "second"


def test_default_session_used_when_none_given(mem):
    """Backward-compat path for CLI usage (main.py) — no session_id
    means "this Orchestrator's own single session"."""
    mem.add("cli query", "amazon", "summary")
    history = mem.get_history(5)
    assert len(history) == 1
    assert history[0]["query"] == "cli query"


def test_clear_wipes_everything(mem):
    mem.add("q1", "amazon", "s1", session_id="alice")
    mem.clear()
    assert mem.get_history(10, all_sessions=True) == []
