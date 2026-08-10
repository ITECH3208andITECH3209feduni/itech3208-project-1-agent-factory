# tests/test_integrity.py — Integrity Check backend + 40-sample
# curated corpus validation (PROJ-364-368).
#
# See agent/integrity.py's module docstring and
# tests/data/integrity_corpus.py's header for the honest scope note:
# this validates the heuristic behaves as designed, not real-world
# AI-detection accuracy against unseen text (no such claim is made
# anywhere in this suite).
# ──────────────────────────────────────────────────────────────

import statistics

import pytest
from fastapi.testclient import TestClient

from agent.integrity import (
    IntegrityError,
    check_ai_authorship,
    check_plagiarism_against_kb,
    run_integrity_check,
)
from app.web_ui.main import app

# Import via `data.integrity_corpus`, not `tests.data.integrity_corpus`:
# tests/ has no __init__.py (matching every other file in this
# directory), so pytest's default import mode puts tests/ itself on
# sys.path rather than the repo root — `data` (tests/data/) resolves
# as an implicit namespace package from there without depending on
# `tests` being importable as a package.
from data.integrity_corpus import (
    AI_STYLE_SAMPLES,
    HUMAN_STYLE_SAMPLES,
    ORIGINAL_SAMPLES,
    PLAGIARISM_PAIRS,
)


# ── Unit tests: MIN_WORDS validation ────────────────────────────


def test_rejects_text_under_min_words():
    with pytest.raises(IntegrityError):
        check_ai_authorship("way too short")


def test_accepts_text_at_min_words():
    text = " ".join(["word"] * 50)
    result = check_ai_authorship(text)
    assert 0.0 <= result["ai_probability"] <= 1.0


# ── Corpus: AI-style vs human-style ordering ────────────────────
#
# The heuristic is noisy by nature (see docstring), so the test
# asserts the honest, defensible claim: *on average*, the AI-style
# corpus scores higher than the human-style corpus, and most
# individual samples land on the expected side. It does NOT assert
# every single sample crosses some absolute threshold — that would
# overstate what a heuristic like this can promise.


def test_ai_style_corpus_scores_higher_on_average_than_human_style():
    ai_scores = [check_ai_authorship(t)["ai_probability"] for t in AI_STYLE_SAMPLES]
    human_scores = [check_ai_authorship(t)["ai_probability"] for t in HUMAN_STYLE_SAMPLES]

    assert len(ai_scores) == 10
    assert len(human_scores) == 10
    assert statistics.mean(ai_scores) > statistics.mean(human_scores)


def test_most_ai_style_samples_score_above_most_human_style_samples():
    ai_scores = [check_ai_authorship(t)["ai_probability"] for t in AI_STYLE_SAMPLES]
    human_scores = [check_ai_authorship(t)["ai_probability"] for t in HUMAN_STYLE_SAMPLES]

    # Every AI-style sample should score higher than the human-style
    # median — a looser, more realistic bar than "beats every human
    # sample individually."
    human_median = statistics.median(human_scores)
    above_median_count = sum(1 for s in ai_scores if s > human_median)
    assert above_median_count >= 8  # allow up to 2 misses out of 10


@pytest.mark.parametrize("text", AI_STYLE_SAMPLES)
def test_each_ai_style_sample_is_well_formed(text):
    result = check_ai_authorship(text)
    assert result["signals"]["word_count"] >= 50


@pytest.mark.parametrize("text", HUMAN_STYLE_SAMPLES)
def test_each_human_style_sample_is_well_formed(text):
    result = check_ai_authorship(text)
    assert result["signals"]["word_count"] >= 50


# ── Corpus: plagiarism pairs (positive) ─────────────────────────


