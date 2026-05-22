# api/routes/amazon.py
# ──────────────────────────────────────────────────────────────
# GET /api/amazon?q={query}
# Returns Amazon product search results.
# Story: PROJ-111
# ──────────────────────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Query

from api.schemas import AmazonResponse, Product
from skills.amazon import AmazonSkill

router = APIRouter(prefix="/api", tags=["amazon"])

# Single skill instance — browser/Claude client state is class-level, safe to reuse.
_amazon_skill = AmazonSkill()


@router.get("/amazon", response_model=AmazonResponse)
def search_amazon(
    q: str = Query(..., min_length=1, description="Product search query, e.g. 'wireless headphones'"),
) -> AmazonResponse:
    """Search Amazon for products. Returns up to 10 results."""
    # Call _run_normal_search directly to bypass auto-routing into
    # comparison/review/opportunity modes — this endpoint is plain product search.
    # (PROJ-166 should eventually expose this as a public method.)
    result = _amazon_skill._run_normal_search(q)

    if not result.success and not result.results:
        raise HTTPException(
            status_code=502,
            detail=result.error or "Amazon search failed.",
        )

    products = [_to_product(r) for r in result.results]
    return AmazonResponse(query=q, count=len(products), products=products)


def _to_product(raw: dict) -> Product:
    """Map an Amazon skill result dict to the API's Product schema.

    Centralised here so PROJ-166's eventual ProductCard refactor only touches
    this one function rather than the route logic.
    """
    return Product(
        title  = raw.get("title", ""),
        price  = raw.get("price", ""),
        rating = raw.get("rating", ""),
        asin   = raw.get("asin", ""),
        url    = raw.get("link", ""),   # skill uses 'link', API spec uses 'url'
    )