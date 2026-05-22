# app/skills/literature_skill.py
# ──────────────────────────────────────────────────────────────
# PROJ-175: LiteratureSkill — arXiv + S2 + dedupe + synthesise → list[PaperCard]
# Orchestrates the modular fetchers and synthesizer.
# ──────────────────────────────────────────────────────────────

from app.skills.arxiv_fetcher import search_arxiv
from app.skills.semantic_scholar import search_semantic_scholar, get_forward_citations
from app.skills.literature_synthesizer import quick_synthesis, synthesise_papers, find_research_gaps
from app.skills.literature_cards import PaperCard
from config.settings import MAX_RESULTS

SYNTHESIS_PAPER_COUNT = 10

SYNTHESIS_TRIGGERS = {"synthesise", "synthesize", "synthesis", "overview",
                      "summarise papers", "summarize papers", "aggregate", "survey"}
GAP_TRIGGERS       = {"gap", "gaps", "missing", "unexplored", "future work",
                      "open problems", "what is missing", "research gap", "research gaps"}
CITATION_TRIGGERS  = {"cited by", "forward citation", "citations", "who cited",
                      "citing papers", "cite this", "citing works"}


def run(query: str) -> dict:
    """
    Main entry point. Returns:
      {
        success: bool,
        results: list[PaperCard],
        summary: str,
        error: str,
        metadata: dict,
      }
    """
    import re

    q_lower = query.lower()

    # ── Forward citation mode ─────────────────────────────────
    if any(t in q_lower for t in CITATION_TRIGGERS):
        return _run_citation_lookup(query)

    paper_count = SYNTHESIS_PAPER_COUNT if any(
        t in q_lower for t in SYNTHESIS_TRIGGERS | GAP_TRIGGERS
    ) else MAX_RESULTS

    results = []
    errors  = []

    # 1. arXiv
    try:
        arxiv_results = search_arxiv(query, max_results=paper_count)
        results.extend(arxiv_results)
    except Exception as e:
        errors.append(f"arXiv: {e}")

    # 2. Semantic Scholar (deduplicate by title)
    try:
        ss_results = search_semantic_scholar(query, limit=paper_count)
        existing   = {r["title"].lower() for r in results}
        for r in ss_results:
            if r["title"].lower() not in existing:
                results.append(r)
                existing.add(r["title"].lower())
    except Exception as e:
        errors.append(f"Semantic Scholar: {e}")

    results = results[:paper_count]

    # Quick synthesis paragraph (always-on)
    q_synthesis = ""
    if results:
        try:
            q_synthesis = quick_synthesis(query, results)
        except Exception as e:
            errors.append(f"Quick synthesis: {e}")

    # Deep synthesis
    synthesis_text = ""
    if any(t in q_lower for t in SYNTHESIS_TRIGGERS) and results:
        try:
            synthesis_text = synthesise_papers(query, results)
        except Exception as e:
            errors.append(f"Synthesis: {e}")

    # Research gaps
    gaps_text = ""
    if any(t in q_lower for t in GAP_TRIGGERS) and results:
        try:
            gaps_text = find_research_gaps(query, results)
        except Exception as e:
            errors.append(f"Gap analysis: {e}")

    paper_cards = [PaperCard.from_skill_result(r) for r in results]

    summary = _build_summary(query, results)
    extras  = []
    if synthesis_text:
        extras.append(synthesis_text)
    if gaps_text:
        extras.append(gaps_text)
    if extras:
        summary = summary + "\n\n" + "\n\n".join(extras)

    return {
        "success":  len(results) > 0,
        "results":  paper_cards,
        "summary":  summary,
        "error":    "; ".join(errors) if errors else "",
        "metadata": {
            "total_found":       len(results),
            "synthesis_done":    bool(synthesis_text),
            "gap_analysis_done": bool(gaps_text),
            "quick_synthesis":   q_synthesis,
        },
    }


def _run_citation_lookup(query: str) -> dict:
    import re

    paper_id = None
    arxiv_match = re.search(r"ARXIV:([\d.v]+)", query, re.IGNORECASE)
    ss_match    = re.search(r"\b([0-9a-f]{40})\b", query)

    if arxiv_match:
        paper_id = f"ARXIV:{arxiv_match.group(1)}"
    elif ss_match:
        paper_id = ss_match.group(1)
    else:
        title_query = re.sub(
            r"(cited by|citations for|citations of|who cited|citing papers for"
            r"|forward citation|forward citations|citing works of)\s*",
            "", query, flags=re.IGNORECASE,
        ).strip()
        try:
            ss = search_semantic_scholar(title_query, limit=1)
            if ss and ss[0].get("paper_id"):
                paper_id = ss[0]["paper_id"]
        except Exception:
            pass

    if not paper_id:
        msg = "Could not find a paper ID. Try: 'citations for ARXIV:1706.03762'"
        return {"success": False, "results": [], "summary": msg, "error": msg, "metadata": {}}

    try:
        citing = get_forward_citations(paper_id)
    except Exception as e:
        msg = f"Citation fetch failed: {e}"
        return {"success": False, "results": [], "summary": msg, "error": msg, "metadata": {}}

    paper_cards = [PaperCard.from_skill_result(r) for r in citing]
    summary = (
        f"Found **{len(citing)} papers** citing `{paper_id}`."
        if citing else f"No citing papers found for `{paper_id}`."
    )
    return {
        "success":  len(citing) > 0,
        "results":  paper_cards,
        "summary":  summary,
        "error":    "",
        "metadata": {"source_paper_id": paper_id, "citing_count": len(citing)},
    }


def _build_summary(query: str, results: list[dict]) -> str:
    if not results:
        return (
            f"No papers found for \"{query}\". "
            "Try shorter or broader search terms."
        )
    years   = [r["year"] for r in results if r.get("year")]
    recent  = max(years) if years else "N/A"
    sources = ", ".join(set(r["source"] for r in results))
    return (
        f"Found {len(results)} papers for '{query}'. "
        f"Most recent: {recent}. Sources: {sources}."
    )
