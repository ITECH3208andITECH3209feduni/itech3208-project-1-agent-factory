"""Tests for skills/amazon_scraper.py — PROJ-167.

All tests use mocked Playwright — they never hit real Amazon.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from skills.amazon_scraper import scrape, ScraperError, _parse_search_results


# ── Sample HTML fixture ──────────────────────────────────────

SAMPLE_HTML = """
<html><body>
  <div data-component-type="s-search-result">
    <h2><a href="/dp/B001"><span>Wireless Mouse Model A</span></a></h2>
    <span class="a-price"><span class="a-offscreen">$24.99</span></span>
    <span class="a-icon-alt">4.5 out of 5 stars</span>
    <span class="a-size-small"><a class="a-link-normal">1,234 ratings</a></span>
    <img class="s-image" src="https://images.example.com/a.jpg"/>
  </div>
  <div data-component-type="s-search-result">
    <h2><a href="/dp/B002"><span>Wireless Mouse Model B</span></a></h2>
    <span class="a-price"><span class="a-offscreen">$39.99</span></span>
    <span class="a-icon-alt">4.2 out of 5 stars</span>
    <span class="a-size-small"><a class="a-link-normal">567 ratings</a></span>
    <img class="s-image" src="https://images.example.com/b.jpg"/>
  </div>
</body></html>
"""


def _build_mock_playwright(html: str = SAMPLE_HTML, raise_on_goto=None):
    """Build a fake Playwright async chain for tests."""
    page = MagicMock()
    page.goto = AsyncMock(side_effect=raise_on_goto) if raise_on_goto else AsyncMock()
    page.content = AsyncMock(return_value=html)

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)

    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    chromium = MagicMock()
    chromium.launch = AsyncMock(return_value=browser)

    pw = MagicMock()
    pw.chromium = chromium

    pw_cm = MagicMock()
    pw_cm.__aenter__ = AsyncMock(return_value=pw)
    pw_cm.__aexit__ = AsyncMock(return_value=False)

    return pw_cm, browser


# ── AC #1: returns list of dicts with 6 fields each ─────────

async def test_scrape_returns_list_of_dicts():
    pw_cm, _ = _build_mock_playwright()
    with patch("skills.amazon_scraper.async_playwright", return_value=pw_cm):
        results = await scrape("wireless mouse")
    assert isinstance(results, list)
    assert len(results) == 2
    for r in results:
        assert isinstance(r, dict)


async def test_scrape_returns_all_six_fields():
    pw_cm, _ = _build_mock_playwright()
    with patch("skills.amazon_scraper.async_playwright", return_value=pw_cm):
        results = await scrape("wireless mouse")

    expected_keys = {"title", "price", "rating", "review_count", "url", "image_url"}
    for r in results:
        assert expected_keys.issubset(r.keys()), f"Missing keys in {r}"


async def test_scrape_extracts_correct_values():
    pw_cm, _ = _build_mock_playwright()
    with patch("skills.amazon_scraper.async_playwright", return_value=pw_cm):
        results = await scrape("wireless mouse")

    first = results[0]
    assert first["title"] == "Wireless Mouse Model A"
    assert first["price"] == "$24.99"
    assert first["rating"] == "4.5"
    assert first["review_count"] == "1234"
    assert first["url"] == "https://www.amazon.com/dp/B001"
    assert first["image_url"] == "https://images.example.com/a.jpg"


# ── AC #2: browser is always closed ─────────────────────────

async def test_browser_closed_on_success():
    pw_cm, browser = _build_mock_playwright()
    with patch("skills.amazon_scraper.async_playwright", return_value=pw_cm):
        await scrape("query")
    browser.close.assert_awaited_once()


async def test_browser_closed_on_timeout():
    pw_cm, browser = _build_mock_playwright(
        raise_on_goto=PlaywrightTimeoutError("timeout")
    )
    with patch("skills.amazon_scraper.async_playwright", return_value=pw_cm):
        with pytest.raises(ScraperError):
            await scrape("query")
    browser.close.assert_awaited_once()


# ── AC #3: timeout → ScraperError, not generic Exception ────

async def test_timeout_raises_scraper_error():
    pw_cm, _ = _build_mock_playwright(
        raise_on_goto=PlaywrightTimeoutError("timeout")
    )
    with patch("skills.amazon_scraper.async_playwright", return_value=pw_cm):
        with pytest.raises(ScraperError) as exc_info:
            await scrape("query")
    assert "timed out" in str(exc_info.value).lower()


def test_scraper_error_is_a_subclass_of_exception():
    assert ScraperError is not Exception
    assert issubclass(ScraperError, Exception)


# ── max_results respected ───────────────────────────────────

async def test_max_results_caps_returned_list():
    pw_cm, _ = _build_mock_playwright()
    with patch("skills.amazon_scraper.async_playwright", return_value=pw_cm):
        results = await scrape("query", max_results=1)
    assert len(results) == 1


# ── Pure parser tests (no async) ────────────────────────────

def test_parse_search_results_returns_list():
    out = _parse_search_results(SAMPLE_HTML, max_results=10)
    assert isinstance(out, list)
    assert len(out) == 2


def test_parse_search_results_skips_malformed_cards():
    html = """
    <div data-component-type="s-search-result"></div>
    <div data-component-type="s-search-result">
      <h2><a href="/dp/B001"><span>Real Product</span></a></h2>
    </div>
    """
    out = _parse_search_results(html, max_results=10)
    assert len(out) == 1
    assert out[0]["title"] == "Real Product"