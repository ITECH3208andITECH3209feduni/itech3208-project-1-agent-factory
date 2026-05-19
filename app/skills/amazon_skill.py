# app/skills/amazon_skill.py
# PROJ-166 + PROJ-170: AmazonSkill adapter with source fallback.
#
# Try the Playwright-backed scraper first; on any failure (raise or
# success=False with no results) fall back to the RapidAPI client.
# If both fail, return an empty envelope. Per-product source tag is
# set to "playwright" or "rapidapi" so downstream consumers can
# distinguish.

import logging

from app.skills.amazon_cards import ProductCard
from app.skills.amazon_api import search_via_api, APIError
from skills.amazon import AmazonSkill as _AmazonSkill

logger = logging.getLogger(__name__)

MAX_RESULTS = 10


class ScraperError(Exception):
    """Raised by the adapter when the inner Playwright skill fails."""
    pass


def _run_scraper(query):
    """
    Returns (list[dict], inner_result) where the dicts are raw products
    tagged source='playwright'. Raises ScraperError on inner-skill
    failure or empty results so the caller can fall through to the API.
    """
    try:
        skill = _AmazonSkill()
        result = skill(query)
    except Exception as e:
        raise ScraperError("Scraper raised: " + str(e)) from e

    if not getattr(result, "success", False):
        err = getattr(result, "error", "") or "unsuccessful"
        raise ScraperError("Scraper unsuccessful: " + str(err))

    raw_products = getattr(result, "results", []) or []
    if not raw_products:
        raise ScraperError("Scraper returned no results")

    for raw in raw_products:
        raw["source"] = "playwright"

    return raw_products, result


def _run_api(query):
    """Returns list[dict] of raw products already tagged source='rapidapi'."""
    return search_via_api(query)


def _to_cards(raw_products):
    cards = []
    for raw in raw_products:
        try:
            cards.append(ProductCard.from_skill_result(raw))
        except Exception:
            continue
    cards.sort(key=lambda c: c.score, reverse=True)
    return cards[:MAX_RESULTS]


def _empty_response(error="", metadata=None):
    return {
        "success":  False,
        "results":  [],
        "summary":  "",
        "error":    error,
        "metadata": metadata or {},
    }


def search(query):
    """
    Web-UI-facing Amazon search with automatic source fallback.

    Tries the Playwright scraper first; on ScraperError, falls back to
    RapidAPI. Returns a dict envelope with typed ProductCard results.
    Never raises - returns empty envelope if both sources fail.
    """
    # ---- 1. Playwright scraper ---------------------------------
    scraper_error = ""
    try:
        raw_products, inner_result = _run_scraper(query)
        cards = _to_cards(raw_products)
        for c in cards:
            c.source = "playwright"
        if cards:
            logger.info(
                "amazon_skill: scraper succeeded (%d results) for query=%r",
                len(cards), query,
            )
            metadata = dict(getattr(inner_result, "metadata", {}) or {})
            metadata["source_used"] = "playwright"
            return {
                "success":  True,
                "results":  cards,
                "summary":  getattr(inner_result, "summary", "") or "",
                "error":    "",
                "metadata": metadata,
            }
        scraper_error = "Scraper returned no parseable products"
    except ScraperError as e:
        scraper_error = str(e)

    logger.info(
        "amazon_skill: scraper failed (%s) for query=%r, trying API fallback",
        scraper_error, query,
    )

    # ---- 2. RapidAPI fallback ----------------------------------
    try:
        raw_products = _run_api(query)
    except APIError as e:
        logger.warning(
            "amazon_skill: both sources failed for query=%r (scraper: %s, api: %s)",
            query, scraper_error, e,
        )
        return _empty_response(
            error="Both sources failed. Scraper: " + scraper_error + ". API: " + str(e),
            metadata={"source_used": "none"},
        )

    cards = _to_cards(raw_products)
    for c in cards:
        c.source = "rapidapi"
    if not cards:
        logger.warning(
            "amazon_skill: API returned no parseable products for query=%r", query,
        )
        return _empty_response(
            error="Scraper failed (" + scraper_error + "); API returned no usable results",
            metadata={"source_used": "rapidapi"},
        )

    logger.info(
        "amazon_skill: API fallback succeeded (%d results) for query=%r",
        len(cards), query,
    )
    return {
        "success":  True,
        "results":  cards,
        "summary":  "",
        "error":    "",
        "metadata": {"source_used": "rapidapi"},
    }
