"""
app.web.main — FastAPI application for Agent Factory (PROJ-299..303).

The ASGI entry point the container runs:

    uvicorn app.web.main:app --host 0.0.0.0 --port 8000

or, equivalently, `./run.sh serve`.

Endpoints:
    GET  /                    service metadata
    GET  /health              liveness + readiness (used by the Docker HEALTHCHECK)
    POST /query               run a query through the agent
    GET  /skills              registered skill manifests (PROJ-334..338)
    GET  /skills/{name}       one manifest
    GET  /skills/{name}/tools that skill's tools
    GET  /ui                  minimal web UI with a skills sidebar
"""

import logging
import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from config import settings
from skills.manifest_loader import discover_manifests, get_manifest

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
        "skills":  "/skills",
        "ui":      "/ui",
    }


# ── Skills registry (PROJ-334..338) ───────────────────────────
def _public_manifest(manifest: dict) -> dict:
    """
    Strip internals before publishing a manifest over HTTP.

    `_source` is a local filename and `_errors` are for operators, not API
    consumers. Configuration entries are reduced to names and whether they are
    set — never values, since several are secrets.
    """
    public = {k: v for k, v in manifest.items() if not k.startswith("_")}

    config = []
    for entry in manifest.get("configuration", []) or []:
        name = entry.get("name", "")
        config.append({
            "name":        name,
            "description": entry.get("description", ""),
            "required":    entry.get("required", False),
            "secret":      entry.get("secret", False),
            # Whether it is configured, never what it is set to.
            "configured":  bool(os.environ.get(name)),
        })
    if config:
        public["configuration"] = config

    return public


@app.get("/skills")
def list_skills(include_tools: bool = True) -> JSONResponse:
    """
    Every registered skill manifest, auto-discovered from skills/manifests/.

    Returns 200 with whatever loaded even when a manifest is malformed; the
    broken ones are reported in `errors`. One bad file should not take the
    whole registry offline.
    """
    manifests = discover_manifests(strict=False)

    skills, errors = [], []
    for manifest in manifests:
        if manifest.get("_errors"):
            errors.append({"source": manifest.get("_source"), "problems": manifest["_errors"]})
            continue
        public = _public_manifest(manifest)
        if not include_tools:
            public.pop("tools", None)
        skills.append(public)

    body: dict[str, Any] = {"count": len(skills), "skills": skills}
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=200, content=body)


@app.get("/skills/{name}")
def get_skill(name: str) -> dict:
    """One skill's manifest."""
    manifest = get_manifest(name)
    if manifest is None or manifest.get("_errors"):
        raise HTTPException(status_code=404, detail=f"skill '{name}' not found")
    return _public_manifest(manifest)


@app.get("/skills/{name}/tools")
def get_skill_tools(name: str) -> dict:
    """Just the tool definitions for one skill, for MCP clients."""
    manifest = get_manifest(name)
    if manifest is None or manifest.get("_errors"):
        raise HTTPException(status_code=404, detail=f"skill '{name}' not found")
    tools = manifest.get("tools", []) or []
    return {"skill": name, "version": manifest.get("version"), "count": len(tools), "tools": tools}


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


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui() -> HTMLResponse:
    """Minimal web UI. The sidebar is populated at runtime from /skills."""
    from app.web.ui import INDEX_HTML

    return HTMLResponse(content=INDEX_HTML)


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
