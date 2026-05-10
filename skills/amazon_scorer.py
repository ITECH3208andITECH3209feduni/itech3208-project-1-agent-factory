"""
Product quality scorer for the Amazon research skill.

PROJ-169 — Sprint 2.

Computes a 0-100 quality score for an Amazon product based on its rating,
review count, price, and availability. Higher scores indicate higher-quality
products that are likely worth buying.

Formula
-------
    score = (rating       * 40)
          + (reviews_norm  * 30)
          + (price_inv     * 20)
          + (availability  * 10)

Each component is normalised to the range 0.0-1.0 before being weighted, so
the maximum achievable score is 40 + 30 + 20 + 10 = 100.
"""

import math
import re
from typing import Any

# ── Constants ────────────────────────────────────────────────
MAX_RATING = 5.0          # Amazon star ratings are out of 5
REVIEW_CAP = 10_000        # Reviews beyond this don't increase the score
PRICE_CAP  = 1_000.0       # Prices above this are treated as "very expensive"

# Weights from the spec (must sum to 100)
W_RATING       = 40
W_REVIEWS      = 30
W_PRICE        = 20
W_AVAILABILITY = 10


# ── Helpers to normalise each input to 0.0-1.0 ───────────────

def _normalise_rating(rating: Any) -> float:
    """
    Convert a 0-5 star rating to 0.0-1.0.

    Accepts numbers (`4.5`) or strings like `"4.5 / 5"` or `"4.5"`.
    Returns 0.0 if the value can't be parsed.
    """
    value = _parse_first_number(rating)
    if value is None:
        return 0.0
    return _clamp(value / MAX_RATING, 0.0, 1.0)


def _normalise_reviews(reviews: Any) -> float:
    """
    Log-normalise a review count to 0.0-1.0 (capped at 10,000).

    Uses log10(n + 1) / log10(REVIEW_CAP + 1) so that:
        0 reviews     → 0.0
        100 reviews   → ~0.50
        1,000 reviews → ~0.75
        10,000+       → 1.0
    """
    count = _parse_first_number(reviews)
    if count is None or count <= 0:
        return 0.0
    capped = min(count, REVIEW_CAP)
    return _clamp(math.log10(capped + 1) / math.log10(REVIEW_CAP + 1), 0.0, 1.0)


def _normalise_price(price: Any) -> float:
    """
    Inverse-normalise price to 0.0-1.0 (cheaper = higher).

    Returns:
        1.0 for free / $0
        0.0 for $1,000+ or unparseable
        Linearly interpolated in between.
    """
    value = _parse_first_number(price)
    if value is None or value < 0:
        return 0.0
    if value >= PRICE_CAP:
        return 0.0
    return _clamp(1.0 - (value / PRICE_CAP), 0.0, 1.0)


def _normalise_availability(availability: Any) -> float:
    """
    Map availability to 0.0, 0.5, or 1.0.

    Accepted inputs:
      - In stock   → "in_stock", "in stock", "available", True, 1
      - Limited    → "limited", "low_stock", "low stock"
      - Out        → "out_of_stock", "out of stock", "unavailable",
                     False, 0, None
    Anything else defaults to 0.0 (treated as out of stock).
    """
    if isinstance(availability, bool):
        return 1.0 if availability else 0.0
    if isinstance(availability, (int, float)):
        return 1.0 if availability >= 1 else 0.0
    if availability is None:
        return 0.0

    norm = str(availability).strip().lower().replace(" ", "_")
    if norm in {"in_stock", "available", "yes", "true"}:
        return 1.0
    if norm in {"limited", "low_stock", "few_left"}:
        return 0.5
    if norm in {"out_of_stock", "unavailable", "no", "false"}:
        return 0.0
    return 0.0


# ── Public scoring function ──────────────────────────────────

def score(card: dict) -> int:
    """
    Return a 0-100 quality score for an Amazon product.

    Args:
        card: A product dict. Expected keys (all optional, missing keys
            are treated as worst-case for that dimension):
                rating       — number or string like "4.5 / 5"
                reviews      — number or string like "1,234"
                price        — number or string like "$24.99"
                availability — "in_stock" / "limited" / "out_of_stock"
                               (or boolean / 0|1 — see _normalise_availability)

    Returns:
        Integer 0-100 inclusive.
    """
    rating_norm       = _normalise_rating(card.get("rating"))
    reviews_norm      = _normalise_reviews(card.get("reviews"))
    price_norm        = _normalise_price(card.get("price"))
    availability_norm = _normalise_availability(card.get("availability"))

    raw = (
        rating_norm       * W_RATING +
        reviews_norm      * W_REVIEWS +
        price_norm        * W_PRICE +
        availability_norm * W_AVAILABILITY
    )

    return int(_clamp(raw, 0, 100))


# ── Internal utilities ───────────────────────────────────────

def _parse_first_number(value: Any) -> float | None:
    """Extract the first number from `value`. Returns None if none found."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).replace(",", "")  # strip thousand separators
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _clamp(value: float, low: float, high: float) -> float:
    """Constrain value to the inclusive range [low, high]."""
    return max(low, min(high, value))