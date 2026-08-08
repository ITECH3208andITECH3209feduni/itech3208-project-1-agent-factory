"""
app.web.main — FastAPI application for Agent Factory (PROJ-299..303).

The ASGI entry point the container runs:

    uvicorn app.web.main:app --host 0.0.0.0 --port 8000

or, equivalently, `./run.sh serve`.

Endpoints:
    GET  /          service metadata
    GET  /health    liveness + readiness (used by the Docker HEALTHCHECK)
    POST /query     run a query through the agent
"""

import logging
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import settings

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("agent_factory.web")

SERVICE_NAME    = "agent-factory"
SERVICE_VERSION = os.environ.get("APP_VERSION", "3.0.0")
STARTED_AT      = time.time()

app = FastAPI(
    title="Agent Factory",
    version=SERVICE_VERSION,
    description="Research AI assistant — literature search and Amazon product research.",
)


# ── Orchestrator is built lazily ──────────────────────────────
# Constructing it instantiates the Anthropic client, which needs a key.
# Doing that at import time would make the container fail to start — and
# more importantly would make /health fail — purely because a key is
# missing, which is exactly when you most want the health endpoint to
# answer and tell you so.
_orchestrator = None


def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from agent.orchestrator import Orchestrator

        _orchestrator = Orchestrator()
    return _orchestrator


# ── Models ────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Natural-language query")
    save: bool = Field(False, description="Also write the result to outputs/")


class QueryResponse(BaseModel):
    query:    str
    skill:    str | None = None
    success:  bool
    summary:  str = ""
    results:  list[dict] = []
    error:    str = ""
    duration: float = 0.0
    saved_to: str | None = None


# ── Routes ────────────────────────────────────────────────────
@app.get("/")
def root() -> dict:
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "docs":    "/docs",
        "health":  "/health",
    }


@app.get("/health")
def health() -> JSONResponse:
    """
    Liveness and readiness in one.

    Always returns 200 while the process is serving — a container that is up
    but under-configured should not be killed and restarted in a loop, since
    restarting cannot supply a missing API key. Configuration problems are
    reported in the body as `degraded` with the specific reasons.
    """
    problems = settings.validate_env()

    # Only a missing Claude key actually stops the agent from answering.
    # The rest disable an optional feature.
    blocking = [p for p in problems if p.startswith("ANTHROPIC_API_KEY")]

    return JSONResponse(
        status_code=200,
        content={
            "status":         "degraded" if blocking else "ok",
            "service":        SERVICE_NAME,
            "version":        SERVICE_VERSION,
            "uptime_sec":     round(time.time() - STARTED_AT, 1),
            "checks": {
                "config": "fail" if blocking else "pass",
            },
            "warnings":       problems,
        },
    )


@app.post("/query", response_model=QueryResponse)
def run_query(req: QueryRequest) -> QueryResponse:
    """Route a query to the appropriate skill and return the result."""
    if settings.ANTHROPIC_API_KEY in ("", "YOUR_API_KEY_HERE"):
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is not configured; the agent cannot answer queries.",
        )

    try:
        orch = get_orchestrator()
        if req.save:
            _rendered, path, result = orch.run_and_save(req.query)
        else:
            _rendered, result = orch.run(req.query)
            path = None
    except Exception as exc:
        logger.exception("query failed: %r", req.query[:80])
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # A clarification request comes back with no SkillResult attached.
    if result is None:
        return QueryResponse(
            query=req.query, success=False, summary=_rendered, error="clarification_required"
        )

    return QueryResponse(
        query    = req.query,
        skill    = result.skill_name,
        success  = result.success,
        summary  = result.summary,
        results  = result.results,
        error    = result.error,
        duration = round(result.duration_sec, 3),
        saved_to = path,
    )
