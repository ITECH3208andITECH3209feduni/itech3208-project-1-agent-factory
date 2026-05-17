# api/routes/literature.py
# ──────────────────────────────────────────────────────────────
# GET /api/literature?q={query}
# Returns paper search results from arXiv, Semantic Scholar, PubMed.
# Story: PROJ-112
# ──────────────────────────────────────────────────────────────

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import require_api_key

from api.schemas import LiteratureResponse, Paper
from skills.literature import LiteratureSkill

router = APIRouter(prefix="/api", tags=["literature"])

# Instantiate once — skill state (Claude client) is class-level, safe to reuse.
_literature_skill = LiteratureSkill()


@router.get("/literature", response_model=LiteratureResponse)
def search_literature(
    q: str = Query(..., min_length=1, description="Search query, e.g. 'transformer attention'"),
    _auth: str = Depends(require_api_key),
) -> LiteratureResponse:
    """Search academic literature across arXiv, Semantic Scholar, and PubMed."""
    result = _literature_skill(q)  # __call__ adds timing + exception safety

    if not result.success and not result.results:
        raise HTTPException(
            status_code=502,
            detail=result.error or "Literature search failed across all sources.",
        )

    papers = [_to_paper(r) for r in result.results]
    return LiteratureResponse(query=q, count=len(papers), papers=papers)


def _to_paper(raw: dict) -> Paper:
    """Map a literature skill result dict to the API's Paper schema."""
    return Paper(
        title    = raw.get("title", ""),
        authors  = raw.get("authors", ""),
        year     = raw.get("year", ""),
        abstract = raw.get("abstract", ""),
        source   = raw.get("source", ""),
        url      = raw.get("link", ""),   # skill uses 'link', API spec uses 'url'
    )