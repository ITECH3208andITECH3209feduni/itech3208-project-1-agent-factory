# tests/app/skills/test_amazon_skill.py
# PROJ-166 + PROJ-170: tests for the AmazonSkill adapter with source fallback.
from unittest.mock import patch, MagicMock

from app.skills.amazon_skill import search, MAX_RESULTS, ScraperError
from app.skills.amazon_api import APIError


def _fake_raw(title, rating=4.5, reviews=100, price="20.00"):
    return {
        "title":    title,
        "price":    price,
        "rating":   rating,
        "reviews":  reviews,
        "link":     "https://amazon.com/dp/" + title.replace(" ", "-"),
        "image":    "",
        "source":   "",
        "bsr":      "",
        "category": "",
    }


def _fake_skill_result(success=True, results=None, error="", metadata=None):
    mock = MagicMock()
    mock.success  = success
    mock.results  = results or []
    mock.error    = error
    mock.summary  = ""
    mock.metadata = metadata or {}
    return mock


def _api_raw(title="API result"):
    return {
        "title":        title,
        "price":        "$15",
        "rating":       4.7,
        "review_count": 500,
        "url":          "https://x",
        "image_url":    "https://i",
        "source":       "rapidapi",
    }


# ---- Scraper success path -------------------------------------------------

def test_search_uses_scraper_when_it_succeeds():
    raw = [_fake_raw("A"), _fake_raw("B")]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill, \
         patch("app.skills.amazon_skill.search_via_api") as MockApi:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")

    assert response["success"] is True
    assert len(response["results"]) == 2
    assert response["metadata"]["source_used"] == "playwright"
    MockApi.assert_not_called()


def test_scraper_results_tagged_playwright():
    raw = [_fake_raw("X")]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")

    assert response["results"][0].source == "playwright"


# ---- Sort + cap (carried over from PROJ-166) ------------------------------

def test_search_sorts_by_score_descending():
    raw = [
        _fake_raw("Low",  rating=3.0, reviews=10),
        _fake_raw("High", rating=5.0, reviews=5000),
        _fake_raw("Mid",  rating=4.0, reviews=500),
    ]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")

    scores = [c.score for c in response["results"]]
    assert scores == sorted(scores, reverse=True)


def test_search_caps_at_max_results():
    raw = [_fake_raw("item-" + str(i)) for i in range(25)]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")

    assert len(response["results"]) == MAX_RESULTS == 10


# ---- API fallback path ----------------------------------------------------

def test_falls_back_to_api_when_scraper_raises():
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill, \
         patch("app.skills.amazon_skill.search_via_api", return_value=[_api_raw()]) as MockApi:
        MockSkill.return_value.side_effect = RuntimeError("playwright blocked")
        response = search("anything")

    assert response["success"] is True
    assert response["metadata"]["source_used"] == "rapidapi"
    assert response["results"][0].source == "rapidapi"
    MockApi.assert_called_once_with("anything")


def test_falls_back_to_api_when_scraper_unsuccessful():
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill, \
         patch("app.skills.amazon_skill.search_via_api", return_value=[_api_raw()]):
        MockSkill.return_value.return_value = _fake_skill_result(success=False, error="503")
        response = search("anything")

    assert response["success"] is True
    assert response["metadata"]["source_used"] == "rapidapi"


def test_falls_back_to_api_when_scraper_returns_empty():
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill, \
         patch("app.skills.amazon_skill.search_via_api", return_value=[_api_raw()]):
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=[])
        response = search("anything")

    assert response["metadata"]["source_used"] == "rapidapi"


# ---- Both-failed path -----------------------------------------------------

def test_returns_empty_when_both_sources_fail():
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill, \
         patch("app.skills.amazon_skill.search_via_api") as MockApi:
        MockSkill.return_value.side_effect = RuntimeError("playwright blocked")
        MockApi.side_effect = APIError("RAPIDAPI_KEY missing")
        response = search("anything")

    assert response["success"] is False
    assert response["results"] == []
    assert "Both sources failed" in response["error"]
    assert response["metadata"]["source_used"] == "none"


# ---- Never raises ---------------------------------------------------------

def test_search_never_raises_even_with_unexpected_errors():
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill, \
         patch("app.skills.amazon_skill.search_via_api") as MockApi:
        MockSkill.return_value.side_effect = RuntimeError("scraper boom")
        MockApi.side_effect = APIError("api boom")
        response = search("anything")
        assert response["success"] is False
