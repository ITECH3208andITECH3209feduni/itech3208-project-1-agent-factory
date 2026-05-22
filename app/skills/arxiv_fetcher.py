# app/skills/arxiv_fetcher.py
# ──────────────────────────────────────────────────────────────
# PROJ-176: arXiv fetcher — search_arxiv()
# Extracted from skills/literature.py for modular architecture.
# ──────────────────────────────────────────────────────────────

import re
import xml.etree.ElementTree as ET

import requests

from config.settings import ARXIV_BASE_URL, MAX_RESULTS, REQUEST_TIMEOUT


def _retry_get(url: str, params: dict = None, retries: int = 3, backoff: float = 2.0) -> requests.Response:
    """GET with exponential backoff. Raises on 429 exhaustion or connection failure."""
    import time

    last_error = None
    was_rate_limited = False
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                wait = backoff * (2 ** attempt)
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
        raise RuntimeError(f"arXiv rate-limited after {retries} attempts — try again in a minute.")
    raise last_error or Exception(f"Request failed after {retries} attempts")


def search_arxiv(query: str, max_results: int = None) -> list[dict]:
    """
    Search arXiv and return a list of paper dicts.

    Each dict contains: title, authors, year, abstract, link, source, paper_id, citations.
    """
    if max_results is None:
        max_results = MAX_RESULTS

    params = {
        "search_query": f"all:{query}",
        "start":        0,
        "max_results":  max_results,
        "sortBy":       "relevance",
        "sortOrder":    "descending",
    }
    resp = _retry_get(ARXIV_BASE_URL, params=params)

    ns   = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    out  = []

    for entry in root.findall("atom:entry", ns):
        title     = (entry.find("atom:title", ns).text or "").strip().replace("\n", " ")
        summary   = (entry.find("atom:summary", ns).text or "").strip()[:400]
        published = (entry.find("atom:published", ns).text or "")[:10]
        link_el   = entry.find("atom:id", ns)
        link      = link_el.text.strip() if link_el is not None else ""
        authors   = [
            a.find("atom:name", ns).text
            for a in entry.findall("atom:author", ns)
            if a.find("atom:name", ns) is not None
        ]

        arxiv_id = ""
        if link:
            m = re.search(r"arxiv\.org/abs/(.+)$", link)
            if m:
                arxiv_id = f"ARXIV:{m.group(1)}"

        out.append({
            "title":    title,
            "authors":  ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
            "year":     published[:4],
            "abstract": summary,
            "link":     link,
            "source":   "arXiv",
            "paper_id": arxiv_id,
            "citations": 0,
        })
    return out
