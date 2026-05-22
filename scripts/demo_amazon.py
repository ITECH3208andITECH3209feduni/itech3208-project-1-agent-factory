"""
PROJ-173: Amazon skill demo.

Runs three product queries through AmazonSkill and prints a formatted
table of results plus timing for each. Intended as a 30-second showcase
for sprint review.

Usage:
    python scripts/demo_amazon.py

Requires:
    pip install tabulate
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Make the project root importable when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tabulate import tabulate  # noqa: E402

from skills.amazon import AmazonSkill  # noqa: E402


QUERIES = [
    "wireless headphones",
    "mechanical keyboard",
    "ergonomic office chair",
]

# 'score' is computed in this demo from rating x log1p(reviews) + prime bonus.
# Once PROJ-166/169 land, replace _compute_score with product.get('score').
TABLE_HEADERS = ["rank", "title", "price", "rating", "score*", "source"]
TITLE_MAX_LEN = 60


import math
import re


def _parse_float(value):
    """Pull the first number out of a string like '4.5 / 5' or '1,234'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[\d,]+\.?\d*", str(value).replace(",", ""))
    return float(match.group()) if match else None


def _compute_score(product):
    """Placeholder score: rating x log1p(reviews) + prime bonus."""
    rating = _parse_float(product.get("rating")) or 0.0
    reviews = _parse_float(product.get("reviews")) or 0.0
    prime_bonus = 5.0 if product.get("prime") else 0.0
    return rating * math.log1p(reviews) + prime_bonus


def _truncate(value: str, max_len: int = TITLE_MAX_LEN) -> str:
    """Trim long strings with an ellipsis so the table doesn't blow up."""
    if not value:
        return "-"
    value = str(value).strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "..."


def _format_field(value) -> str:
    """Render a field for the table, using a dash for missing data."""
    if value is None or value == "":
        return "-"
    return str(value)


def _build_rows(products, fallback_source):
    rows = []
    for rank, product in enumerate(products, start=1):
        score = _compute_score(product)
        rows.append(
            [
                rank,
                _truncate(product.get("title", "")),
                _format_field(product.get("price")),
                _format_field(product.get("rating")),
                f"{score:.2f}",
                product.get("source") or fallback_source,
            ]
        )
    return rows


def _run_query(skill, query):
    """Run one query. Returns (products, elapsed_seconds, source_label)."""
    start = time.perf_counter()
    try:
        result = skill(query)  # BaseSkill.__call__ swallows exceptions for us
    except Exception as exc:
        elapsed = time.perf_counter() - start
        print(f"  ! Query failed: {exc}")
        return [], elapsed, "-"

    elapsed = time.perf_counter() - start

    if not getattr(result, "success", False):
        err = getattr(result, "error", None) or "no results"
        print(f"  ! Query unsuccessful: {err}")
        return [], elapsed, "-"

    products = getattr(result, "results", []) or []
    metadata = getattr(result, "metadata", {}) or {}
    source = metadata.get("source", "amazon")
    return products, elapsed, source


def _avg_score(all_products):
    if not all_products:
        return 0.0
    scores = [_compute_score(p) for p in all_products]
    return sum(scores) / len(scores)


def main():
    print("Amazon skill demo - PROJ-173")
    print("=" * 60)

    skill = AmazonSkill()

    total_start = time.perf_counter()
    all_products = []

    for query in QUERIES:
        print(f"\nQuery: {query!r}")
        products, elapsed, source = _run_query(skill, query)
        all_products.extend(products)

        if products:
            rows = _build_rows(products, source)
            print(tabulate(rows, headers=TABLE_HEADERS, tablefmt="github"))
        else:
            print("  (no results)")

        print(f"  -> {elapsed:.2f}s, {len(products)} results")

    total_elapsed = time.perf_counter() - total_start

    print("\n" + "=" * 60)
    print(
        f"{len(QUERIES)} queries, "
        f"{len(all_products)} products found, "
        f"avg score {_avg_score(all_products):.2f}, "
        f"total {total_elapsed:.2f}s"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())