@pytest.mark.parametrize("source,near_copy", PLAGIARISM_PAIRS)
def test_near_copy_flagged_against_source_kb_doc(source, near_copy):
    kb_docs = [{"id": 1, "filename": "source.txt", "content": source}]
    matches = check_plagiarism_against_kb(near_copy, kb_docs, threshold=0.12)
    assert len(matches) == 1
    assert matches[0]["overlap_ratio"] >= 0.12


def test_all_ten_plagiarism_pairs_flagged():
    flagged = 0
    for source, near_copy in PLAGIARISM_PAIRS:
        kb_docs = [{"id": 1, "filename": "source.txt", "content": source}]
        matches = check_plagiarism_against_kb(near_copy, kb_docs, threshold=0.12)
        if matches:
            flagged += 1
    assert flagged == 10


# ── Corpus: original samples (negative) ─────────────────────────


@pytest.mark.parametrize("text", ORIGINAL_SAMPLES)
def test_original_sample_not_flagged_against_unrelated_kb_docs(text):
    # KB contains the plagiarism-pair source docs (all on unrelated
    # topics) — an original sample about something else entirely
    # should not cross the overlap threshold against any of them.
    kb_docs = [
        {"id": i, "filename": f"source_{i}.txt", "content": source}
        for i, (source, _copy) in enumerate(PLAGIARISM_PAIRS)
    ]
    matches = check_plagiarism_against_kb(text, kb_docs, threshold=0.12)
    assert matches == []


def test_empty_kb_never_flags_anything():
    for text in AI_STYLE_SAMPLES + HUMAN_STYLE_SAMPLES + ORIGINAL_SAMPLES:
        assert check_plagiarism_against_kb(text, []) == []


# ── run_integrity_check() response shape ────────────────────────


def test_run_integrity_check_shape_matches_frontend_contract():
    # static/js/app.js renderIntegrityResult() reads
    # data.ai_probability / data.summary / data.details (flat).
    result = run_integrity_check(AI_STYLE_SAMPLES[0], [])
    assert set(result.keys()) == {"ai_probability", "summary", "details"}
    assert isinstance(result["ai_probability"], float)
    assert isinstance(result["summary"], str) and result["summary"]
    assert isinstance(result["details"], list) and len(result["details"]) >= 2


# ── HTTP integration: real POST /integrity through the FastAPI app ─


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    import uuid

    username = f"itest_integrity_{uuid.uuid4().hex[:10]}"
    resp = client.post(
        "/auth/register", json={"username": username, "password": "correct-horse-battery"}
    )
    assert resp.status_code == 200, resp.text
    return client, username


def test_integrity_endpoint_requires_login(client):
    resp = client.post("/integrity", json={"text": " ".join(["word"] * 60)})
    assert resp.status_code == 401


def test_integrity_endpoint_rejects_short_text(auth_client):
    client, _username = auth_client
    resp = client.post("/integrity", json={"text": "too short"})
    assert resp.status_code == 400


def test_integrity_endpoint_returns_expected_shape(auth_client):
    client, _username = auth_client
    resp = client.post("/integrity", json={"text": AI_STYLE_SAMPLES[0]})
    assert resp.status_code == 200
    data = resp.json()
    assert "ai_probability" in data
    assert "summary" in data
    assert "details" in data


def test_integrity_endpoint_flags_plagiarism_against_uploaded_kb_doc(auth_client):
    client, _username = auth_client
    source, near_copy = PLAGIARISM_PAIRS[0]

    upload = client.post(
        "/kb/upload",
        files={"file": ("source.txt", source.encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 200, upload.text

    resp = client.post("/integrity", json={"text": near_copy})
    assert resp.status_code == 200
    data = resp.json()
    assert any("source.txt" in d for d in data["details"])


def test_integrity_endpoint_no_kb_match_when_nothing_uploaded(auth_client):
    client, _username = auth_client
    resp = client.post("/integrity", json={"text": ORIGINAL_SAMPLES[0]})
    assert resp.status_code == 200
    data = resp.json()
    assert any("No overlap found" in d for d in data["details"])
