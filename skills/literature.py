# skills/literature.py
# ──────────────────────────────────────────────────────────────
# Literature Research Skill
# Sources: arXiv, Semantic Scholar, PubMed
#
# Fix (PROJ-81): Added retry + exponential backoff for 429 rate
#   limits and connection errors on all API calls.
#
# Sprint 1 Enhancements:
#   PROJ-92: Multi-paper synthesis aggregator (8–10 papers)
#   PROJ-93: Claude AI research gap finder
#   PROJ-94: Forward citation lookup via Semantic Scholar API
# ──────────────────────────────────────────────────────────────

import time
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from skills.base_skill import BaseSkill, SkillResult
from config.settings import (
    ARXIV_BASE_URL,
    SEMANTIC_SCHOLAR_URL,
    PUBMED_SEARCH_URL,
    PUBMED_FETCH_URL,
    MAX_RESULTS,
    REQUEST_TIMEOUT,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
)

# How many papers to fetch for synthesis (PROJ-92) — more than normal MAX_RESULTS
SYNTHESIS_PAPER_COUNT = 10

# Semantic Scholar citations endpoint
SEMANTIC_SCHOLAR_CITATIONS_URL = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
SEMANTIC_SCHOLAR_PAPER_URL     = "https://api.semanticscholar.org/graph/v1/paper/search"

# Trigger keywords for each enhanced mode
SYNTHESIS_TRIGGERS  = {"synthesise", "synthesize", "synthesis", "overview", "summarise papers",
                        "summarize papers", "aggregate", "survey"}
GAP_TRIGGERS        = {"gap", "gaps", "missing", "unexplored", "future work", "open problems",
                        "what is missing", "research gap", "research gaps"}
CITATION_TRIGGERS   = {"cited by", "forward citation", "citations", "who cited",
                        "citing papers", "cite this", "citing works"}


