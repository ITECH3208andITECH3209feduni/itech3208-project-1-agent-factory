# app/skills/semantic_scholar.py
# ──────────────────────────────────────────────────────────────
# PROJ-177: Semantic Scholar API with 429 retry (2s sleep)
# Extracted from skills/literature.py for modular architecture.
# ──────────────────────────────────────────────────────────────

import time

import requests

from config.settings import SEMANTIC_SCHOLAR_URL, MAX_RESULTS, REQUEST_TIMEOUT

SEMANTIC_SCHOLAR_CITATIONS_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
)


def _retry_get(url: str, params: dict = None, retries: int = 3, backoff: float = 2.0) -> requests.Response:
    """GET with 429 retry using 2s sleep (Semantic Scholar rate-limit spec)."""
    last_error = None
    was_rate_limited = False
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                wait = backoff * (2 ** attempt)   # 2s, 4s, 8s
                time.sleep(wait)
                last_error = Exception(f"HTTP 429 (waited {wait}s)")
                was_rate_limited = True
                continue
            was_rate_limited = False
            resp.raise_for_status()
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = e
            was_rate_limited = False
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    if was_rate_limited:
        raise RuntimeError(
            f"Semantic Scholar rate-limited after {retries} attempts — try again in a minute."
        )
    raise last_error or Exception(f"Request failed after {retries} attempts")


def search_semantic_scholar(query: str, limit: int = None) -> list[dict]:
    """
    Search Semantic Scholar and return a list of paper dicts.

    Each dict contains: title, authors, year, abstract, link, source, citations, paper_id.
    """
    if limit is None:
        limit = MAX_RESULTS

    params = {
        "query":  query,
        "limit":  limit,
        "fields": "title,authors,year,abstract,url,citationCount,paperId",
    }
    resp = _retry_get(SEMANTIC_SCHOLAR_URL, params=params)
    data = resp.json().get("data", [])

    out = []
    for paper in data:
        authors = [a.get("name", "") for a in paper.get("authors", [])]
        out.append({
            "title":    paper.get("title", ""),
            "authors":  ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
            "year":     str(paper.get("year") or ""),
            "abstract": (paper.get("abstract") or "")[:400],
            "link":     paper.get("url", ""),
            "source":   "Semantic Scholar",
            "citations": paper.get("citationCount", 0),
            "paper_id": paper.get("paperId", ""),
        })
    return out


def get_forward_citations(paper_id: str, limit: int = 20) -> list[dict]:
    """
    Return papers that cite the given paper_id via Semantic Scholar citations API.
    Results are sorted by citation count descending.
    """
    url    = SEMANTIC_SCHOLAR_CITATIONS_URL.format(paper_id=paper_id)
    params = {
        "fields": "title,authors,year,url,citationCount,paperId",
        "limit":  limit,
    }
    resp = _retry_get(url, params=params)
    data = resp.json().get("data", [])

    out = []
    for item in data:
        paper = item.get("citingPaper", {})
        if not paper:
            continue
        authors = [a.get("name", "") for a in paper.get("authors", [])]
        out.append({
            "title":    paper.get("title", ""),
            "authors":  ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
            "year":     str(paper.get("year") or ""),
            "abstract": "",
            "link":     paper.get("url", ""),
            "source":   "Semantic Scholar (citing)",
            "citations": paper.get("citationCount", 0),
            "paper_id": paper.get("paperId", ""),
        })

    out.sort(key=lambda x: x.get("citations", 0), reverse=True)
    return out
