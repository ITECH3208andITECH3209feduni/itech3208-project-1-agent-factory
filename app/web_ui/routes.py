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

router = APIRouter()

# Shared orchestrator instance (one per process)
_orchestrator = Orchestrator()


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


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Health check — confirms API is running and agent is ready."""
    return StatusResponse(status="ok", agent="ready")
