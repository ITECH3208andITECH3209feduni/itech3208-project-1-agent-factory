# tests/app/skills/test_amazon_skill.py
# PROJ-166: tests for the AmazonSkill adapter
from unittest.mock import patch, MagicMock
from app.skills.amazon_skill import search, MAX_RESULTS
from components.amazon_cards import ProductCard


def _fake_raw(title, rating=4.5, reviews=100, price="20.00 USD"):
    url = "https://amazon.com/dp/" + title.replace(" ", "-")
    return {
        "title":    title,
        "price":    price,
        "rating":   rating,
        "reviews":  reviews,
        "link":     url,
        "image":    "",
        "source":   "amazon",
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


def test_search_returns_dict_envelope_with_product_card_list():
    raw = [_fake_raw("A"), _fake_raw("B")]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")
    assert isinstance(response, dict)
    assert response["success"] is True
    assert all(isinstance(c, ProductCard) for c in response["results"])
    assert len(response["results"]) == 2


def test_search_sorts_by_score_descending():
    raw = [
        _fake_raw("Low",    rating=3.0, reviews=10),
        _fake_raw("High",   rating=5.0, reviews=5000),
        _fake_raw("Medium", rating=4.0, reviews=500),
    ]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")
    scores = [c.score for c in response["results"]]
    assert scores == sorted(scores, reverse=True)
    assert response["results"][0].title == "High"


def test_search_caps_at_max_results():
    raw = [_fake_raw("item-" + str(i)) for i in range(25)]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")
    assert len(response["results"]) == MAX_RESULTS == 10


def test_search_returns_empty_list_when_underlying_skill_raises():
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.side_effect = RuntimeError("scraper exploded")
        response = search("anything")
    assert response["success"] is False
    assert response["results"] == []
    assert "scraper exploded" in response["error"]


def test_search_returns_empty_list_when_underlying_skill_unsuccessful():
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(
            success=False, results=[], error="503 from Amazon"
        )
        response = search("anything")
    assert response["success"] is False
    assert response["results"] == []
    assert "503" in response["error"]


def test_search_skips_individual_products_that_fail_to_parse():
    raw = [
        {"title": "bad", "rating": "not a number", "reviews": "also bad"},
        _fake_raw("good"),
    ]
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = _fake_skill_result(success=True, results=raw)
        response = search("anything")
    titles = [c.title for c in response["results"]]
    assert "good" in titles


def test_search_passes_through_metadata_and_summary():
    fake_result = _fake_skill_result(
        success=True,
        results=[_fake_raw("X")],
        metadata={"source": "Amazon.com (scraped)", "total_found": 1},
    )
    fake_result.summary = "Found 1 product"
    with patch("app.skills.amazon_skill._AmazonSkill") as MockSkill:
        MockSkill.return_value.return_value = fake_result
        response = search("anything")
    assert response["summary"] == "Found 1 product"
    assert response["metadata"]["source"] == "Amazon.com (scraped)"
