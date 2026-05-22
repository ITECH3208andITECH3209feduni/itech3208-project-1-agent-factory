# tests/api/test_amazon_endpoint.py
# ──────────────────────────────────────────────────────────────
# Tests for GET /api/amazon
# Uses FastAPI TestClient — no real scraping.
# ──────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient

from api.main import app
from api.routes import amazon as amazon_route
from skills.base_skill import SkillResult

client = TestClient(app)


def _fake_result(results: list[dict], success: bool = True, error: str = "") -> SkillResult:
    """Build a fake SkillResult for monkeypatching the skill call."""
    return SkillResult(
        skill_name="amazon",
        query="test",
        success=success,
        results=results,
        error=error,
    )


def _patch_skill(monkeypatch, fake_result: SkillResult) -> None:
    """Replace the skill's _run_normal_search with a stub returning fake_result."""
    monkeypatch.setattr(
        amazon_route._amazon_skill,
        "_run_normal_search",
        lambda q: fake_result,
    )


def test_amazon_returns_products(monkeypatch):
    """Happy path: skill returns results, API returns 200 with mapped products."""
    fake_results = [
        {
            "title":  "Sony WH-1000XM5 Headphones",
            "price":  "$349.99",
            "rating": "4.5 / 5",
            "asin":   "B09XS7JWHH",
            "link":   "https://www.amazon.com/dp/B09XS7JWHH",
            # Extra fields the skill returns but the API should drop:
            "reviews": "1,234",
            "prime":   True,
            "image":   "https://example.com/img.jpg",
            "source":  "Amazon",
        }
    ]
    _patch_skill(monkeypatch, _fake_result(fake_results))

    response = client.get("/api/amazon", params={"q": "headphones"})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "headphones"
    assert body["count"] == 1

    product = body["products"][0]
    assert product["title"]  == "Sony WH-1000XM5 Headphones"
    assert product["price"]  == "$349.99"
    assert product["rating"] == "4.5 / 5"
    assert product["asin"]   == "B09XS7JWHH"
    assert product["url"]    == "https://www.amazon.com/dp/B09XS7JWHH"

    # Verify the API drops fields not in the spec
    assert "reviews" not in product
    assert "prime"   not in product
    assert "image"   not in product
    assert "source"  not in product


def test_amazon_missing_query_returns_422():
    """No q param → FastAPI's automatic validation returns 422."""
    response = client.get("/api/amazon")
    assert response.status_code == 422


def test_amazon_empty_query_returns_422():
    """Empty q param → 422 because of min_length=1."""
    response = client.get("/api/amazon", params={"q": ""})
    assert response.status_code == 422


def test_amazon_skill_failure_returns_502(monkeypatch):
    """Scraper error → 502 Bad Gateway."""
    _patch_skill(
        monkeypatch,
        _fake_result(
            results=[],
            success=False,
            error="Playwright unavailable; requests fallback returned 503",
        ),
    )
    response = client.get("/api/amazon", params={"q": "anything"})
    assert response.status_code == 502
    assert "playwright" in response.json()["detail"].lower()


def test_amazon_zero_results_with_success_returns_200(monkeypatch):
    """Skill ran successfully but found no products → 200 with empty array."""
    _patch_skill(monkeypatch, _fake_result(results=[], success=True))
    response = client.get("/api/amazon", params={"q": "xyznonexistent123"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["products"] == []
    