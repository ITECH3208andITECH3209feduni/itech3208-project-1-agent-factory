"""
Async Playwright scraper for the Amazon research skill.

PROJ-167 — Sprint 2.

Fetches Amazon search results in parallel-friendly async style. Designed to
slot in behind a higher-level orchestrator (PROJ-166) that decides whether
to use this scraper or the RapidAPI fallback (PROJ-168).

Returns a list of product dicts. Each dict contains: title, price, rating,
review_count, url, image_url.

Raises:
    ScraperError: when the page fails to load within the timeout, or when
        Playwright itself raises any error during scraping. Generic
        exceptions are NOT propagated — callers can catch ScraperError
        without worrying about timeout vs network vs parsing.
"""

import re
from urllib.parse import quote_plus

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)


# ── Constants ────────────────────────────────────────────────
AMAZON_SEARCH_URL = "https://www.amazon.com/s?k={query}"
DEFAULT_TIMEOUT_MS = 5_000          # 5 seconds per page load (per spec)
DEFAULT_MAX_RESULTS = 10            # 10 results max (per spec)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


# ── Custom exception ─────────────────────────────────────────
class ScraperError(Exception):
    """Raised when the Amazon scraper fails (timeout, network, parsing)."""


# ── Public scrape function ───────────────────────────────────
async def scrape(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> list[dict]:
    """
    Scrape Amazon search results for `query`.

    Args:
        query: Search term, e.g. "wireless mouse".
        max_results: Maximum number of products to return (default 10).
        timeout_ms: Page-load timeout in milliseconds (default 5000).

    Returns:
        A list of product dicts, each with keys:
            title, price, rating, review_count, url, image_url

    Raises:
        ScraperError: on timeout or any Playwright error. The browser is
            always closed before this exception propagates.
    """
    url = AMAZON_SEARCH_URL.format(query=quote_plus(query))

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=USER_AGENT)
                page = await context.new_page()
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                html = await page.content()
            finally:
                # Always close the browser — even on error — to prevent leaks.
                await browser.close()
    except PlaywrightTimeoutError as e:
        raise ScraperError(f"Timed out loading Amazon search for '{query}'") from e
    except PlaywrightError as e:
        raise ScraperError(f"Playwright error scraping Amazon: {e}") from e

    return _parse_search_results(html, max_results=max_results)


# ── HTML parsing ─────────────────────────────────────────────

def _parse_search_results(html: str, *, max_results: int) -> list[dict]:
    """
    Parse Amazon search HTML into a list of product dicts.

    Lazy-imports BeautifulSoup so `import skills.amazon_scraper` doesn't
    fail in environments where bs4 is unavailable (e.g. early CI setup).
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise ScraperError("beautifulsoup4 not installed") from e

    soup = BeautifulSoup(html, "html.parser")
    products: list[dict] = []

    for card in soup.select('[data-component-type="s-search-result"]'):
        product = _parse_card(card)
        if product:
            products.append(product)
        if len(products) >= max_results:
            break

    return products


def _parse_card(card) -> dict | None:
    """Parse a single search-result card into a product dict, or None on failure."""
    try:
        # ── Title ──────────────────────────────────────
        title_el = (
            card.select_one("h2 span.a-size-medium.a-color-base.a-text-normal")
            or card.select_one("h2 span.a-size-base-plus.a-color-base.a-text-normal")
            or card.select_one("h2 span")
            or card.select_one("h2 a span")
        )
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None  # Skip cards without titles (often ads/banners)

        # ── Price ──────────────────────────────────────
        price_whole = card.select_one(".a-price-whole")
        price_frac = card.select_one(".a-price-fraction")
        if price_whole:
            price = f"${price_whole.get_text(strip=True)}"
            if price_frac:
                price += price_frac.get_text(strip=True)
        else:
            price_el = card.select_one(".a-price .a-offscreen")
            price = price_el.get_text(strip=True) if price_el else ""

        # ── Rating ─────────────────────────────────────
        rating_el = (
            card.select_one(".a-icon-star-small .a-icon-alt")
            or card.select_one("[aria-label*='out of 5 stars']")
            or card.select_one(".a-icon-alt")  # bare .a-icon-alt span (real Amazon + tests)
        )
        rating = ""
        if rating_el:
            rating_text = rating_el.get("aria-label") or rating_el.get_text()
            match = re.search(r"[\d.]+", rating_text)
            rating = match.group() if match else ""

        # ── Review count ───────────────────────────────
        reviews_el = card.select_one(".a-size-small .a-link-normal") or card.select_one(
            "[aria-label*='ratings']"
        )
        review_count = ""
        if reviews_el:
            review_text = reviews_el.get_text(strip=True)
            match = re.search(r"[\d,]+", review_text)
            review_count = match.group().replace(",", "") if match else ""

        # ── URL ────────────────────────────────────────
        link_el = card.select_one("h2 a") or card.select_one("a.a-link-normal")
        href = link_el.get("href", "") if link_el else ""
        url = f"https://www.amazon.com{href}" if href.startswith("/") else href

        # ── Image ──────────────────────────────────────
        img_el = card.select_one("img.s-image")
        image_url = img_el.get("src", "") if img_el else ""

        return {
            "title":        title,
            "price":        price,
            "rating":       rating,
            "review_count": review_count,
            "url":          url,
            "image_url":    image_url,
        }
    except Exception:
        # Don't let one malformed card kill the whole scrape.
        return None