class LiteratureSkill(BaseSkill):
    name        = "literature"
    description = (
        "Search academic papers, research articles, and scientific literature. "
        "Use when the user asks about research, papers, studies, journals, "
        "authors, citations, or any academic/scientific topic. "
        "Also handles multi-paper synthesis, research gap analysis, "
        "and forward citation lookup."
    )
    triggers = [
        "paper", "papers", "research", "study", "studies", "journal",
        "article", "author", "cite", "citation", "arxiv", "pubmed",
        "literature", "academic", "science", "findings", "review",
        "meta-analysis", "systematic review", "synthesise", "synthesis",
        "research gap", "gaps", "forward citation", "cited by",
    ]

    _claude_client = None

    # ── Claude client ─────────────────────────────────────────
    @classmethod
    def _get_claude(cls):
        """Lazy-load Claude client once."""
        if not ANTHROPIC_AVAILABLE:
            return None
        if cls._claude_client is None:
            try:
                cls._claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except Exception:
                pass
        return cls._claude_client

    # ── Retry helper ──────────────────────────────────────────
    def _retry_get(self, url: str, params: dict = None, retries: int = 3, backoff: float = 2.0) -> requests.Response:
        """GET with automatic retry and exponential backoff.
        Handles 429 rate limits and transient connection / timeout errors."""
        last_error = None
        for attempt in range(retries):
            try:
                resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 429:
                    wait = backoff * (2 ** attempt)   # 2s, 4s, 8s
                    time.sleep(wait)
                    last_error = Exception(f"429 rate-limited (waited {wait}s before retry)")
                    continue
                resp.raise_for_status()
                return resp
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(backoff * (attempt + 1))
        raise last_error or Exception(f"Request failed after {retries} attempts")

    # ── Main entry point ──────────────────────────────────────
    def run(self, query: str) -> SkillResult:
        q_lower = query.lower()

        # ── Mode: Forward citations (PROJ-94) ─────────────────
        if any(t in q_lower for t in CITATION_TRIGGERS):
            return self._run_citation_lookup(query)

        # Determine how many papers to fetch
        paper_count = SYNTHESIS_PAPER_COUNT if any(
            t in q_lower for t in SYNTHESIS_TRIGGERS | GAP_TRIGGERS
        ) else MAX_RESULTS

        results = []
        errors  = []

        # ── 1. arXiv ─────────────────────────────────────────
        try:
            arxiv_results = self._search_arxiv(query, max_results=paper_count)
            results.extend(arxiv_results)
        except Exception as e:
            errors.append(f"arXiv: {e}")

        # ── 2. Semantic Scholar ───────────────────────────────
        try:
            ss_results = self._search_semantic_scholar(query, limit=paper_count)
            existing_titles = {r["title"].lower() for r in results}
            for r in ss_results:
                if r["title"].lower() not in existing_titles:
                    results.append(r)
                    existing_titles.add(r["title"].lower())
        except Exception as e:
            errors.append(f"Semantic Scholar: {e}")

        # ── 3. PubMed (medical/life sciences queries) ─────────
        if any(kw in q_lower for kw in ["medicine", "health", "clinical", "drug",
                                         "disease", "patient", "trial"]):
            try:
                pubmed_results = self._search_pubmed(query)
                existing_titles = {r["title"].lower() for r in results}
                for r in pubmed_results:
                    if r["title"].lower() not in existing_titles:
                        results.append(r)
            except Exception as e:
                errors.append(f"PubMed: {e}")

        results = results[:paper_count]

        # ── Mode: Multi-paper synthesis (PROJ-92) ─────────────
        synthesis_text = ""
        if any(t in q_lower for t in SYNTHESIS_TRIGGERS) and results:
            try:
                synthesis_text = self._synthesise_papers(query, results)
            except Exception as e:
                errors.append(f"Synthesis: {e}")

        # ── Mode: Research gap finder (PROJ-93) ───────────────
        gaps_text = ""
        if any(t in q_lower for t in GAP_TRIGGERS) and results:
            try:
                gaps_text = self._find_research_gaps(query, results)
            except Exception as e:
                errors.append(f"Gap analysis: {e}")

        # Build final summary
        base_summary = self._build_summary(query, results)
        extra_sections = []
        if synthesis_text:
            extra_sections.append(synthesis_text)
        if gaps_text:
            extra_sections.append(gaps_text)

        final_summary = base_summary
        if extra_sections:
            final_summary = base_summary + "\n\n" + "\n\n".join(extra_sections)

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = len(results) > 0,
            results    = results,
            summary    = final_summary,
            error      = "; ".join(errors) if errors else "",
            metadata   = {
                "sources_queried": ["arXiv", "Semantic Scholar"] + (
                    ["PubMed"] if any(
                        kw in q_lower for kw in ["medicine", "health", "clinical",
                                                   "drug", "disease", "patient", "trial"]
                    ) else []
                ),
                "total_found":      len(results),
                "synthesis_done":   bool(synthesis_text),
                "gap_analysis_done": bool(gaps_text),
            },
        )

    # ── arXiv ─────────────────────────────────────────────────
    def _search_arxiv(self, query: str, max_results: int = None) -> list[dict]:
        if max_results is None:
            max_results = MAX_RESULTS
        params = {
            "search_query": f"all:{quote_plus(query)}",
            "start":        0,
            "max_results":  max_results,
            "sortBy":       "relevance",
            "sortOrder":    "descending",
        }
        resp = self._retry_get(ARXIV_BASE_URL, params=params)

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

            # Extract arXiv paper ID from URL for forward citation lookups (PROJ-94)
            arxiv_id = ""
            if link:
                import re
                m = re.search(r"arxiv\.org/abs/(.+)$", link)
                if m:
                    arxiv_id = f"ARXIV:{m.group(1)}"

            out.append({
                "title":     title,
                "authors":   ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                "year":      published[:4],
                "abstract":  summary,
                "link":      link,
                "source":    "arXiv",
                "paper_id":  arxiv_id,
                "citations": 0,
            })
        return out

    # ── Semantic Scholar ──────────────────────────────────────
    def _search_semantic_scholar(self, query: str, limit: int = None) -> list[dict]:
        if limit is None:
            limit = MAX_RESULTS
        params = {
            "query":  query,
            "limit":  limit,
            "fields": "title,authors,year,abstract,url,citationCount,paperId",
        }
        resp = self._retry_get(SEMANTIC_SCHOLAR_URL, params=params)
        data = resp.json().get("data", [])
        out  = []
        for paper in data:
            authors = [a.get("name", "") for a in paper.get("authors", [])]
            out.append({
                "title":     paper.get("title", ""),
                "authors":   ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                "year":      str(paper.get("year") or ""),
                "abstract":  (paper.get("abstract") or "")[:400],
                "link":      paper.get("url", ""),
                "source":    "Semantic Scholar",
                "citations": paper.get("citationCount", 0),
                "paper_id":  paper.get("paperId", ""),
            })
        return out

    # ── PubMed ────────────────────────────────────────────────
    def _search_pubmed(self, query: str) -> list[dict]:
        search_resp = self._retry_get(
            PUBMED_SEARCH_URL,
            params={"db": "pubmed", "term": query, "retmax": 5, "retmode": "json"},
        )
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        fetch_resp = self._retry_get(
            PUBMED_FETCH_URL,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        )
        root = ET.fromstring(fetch_resp.text)
        out  = []

        for article in root.findall(".//PubmedArticle"):
            title_el    = article.find(".//ArticleTitle")
            abstract_el = article.find(".//AbstractText")
            year_el     = article.find(".//PubDate/Year")
            pmid_el     = article.find(".//PMID")
            author_els  = article.findall(".//Author")

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
                "title":     title or "",
                "authors":   ", ".join(authors) + (" et al." if len(author_els) > 3 else ""),
                "year":      year,
                "abstract":  (abstract or "")[:400],
                "link":      f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source":    "PubMed",
                "citations": 0,
                "paper_id":  f"PMID:{pmid}" if pmid else "",
            })
        return out

    # ── Multi-paper synthesis (PROJ-92) ───────────────────────
    def _synthesise_papers(self, query: str, results: list[dict]) -> str:
        """Use Claude to synthesise findings across 8–10 papers into a cohesive overview."""
        client = self._get_claude()
        if not client or not results:
            return ""

        # Build a structured input for Claude
        paper_list = "\n\n".join(
            f"[{i+1}] **{r['title']}** ({r.get('year','?')}) — {r.get('authors','?')}\n"
            f"Abstract: {r.get('abstract','No abstract available.')}"
            for i, r in enumerate(results[:10])
        )

        prompt = f"""You are a research librarian. Synthesise the following {len(results[:10])} academic papers on the topic: "{query}"

Papers:
{paper_list}

Write a structured synthesis that:
1. Identifies the 3–4 main themes that emerge across these papers
2. Highlights where papers AGREE on key findings
3. Highlights where papers DISAGREE or show conflicting results
4. Notes methodological approaches used across the papers
5. Identifies the most cited / most impactful finding

Format as:
## Cross-Paper Synthesis: {query}

### Main Themes
<bullet points of 3-4 themes>

### Areas of Consensus
<2-3 sentences>

### Conflicting Findings
<2-3 sentences, or "No major conflicts identified" if papers are aligned>

### Methodological Approaches
<1-2 sentences>

### Key Finding
<1 sentence — the single most important takeaway across all papers>

Keep the synthesis concise but insightful (under 400 words)."""

        try:
            message = client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = 600,
                messages   = [{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return ""

    # ── Research gap finder (PROJ-93) ─────────────────────────
    def _find_research_gaps(self, query: str, results: list[dict]) -> str:
        """Use Claude to identify under-researched areas and future work directions."""
        client = self._get_claude()
        if not client or not results:
            return ""

        paper_list = "\n\n".join(
            f"[{i+1}] **{r['title']}** ({r.get('year','?')})\n"
            f"Abstract: {r.get('abstract','No abstract available.')}"
            for i, r in enumerate(results[:10])
        )

        years = [r.get("year","") for r in results if r.get("year","").isdigit()]
        year_range = f"{min(years)}–{max(years)}" if years else "unknown range"

        prompt = f"""You are a research strategist analysing the literature on: "{query}"

The papers below span {year_range}. Based on what IS covered, identify what is NOT yet covered — the research gaps, open problems, and future directions.

Papers reviewed:
{paper_list}

Respond with exactly this structure:

## Research Gaps & Future Directions: {query}

### Under-Researched Areas
- <gap 1>
- <gap 2>
- <gap 3>

### Methodological Limitations in Current Research
- <limitation 1>
- <limitation 2>

### Suggested Future Research Directions
- <direction 1>
- <direction 2>
- <direction 3>

### Emerging Questions
<1–2 sentences on the most pressing open question in this field>

Be specific and grounded in what the abstracts actually discuss (or don't discuss). Under 350 words."""

        try:
            message = client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = 500,
                messages   = [{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return ""

    # ── Forward citation lookup (PROJ-94) ─────────────────────
    def _run_citation_lookup(self, query: str) -> SkillResult:
        """
        Look up papers that CITE a given paper via Semantic Scholar.
        Accepts queries like:
          - "citations for Attention is All You Need"
          - "who cited ARXIV:1706.03762"
          - "forward citations of [paper title]"
        """
        import re

        # Try to extract a Semantic Scholar paper ID or arXiv ID from the query
        paper_id = None
        arxiv_match = re.search(r"ARXIV:([\d.v]+)", query, re.IGNORECASE)
        ss_match    = re.search(r"\b([0-9a-f]{40})\b", query)  # 40-char hex SS paper ID

        if arxiv_match:
            paper_id = f"ARXIV:{arxiv_match.group(1)}"
        elif ss_match:
            paper_id = ss_match.group(1)
        else:
            # No explicit ID — search for the paper title first
            title_query = re.sub(
                r"(cited by|citations for|citations of|who cited|citing papers for"
                r"|forward citation|forward citations|citing works of)\s*",
                "", query, flags=re.IGNORECASE
            ).strip()

            if not title_query:
                return SkillResult(
                    skill_name=self.name, query=query, success=False,
                    error="Could not extract a paper title or ID to look up citations for.",
                )

            # Search for the paper to get its ID
            try:
                ss_results = self._search_semantic_scholar(title_query, limit=1)
                if ss_results and ss_results[0].get("paper_id"):
                    paper_id = ss_results[0]["paper_id"]
                else:
                    return SkillResult(
                        skill_name=self.name, query=query, success=False,
                        error=f"Could not find paper '{title_query}' in Semantic Scholar.",
                    )
            except Exception as e:
                return SkillResult(
                    skill_name=self.name, query=query, success=False, error=str(e),
                )

        # Now fetch forward citations
        try:
            citing_papers = self._get_forward_citations(paper_id)
        except Exception as e:
            return SkillResult(
                skill_name=self.name, query=query, success=False, error=str(e),
            )

        summary = (
            f"Found **{len(citing_papers)} papers** that cite paper `{paper_id}`.\n"
            + (
                "\n".join(
                    f"- {p['title']} ({p.get('year','?')}) by {p.get('authors','?')} — {p.get('link','')}"
                    for p in citing_papers[:10]
                ) if citing_papers else "No citing papers found in Semantic Scholar."
            )
        )

        return SkillResult(
            skill_name = self.name,
            query      = query,
            success    = len(citing_papers) > 0,
            results    = citing_papers,
            summary    = summary,
            metadata   = {
                "source":          "Semantic Scholar",
                "source_paper_id": paper_id,
                "citing_count":    len(citing_papers),
                "mode":            "forward_citations",
            },
        )

    def _get_forward_citations(self, paper_id: str, limit: int = 20) -> list[dict]:
        """
        Retrieve papers that cite `paper_id` via the Semantic Scholar citations API.

        Endpoint: GET /paper/{paper_id}/citations
        Returns list of dicts matching the standard paper dict schema.
        """
        url    = SEMANTIC_SCHOLAR_CITATIONS_URL.format(paper_id=paper_id)
        params = {
            "fields": "title,authors,year,url,citationCount,paperId",
            "limit":  limit,
        }

        resp = self._retry_get(url, params=params)
        data = resp.json().get("data", [])

        out = []
        for item in data:
            # Each item has a "citingPaper" key
            paper = item.get("citingPaper", {})
            if not paper:
                continue
            authors = [a.get("name", "") for a in paper.get("authors", [])]
            out.append({
                "title":     paper.get("title", ""),
                "authors":   ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                "year":      str(paper.get("year") or ""),
                "abstract":  "",   # not fetched in citation list to keep it fast
                "link":      paper.get("url", ""),
                "source":    "Semantic Scholar (citing)",
                "citations": paper.get("citationCount", 0),
                "paper_id":  paper.get("paperId", ""),
            })

        # Sort by citation count descending (most influential citing papers first)
        out.sort(key=lambda x: x.get("citations", 0), reverse=True)
        return out

    # ── Summary builder ───────────────────────────────────────
    def _build_summary(self, query: str, results: list[dict]) -> str:
        if not results:
            return f"No papers found for '{query}'."

        years  = [r["year"] for r in results if r.get("year")]
        recent = max(years) if years else "N/A"

        # Highlight highly-cited papers if available
        high_cited = [r for r in results if r.get("citations", 0) > 100]
        cited_note = (
            f" {len(high_cited)} papers with 100+ citations." if high_cited else ""
        )

        return (
            f"Found {len(results)} papers for '{query}'. "
            f"Most recent: {recent}.{cited_note} "
            f"Sources: {', '.join(set(r['source'] for r in results))}."
        )
