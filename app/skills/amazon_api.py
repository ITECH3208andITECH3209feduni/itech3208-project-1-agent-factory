# app/skills/amazon_api.py
# PROJ-168: RapidAPI Amazon fallback
# Standalone client. Wired into the skill stack by PROJ-170.

import time
from typing import Optional

import requests

from config.settings import RAPIDAPI_KEY, RAPIDAPI_AMAZON_HOST, REQUEST_TIMEOUT


class APIError(Exception):
    """Raised on unrecoverable RapidAPI failures."""
    pass


_SEARCH_URL = f"https://{RAPIDAPI_AMAZON_HOST}/search"
_RETRY_DELAY_SECONDS = 1.0


def _coerce_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise(raw: dict) -> dict:
    """Map a real-time-amazon-data product dict to our schema."""
    rating = _coerce_float(raw.get("product_star_rating"))
    reviews = raw.get("product_num_ratings")
    try:
        review_count = int(reviews) if reviews is not None else 0
    except (TypeError, ValueError):
        review_count = 0

    return {
        "title":        raw.get("product_title", "") or "",
        "price":        raw.get("product_price", "") or "",
        "rating":       rating if rating is not None else 0.0,
        "review_count": review_count,
        "url":          raw.get("product_url", "") or "",
        "image_url":    raw.get("product_photo", "") or "",
        "source":       "rapidapi",
    }


def search_via_api(query: str) -> list:
    """
    Fetch Amazon search results from real-time-amazon-data on RapidAPI.

    Returns a list of dicts with keys: title, price, rating, review_count,
    url, image_url, source. The source field is always "rapidapi".

    Raises APIError if RAPIDAPI_KEY is unset, if HTTP responses are
    unrecoverable (non-2xx after retry on 429), or if the JSON body is
    malformed. Callers (PROJ-170) decide how to react.
    """
    if not RAPIDAPI_KEY:
        raise APIError("RAPIDAPI_KEY environment variable is not set")

    headers = {
        "X-RapidAPI-Key":  RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_AMAZON_HOST,
    }
    params = {
        "query":   query,
        "country": "US",
        "page":    "1",
    }

    response = requests.get(_SEARCH_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)

    if response.status_code == 429:
        time.sleep(_RETRY_DELAY_SECONDS)
        response = requests.get(_SEARCH_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)

    if response.status_code != 200:
        body_snippet = (response.text or "")[:200]
        raise APIError(f"RapidAPI returned {response.status_code}: {body_snippet}")

    try:
        payload = response.json()
    except ValueError as e:
        raise APIError(f"RapidAPI returned non-JSON body: {e}")

    data = payload.get("data") or {}
    products = data.get("products") or []

    return [_normalise(p) for p in products]
