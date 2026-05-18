# app/skills/literature_synthesizer.py
# ──────────────────────────────────────────────────────────────
# PROJ-178: Claude Haiku synthesis engine
# Returns {synthesis, gaps, citations} — extracted from skills/literature.py
# ──────────────────────────────────────────────────────────────

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_HAIKU_MODEL

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

_client = None


def _get_client():
    global _client
    if not _ANTHROPIC_AVAILABLE:
        return None
    if _client is None:
        try:
            _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except Exception:
            pass
    return _client


def quick_synthesis(query: str, results: list[dict]) -> str:
    """
    2-3 sentence Sonnet paragraph summarising the top-5 results.
    Runs on every successful search.
    """
    client = _get_client()
    if not client or not results:
        return ""

    top5 = results[:5]
    paper_list = "\n".join(
        f"[{i+1}] {r['title']} ({r.get('year', '?')}) — {r.get('authors', '?')}: "
        f"{r.get('abstract', '')[:200]}"
        for i, r in enumerate(top5)
    )

    prompt = (
        f"A researcher searched for: \"{query}\"\n\n"
        f"Top {len(top5)} papers found:\n{paper_list}\n\n"
        "Write a single paragraph of exactly 2–3 sentences that:\n"
        "1. Identifies the key themes across these papers\n"
        "2. Conveys what the literature reveals about this topic\n"
        "3. Gives the researcher immediate orientation\n\n"
        "Write only the paragraph — no headers, no bullet points, no preamble."
    )

    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=180,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


def synthesise_papers(query: str, results: list[dict]) -> str:
    """
    Multi-paper synthesis via Claude Haiku — themes, consensus, conflicts, key finding.
    """
    client = _get_client()
    if not client or not results:
        return ""

    paper_list = "\n\n".join(
        f"[{i+1}] **{r['title']}** ({r.get('year', '?')}) — {r.get('authors', '?')}\n"
        f"Abstract: {r.get('abstract', 'No abstract available.')}"
        for i, r in enumerate(results[:10])
    )

    prompt = f"""You are a research librarian. Synthesise the following {len(results[:10])} academic papers on the topic: \"{query}\"

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
        msg = client.messages.create(
            model=CLAUDE_HAIKU_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


def find_research_gaps(query: str, results: list[dict]) -> str:
    """
    Identify under-researched areas and future work directions via Claude Haiku.
    """
    client = _get_client()
    if not client or not results:
        return ""

    paper_list = "\n\n".join(
        f"[{i+1}] **{r['title']}** ({r.get('year', '?')})\n"
        f"Abstract: {r.get('abstract', 'No abstract available.')}"
        for i, r in enumerate(results[:10])
    )

    years = [r.get("year", "") for r in results if r.get("year", "").isdigit()]
    year_range = f"{min(years)}–{max(years)}" if years else "unknown range"

    prompt = f"""You are a research strategist analysing the literature on: \"{query}\"

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
        msg = client.messages.create(
            model=CLAUDE_HAIKU_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""
