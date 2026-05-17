# tests/api/test_literature_endpoint.py
# ──────────────────────────────────────────────────────────────
# Tests for GET /api/literature
# Uses FastAPI TestClient — no real HTTP calls to arXiv/etc.
# All authenticated calls include the X-API-Key header so they pass
# the auth dependency added in PROJ-113.
# ──────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient

from api.main import app
from api.routes import literature as literature_route
from skills.base_skill import SkillResult

client = TestClient(app)

# Matches the key set by tests/api/conftest.py
HEADERS = {"X-API-Key": "test-api-key-for-pytest"}


def _fake_result(results: list[dict], success: bool = True, error: str = "") -> SkillResult:
    """Build a fake SkillResult for monkeypatching the skill call."""
    return SkillResult(
        skill_name="literature",
        query="test",
        success=success,
        results=results,
        error=error,
    )


def _patch_skill(monkeypatch, fake_result: SkillResult) -> None:
    """Replace the skill instance with a stub returning fake_result."""
    monkeypatch.setattr(
        literature_route,
        "_literature_skill",
        lambda q: fake_result,
    )


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_literature_returns_papers(monkeypatch):
    """Happy path: skill returns results, API returns 200 with mapped papers."""
    fake_results = [
        {
            "title":    "Attention Is All You Need",
            "authors":  "Vaswani et al.",
            "year":     "2017",
            "abstract": "We propose a new simple network architecture, the Transformer.",
            "link":     "https://arxiv.org/abs/1706.03762",
            "source":   "arXiv",
        }
    ]
    _patch_skill(monkeypatch, _fake_result(fake_results))

    response = client.get(
        "/api/literature",
        params={"q": "transformers"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "transformers"
    assert body["count"] == 1
    paper = body["papers"][0]
    assert paper["title"]  == "Attention Is All You Need"
    assert paper["url"]    == "https://arxiv.org/abs/1706.03762"  # link → url mapping
    assert paper["source"] == "arXiv"
    assert paper["year"]   == "2017"


def test_literature_missing_query_returns_422():
    """No q param → FastAPI's automatic validation returns 422."""
    response = client.get("/api/literature", headers=HEADERS)
    assert response.status_code == 422


def test_literature_empty_query_returns_422():
    """Empty q param → 422 because of min_length=1."""
    response = client.get(
        "/api/literature",
        params={"q": ""},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_literature_skill_failure_returns_502(monkeypatch):
    """All upstream sources error → 502 Bad Gateway."""
    _patch_skill(
        monkeypatch,
        _fake_result(
            results=[],
            success=False,
            error="arXiv: timeout; Semantic Scholar: 500",
        ),
    )
    response = client.get(
        "/api/literature",
        params={"q": "anything"},
        headers=HEADERS,
    )
    assert response.status_code == 502
    assert "timeout" in response.json()["detail"].lower()