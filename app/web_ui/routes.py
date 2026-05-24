# app/web_ui/routes.py
# ──────────────────────────────────────────────────────────────
# FastAPI route definitions for the Agent Factory Web UI
# PROJ-140 + PROJ-146 (Dilraj Singh)
#
# Endpoints:
#   POST /query        — run a research/shopping query, return cards
#   POST /literature   — dedicated literature search (PROJ-92–94)
#   POST /integrity    — academic integrity check (PROJ-184–186)
#   POST /seller       — Amazon seller tools (PROJ-187–190)
#   POST /export       — export results to PDF/Excel (PROJ-191)
#   GET  /history      — last 20 messages from memory
#   GET  /status       — health check
# ──────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent.orchestrator import Orchestrator
from components.amazon_cards import ProductCard
from components.literature_cards import PaperCard
from components.integrity_cards import IntegrityCard
from components.seller_cards import SupplierCard, CampaignCard
from skills.literature import LiteratureSkill
import app.skills.amazon_skill as amazon_ui_skill
from skills.academic_integrity import AcademicIntegritySkill
from skills.amazon_seller import AmazonSellerSkill
from skills.export import ExportSkill, export_to_pdf, export_to_excel

router = APIRouter()

# ── Shared skill instances (one per process) ───────────────────
_orchestrator  = Orchestrator()
_lit_skill     = LiteratureSkill()
_integrity     = AcademicIntegritySkill()
_seller        = AmazonSellerSkill()
_export        = ExportSkill()


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


class AmazonRequest(BaseModel):
    query: str


class AmazonResponse(BaseModel):
    query:    str
    total:    int
    cards:    list[dict]
    response: str
    type:     str
    error:    str


class IntegrityRequest(BaseModel):
    text: str
    mode: str = "auto"   # "auto" | "ai_detection" | "plagiarism" | "full_report"


class IntegrityResponse(BaseModel):
    mode:              str
    classification:    str
    ai_probability:    float
    confidence_score:  float
    perplexity_score:  float
    burstiness_score:  float
    similarity_score:  float
    risk_level:        str
    flagged_passages:  list[str]
    matched_sources:   list[dict]
    summary:           str
    word_count:        int
    error:             str


class SellerRequest(BaseModel):
    query: str


class SellerResponse(BaseModel):
    mode:    str
    results: list[dict]
    summary: str
    metadata: dict
    error:   str


class ExportRequest(BaseModel):
    data:   dict
    format: str = "pdf"    # "pdf" | "excel"


class ExportResponse(BaseModel):
    file_path: str
    format:    str
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

    elif skill_type == "amazon_seller" and result.results:
        mode = result.metadata.get("mode", "")
        for raw in result.results:
            try:
                if mode == "supplier_finder":
                    card = SupplierCard.from_skill_result(raw)
                else:
                    card = CampaignCard.from_skill_result(raw)
                cards.append(card.to_dict())
            except Exception:
                pass

    # Use mode-specific type for seller skill so the frontend can render correctly
    if skill_type == "amazon_seller":
        seller_mode = result.metadata.get("mode", "")
        response_type = "ppc_builder" if seller_mode == "ppc_builder" else "supplier_finder"
    else:
        response_type = skill_type if skill_type in ("amazon", "literature") else "unknown"

    return QueryResponse(
        response=rendered,
        cards=cards,
        type=response_type,
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


@router.post("/amazon", response_model=AmazonResponse)
async def search_amazon(body: AmazonRequest):
    """
    Search Amazon products by query.
    Calls app.skills.amazon_skill.search() directly (PROJ-166 adapter).

    Returns a list of ProductCard dicts plus a short summary.
    Always returns type="amazon"; cards=[] on failure with the
    error string populated.
    """
    result = amazon_ui_skill.search(body.query)

    cards = [c.to_dict() for c in result.get("results", [])]

    summary = result.get("summary") or ""
    if not summary:
        n = len(cards)
        if n == 0:
            summary = "No products found."
        elif n == 1:
            summary = "Found 1 product."
        else:
            summary = "Found " + str(n) + " products."

    return AmazonResponse(
        query=body.query,
        total=len(cards),
        cards=cards,
        response=summary,
        type="amazon",
        error=result.get("error", "") or "",
    )


@router.post("/integrity", response_model=IntegrityResponse)
async def check_integrity(body: IntegrityRequest):
    """
    Academic integrity check on submitted text.

    Modes (auto-detected or explicitly set via `mode` field):
        ai_detection  — PROJ-184: perplexity + burstiness + Claude classify
        plagiarism    — PROJ-185: DuckDuckGo phrase-match cross-check
        full_report   — PROJ-186: both combined with markdown risk report

    Minimum 50 words required.
    """
    # Build query string that the skill's mode detection understands
    mode_prefixes = {
        "ai_detection": "detect ai",
        "plagiarism":   "plagiarism check",
        "full_report":  "integrity report",
        "auto":         "detect ai",
    }
    prefix = mode_prefixes.get(body.mode, "detect ai")
    query  = f"{prefix}: {body.text}"

    result = _integrity(query)
    meta   = result.metadata

    return IntegrityResponse(
        mode=meta.get("mode", body.mode),
        classification=meta.get("classification", "Unknown"),
        ai_probability=meta.get("ai_probability", 0.0),
        confidence_score=meta.get("confidence_score", 0.0),
        perplexity_score=meta.get("perplexity_score", 0.0),
        burstiness_score=meta.get("burstiness_score", 0.0),
        similarity_score=meta.get("similarity_score", 0.0),
        risk_level=meta.get("risk_level", "low"),
        flagged_passages=meta.get("flagged_passages", []),
        matched_sources=meta.get("matched_sources", []),
        summary=result.summary,
        word_count=meta.get("word_count", 0),
        error=result.error,
    )


@router.post("/seller", response_model=SellerResponse)
async def seller_tools(body: SellerRequest):
    """
    Amazon Seller Intelligence — four tools in one endpoint.

    Query format:
        "find alibaba suppliers for: wireless earbuds"   → PROJ-187
        "build ppc campaign for: bamboo toothbrushes"   → PROJ-188
        "analyze product progress: ASIN B07XYZ123"      → PROJ-189
        "optimize profit: selling_price=24.99 cost_price=7.00" → PROJ-190
    """
    result = _seller(body.query)

    return SellerResponse(
        mode=result.metadata.get("mode", "unknown"),
        results=result.results,
        summary=result.summary,
        metadata=result.metadata,
        error=result.error,
    )


@router.post("/export", response_model=ExportResponse)
async def export_results(body: ExportRequest):
    """
    Export any skill result to PDF or Excel (PROJ-191).

    Pass the full SkillResult.to_dict() payload under `data`.
    Set `format` to "pdf" or "excel".
    Returns the path to the generated file.
    """
    try:
        if body.format.lower() == "excel":
            file_path = export_to_excel(body.data)
        else:
            file_path = export_to_pdf(body.data)

        return ExportResponse(
            file_path=file_path,
            format=body.format,
            error="",
        )
    except Exception as exc:
        return ExportResponse(
            file_path="",
            format=body.format,
            error=str(exc),
        )


@router.get("/export/download")
async def download_export(path: str):
    """
    Download a previously exported file by its path.
    GET /export/download?path=exports/result_20260515_123456.pdf
    """
    if not os.path.exists(path):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=os.path.basename(path))


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Health check — confirms API is running and agent is ready."""
    return StatusResponse(status="ok", agent="ready")
