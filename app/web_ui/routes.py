# app/web_ui/routes.py
# ──────────────────────────────────────────────────────────────
# FastAPI route definitions for the Agent Factory Web UI
# PROJ-140 + PROJ-146 (Dilraj Singh)
#
# Endpoints:
#   POST /query   — run a research query, return response + cards
#   GET  /history — last 20 messages from memory
#   GET  /status  — health check
# ──────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter
from pydantic import BaseModel

from agent.orchestrator import Orchestrator
from components.amazon_cards import ProductCard
from components.literature_cards import PaperCard
from skills.literature import LiteratureSkill

router = APIRouter()

# Shared orchestrator instance (one per process)
_orchestrator = Orchestrator()
# Dedicated skill instance for /literature — bypasses orchestrator routing
_lit_skill = LiteratureSkill()


# ── Pydantic models ────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    response: str
    cards: list[dict]
    type: str


class HistoryItem(BaseModel):
    timestamp: str
    query: str
    skill: str
    summary: str


class StatusResponse(BaseModel):
    status: str
    agent: str


class LiteratureRequest(BaseModel):
    topic: str


class PaperResult(BaseModel):
    title:     str
    authors:   str
    year:      str
    abstract:  str
    source:    str
    url:       str
    citations: int


class LiteratureResponse(BaseModel):
    query:     str
    total:     int
    papers:    list[PaperResult]
    synthesis: str
    error:     str


# ── Routes ─────────────────────────────────────────────────────
@router.post("/query", response_model=QueryResponse)
async def query_agent(body: QueryRequest):
    """
    Run a research query through the agent.
    Returns the text response plus typed result cards.

    Response schema:
        response  — human-readable agent answer
        cards     — list of ProductCard or PaperCard dicts
        type      — "amazon" | "literature" | "unknown"
    """
    rendered, result = _orchestrator.run(body.query)

    if result is None:
        return QueryResponse(response=rendered, cards=[], type="unknown")

    skill_type = result.skill_name
    cards: list[dict] = []

    if skill_type == "amazon" and result.results:
        for raw in result.results:
            try:
                card = ProductCard.from_skill_result(raw)
                cards.append(card.to_dict())
            except Exception:
                pass

    elif skill_type == "literature" and result.results:
        for raw in result.results:
            try:
                card = PaperCard.from_skill_result(raw)
                cards.append(card.to_dict())
            except Exception:
                pass

    return QueryResponse(
        response=rendered,
        cards=cards,
        type=skill_type if skill_type in ("amazon", "literature") else "unknown",
    )


@router.get("/history", response_model=list[HistoryItem])
async def get_history():
    """Return the last 20 queries from session memory."""
    history = _orchestrator.memory.get_history(20)
    return [
        HistoryItem(
            timestamp=h.get("timestamp", ""),
            query=h.get("query", ""),
            skill=h.get("skill", ""),
            summary=h.get("summary", ""),
        )
        for h in history
    ]


@router.post("/literature", response_model=LiteratureResponse)
async def search_literature(body: LiteratureRequest):
    """
    Search academic literature by topic.
    Calls LiteratureSkill directly — no orchestrator routing needed.

    Returns up to MAX_RESULTS papers with title, authors, year,
    abstract snippet, source, url, and citation count.
    If the topic contains synthesis/gap keywords the skill activates
    those modes automatically and the result is returned in `synthesis`.
    """
    result = _lit_skill(body.topic)

    papers: list[PaperResult] = []
    for raw in result.results:
        try:
            card = PaperCard.from_skill_result(raw)
            papers.append(PaperResult(
                title=card.title,
                authors=card.authors,
                year=card.year,
                abstract=card.truncate_abstract(300),
                source=card.source,
                url=card.url,
                citations=card.citations,
            ))
        except Exception:
            pass

    # Full structured synthesis/gap output takes precedence; fall back to the
    # always-on quick paragraph so the UI always has something to show.
    if result.metadata.get("synthesis_done") or result.metadata.get("gap_analysis_done"):
        synthesis = result.summary
    else:
        synthesis = result.metadata.get("quick_synthesis", "")

    return LiteratureResponse(
        query=body.topic,
        total=len(papers),
        papers=papers,
        synthesis=synthesis,
        error=result.error,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Health check — confirms API is running and agent is ready."""
    return StatusResponse(status="ok", agent="ready")
