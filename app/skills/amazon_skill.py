# app/skills/amazon_skill.py
# PROJ-166: AmazonSkill adapter - wraps skills.amazon.AmazonSkill,
# normalises raw product dicts into ProductCard objects, sorts by
# score, returns top 10. Mirrors the shape of literature_skill.run().

from app.skills.amazon_cards import ProductCard
from skills.amazon import AmazonSkill as _AmazonSkill

MAX_RESULTS = 10


def search(query: str) -> dict:
    """Web-UI-facing entry point for Amazon product search.

    Returns a dict with keys: success, results (list[ProductCard]),
    summary, error, metadata. Never raises - failures surface as
    success=False with an error string and empty results.
    """
    try:
        skill = _AmazonSkill()
        result = skill(query)
    except Exception as e:
        return _empty_response(error=f"Skill invocation failed: {e}")

    if not getattr(result, "success", False):
        return _empty_response(
            error=getattr(result, "error", "") or "Skill returned no results",
            metadata=dict(getattr(result, "metadata", {}) or {}),
        )

    raw_products = getattr(result, "results", []) or []

    cards = []
    for raw in raw_products:
        try:
            cards.append(ProductCard.from_skill_result(raw))
        except Exception:
            continue

    cards.sort(key=lambda c: c.score, reverse=True)
    cards = cards[:MAX_RESULTS]

    return {
        "success":  len(cards) > 0,
        "results":  cards,
        "summary":  getattr(result, "summary", "") or "",
        "error":    getattr(result, "error", "") or "",
        "metadata": dict(getattr(result, "metadata", {}) or {}),
    }


def _empty_response(error: str = "", metadata: dict | None = None) -> dict:
    return {
        "success":  False,
        "results":  [],
        "summary":  "",
        "error":    error,
        "metadata": metadata or {},
    }
