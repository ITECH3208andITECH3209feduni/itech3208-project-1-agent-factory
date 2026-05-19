# tests/app/skills/test_amazon_api.py
# PROJ-168: tests for app.skills.amazon_api
from unittest.mock import patch, MagicMock

import pytest


def _fake_response(status_code=200, json_payload=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_payload is None:
        resp.json.side_effect = ValueError("no JSON")
    else:
        resp.json.return_value = json_payload
    return resp


def _payload(products):
    return {"status": "OK", "request_id": "x", "data": {"products": products}}


def _raw(title="Item", price="$10.00", rating="4.5", reviews=100, url="https://amazon.com/x", image="https://img"):
    return {
        "product_title": title,
        "product_price": price,
        "product_star_rating": rating,
        "product_num_ratings": reviews,
        "product_url": url,
        "product_photo": image,
        "asin": "ASIN123",
    }


def test_search_returns_normalised_dicts(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "fake-key")
    # Force re-read of settings after patching env. amazon_api caches the value.
    import importlib
    import config.settings
    importlib.reload(config.settings)
    import app.skills.amazon_api as mod
    importlib.reload(mod)

    fake = _fake_response(200, _payload([_raw(title="Headphones")]))
    with patch.object(mod.requests, "get", return_value=fake):
        results = mod.search_via_api("anything")

    assert isinstance(results, list)
    assert len(results) == 1
    item = results[0]
    assert item["title"] == "Headphones"
    assert item["source"] == "rapidapi"
    assert set(["title", "price", "rating", "review_count", "url", "image_url", "source"]).issubset(item.keys())


def test_search_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    import importlib
    import config.settings
    importlib.reload(config.settings)
    import app.skills.amazon_api as mod
    importlib.reload(mod)

    with pytest.raises(mod.APIError):
        mod.search_via_api("anything")


def test_search_retries_once_on_429_then_succeeds(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "fake-key")
    import importlib
    import config.settings
    importlib.reload(config.settings)
    import app.skills.amazon_api as mod
    importlib.reload(mod)

    first = _fake_response(429, text="too many")
    second = _fake_response(200, _payload([_raw(title="OK")]))
    with patch.object(mod.requests, "get", side_effect=[first, second]) as m,          patch.object(mod.time, "sleep") as sleep_mock:
        results = mod.search_via_api("anything")

    assert len(results) == 1
    assert results[0]["title"] == "OK"
    assert m.call_count == 2
    sleep_mock.assert_called_once()


def test_search_raises_on_second_429(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "fake-key")
    import importlib
    import config.settings
    importlib.reload(config.settings)
    import app.skills.amazon_api as mod
    importlib.reload(mod)

    bad = _fake_response(429, text="still too many")
    with patch.object(mod.requests, "get", side_effect=[bad, bad]),          patch.object(mod.time, "sleep"):
        with pytest.raises(mod.APIError):
            mod.search_via_api("anything")


def test_search_raises_on_500(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "fake-key")
    import importlib
    import config.settings
    importlib.reload(config.settings)
    import app.skills.amazon_api as mod
    importlib.reload(mod)

    fake = _fake_response(500, text="server fail")
    with patch.object(mod.requests, "get", return_value=fake):
        with pytest.raises(mod.APIError):
            mod.search_via_api("anything")


def test_search_returns_empty_on_no_products(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "fake-key")
    import importlib
    import config.settings
    importlib.reload(config.settings)
    import app.skills.amazon_api as mod
    importlib.reload(mod)

    fake = _fake_response(200, _payload([]))
    with patch.object(mod.requests, "get", return_value=fake):
        results = mod.search_via_api("anything")

    assert results == []


def test_search_raises_on_malformed_json(monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "fake-key")
    import importlib
    import config.settings
    importlib.reload(config.settings)
    import app.skills.amazon_api as mod
    importlib.reload(mod)

    fake = _fake_response(200, json_payload=None, text="not json")
    with patch.object(mod.requests, "get", return_value=fake):
        with pytest.raises(mod.APIError):
            mod.search_via_api("anything")
