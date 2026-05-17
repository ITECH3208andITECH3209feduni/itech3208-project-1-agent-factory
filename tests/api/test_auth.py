# tests/api/test_auth.py
# ──────────────────────────────────────────────────────────────
# Tests for API key authentication middleware.
# PROJ-113.
# ──────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient

from api.main import app
from api.routes import literature as literature_route
from skills.base_skill import SkillResult

client = TestClient(app)

VALID_KEY = "test-api-key-for-pytest"  # matches conftest.py


def _stub_literature_success(monkeypatch):
    """Patch the literature skill so we get past the skill call cleanly."""
    monkeypatch.setattr(
        literature_route,
        "_literature_skill",
        lambda q: SkillResult(
            skill_name="literature",
            query=q,
            success=True,
            results=[{"title": "T", "source": "arXiv"}],
        ),
    )


def test_health_endpoint_does_not_require_auth():
    """/health is public — no key needed."""
    response = client.get("/health")
    assert response.status_code == 200


def test_api_endpoint_with_valid_header_key_passes(monkeypatch):
    """Valid key via X-API-Key header → 200."""
    _stub_literature_success(monkeypatch)
    response = client.get(
        "/api/literature",
        params={"q": "test"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 200


def test_api_endpoint_with_valid_query_key_passes(monkeypatch):
    """Valid key via ?api_key= query param → 200."""
    _stub_literature_success(monkeypatch)
    response = client.get(
        "/api/literature",
        params={"q": "test", "api_key": VALID_KEY},
    )
    assert response.status_code == 200


def test_api_endpoint_with_missing_key_returns_401():
    """No key in header or query → 401 with 'required' message."""
    response = client.get("/api/literature", params={"q": "test"})
    assert response.status_code == 401
    assert "required" in response.json()["detail"].lower()


def test_api_endpoint_with_wrong_key_returns_401():
    """Wrong key value → 401 with 'invalid' message."""
    response = client.get(
        "/api/literature",
        params={"q": "test"},
        headers={"X-API-Key": "this-is-wrong"},
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_api_endpoint_fails_closed_when_env_unset(monkeypatch):
    """If API_KEY is unset/empty in env, requests fail even with 'correct' guesses."""
    monkeypatch.setenv("API_KEY", "")  # override the conftest fixture
    response = client.get(
        "/api/literature",
        params={"q": "test"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert response.status_code == 401
    assert "not configured" in response.json()["detail"].lower()


def test_amazon_endpoint_also_requires_auth():
    """Confirm auth covers /api/amazon too, not just literature."""
    response = client.get("/api/amazon", params={"q": "laptop"})
    assert response.status_code == 401