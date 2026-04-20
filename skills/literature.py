# skills/literature.py
# ──────────────────────────────────────────────────────────────
# Literature Research Skill
# Sources: arXiv, Semantic Scholar, PubMed
# ──────────────────────────────────────────────────────────────

import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from skills.base_skill import BaseSkill, SkillResult
from config.settings import (
    ARXIV_BASE_URL,
    SEMANTIC_SCHOLAR_URL,
    PUBMED_SEARCH_URL,
    PUBMED_FETCH_URL,
    MAX_RESULTS,
    REQUEST_TIMEOUT,
)


class LiteratureSkill(BaseSkill):
    name        = "literature"
    description = (
        "Search academic papers, research articles, and scientific literature. "
        "Use when the user asks about research, papers, studies, journals, "
        "authors, citations, or any academic/scientific topic."
    )
    triggers = [
        "paper", "papers", "research", "study", "studies", "journal",
        "article", "author", "cite", "citation", "arxiv", "pubmed",
        "literature", "academic", "science", "findings", "review",
        "meta-analysis", "systematic review",
    ]

    def run(self, query: str) -> SkillResult:
        results = []
        errors  = []

        # ── 1. arXiv ──────────────────────────────────────────
        try:
            arxiv_results = self._search_arxiv(query)
            results.extend(arxiv_results)
        except Exception as e:
            errors.append(f"arXiv: {e}")

        # ── 2. Semantic Scholar ────────────────────────────────
        try:
            ss_results = self._search_semantic_scholar(query)
            # Merge — avoid duplicates by title
            existing_titles = {r["title"].lower() for r in results}
            for r in ss_results:
                if r["title"].lower() not in existing_titles:
                    results.append(r)
                    existing_titles.add(r["title"].lower())
        except Exception as e:
            errors.append(f"Semantic Scholar: {e}")

        # ── 3. PubMed (medical/life sciences queries) ──────────
        if any(kw in query.lower() for kw in ["medicine","health","clinical","drug","disease","patient","trial"]):
            try:
                pubmed_results = self._search_pubmed(query)
                existing_titles = {r["title"].lower() for r in results}
                for r in pubmed_results:
                    if r["title"].lower() not in existing_titles:
                        results.append(r)
            except Exception as e:
                errors.append(f"PubMed: {e}")

        results = results[:MAX_RESULTS]

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = len(results) > 0,
            results    = results,
            summary    = self._build_summary(query, results),
            error      = "; ".join(errors) if errors else "",
            metadata   = {
                "sources_queried": ["arXiv", "Semantic Scholar"] + (["PubMed"] if "PubMed" not in str(errors) else []),
                "total_found":     len(results),
            },
        )

    # ── arXiv ──────────────────────────────────────────────────
    def _search_arxiv(self, query: str) -> list[dict]:
        params = {
            "search_query": f"all:{quote_plus(query)}",
            "start":        0,
            "max_results":  MAX_RESULTS,
            "sortBy":       "relevance",
            "sortOrder":    "descending",
        }
        resp = requests.get(ARXIV_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

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
            out.append({
                "title":    title,
                "authors":  ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                "year":     published[:4],
                "abstract": summary,
                "link":     link,
                "source":   "arXiv",
            })
        return out

    # ── Semantic Scholar ───────────────────────────────────────
    def _search_semantic_scholar(self, query: str) -> list[dict]:
        params = {
            "query":  query,
            "limit":  MAX_RESULTS,
            "fields": "title,authors,year,abstract,url,citationCount",
        }
        resp = requests.get(SEMANTIC_SCHOLAR_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        out  = []
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
            })
        return out

    # ── PubMed ─────────────────────────────────────────────────
    def _search_pubmed(self, query: str) -> list[dict]:
        # Step 1: get IDs
        search_resp = requests.get(
            PUBMED_SEARCH_URL,
            params={"db": "pubmed", "term": query, "retmax": 5, "retmode": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        search_resp.raise_for_status()
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        # Step 2: fetch details
        fetch_resp = requests.get(
            PUBMED_FETCH_URL,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            timeout=REQUEST_TIMEOUT,
        )
        fetch_resp.raise_for_status()
        root = ET.fromstring(fetch_resp.text)
        out  = []

        for article in root.findall(".//PubmedArticle"):
            title_el   = article.find(".//ArticleTitle")
            abstract_el= article.find(".//AbstractText")
            year_el    = article.find(".//PubDate/Year")
            pmid_el    = article.find(".//PMID")
            author_els = article.findall(".//Author")

            title    = title_el.text    if title_el    is not None else ""
            abstract = abstract_el.text if abstract_el is not None else ""
            year     = year_el.text     if year_el     is not None else ""
            pmid     = pmid_el.text     if pmid_el     is not None else ""

            authors = []
            for a in author_els[:3]:
                last  = a.find("LastName")
                first = a.find("ForeName")
                if last is not None:
                    name = last.text
                    if first is not None:
                        name += f" {first.text}"
                    authors.append(name)

            out.append({
                "title":    title or "",
                "authors":  ", ".join(authors) + (" et al." if len(author_els) > 3 else ""),
                "year":     year,
                "abstract": (abstract or "")[:400],
                "link":     f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source":   "PubMed",
            })
        return out

    # ── Summary builder ────────────────────────────────────────
    def _build_summary(self, query: str, results: list[dict]) -> str:
        if not results:
            return f"No papers found for '{query}'."
        years  = [r["year"] for r in results if r.get("year")]
        recent = max(years) if years else "N/A"
        return (
            f"Found {len(results)} papers for '{query}'. "
            f"Most recent: {recent}. "
            f"Sources: {', '.join(set(r['source'] for r in results))}."
        )
