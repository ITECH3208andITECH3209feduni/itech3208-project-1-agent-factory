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

from fastapi import FastAPI, HTTPException, Request, Response
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
        "skills":    "/skills",
        "ui":        "/ui",
        "dashboard": "/dashboard",
        "stats":     "/api/stats",
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


# ── Dashboard (PROJ-437) ──────────────────────────────────────
def current_user() -> dict | None:
    """
    Auth seam for the dashboard.

    PROJ-399 calls for an *authenticated* landing page, but accounts and
    sessions are PROJ-392 (Accounts & Multi-tenancy), which has not landed.
    Rather than fake a login — which would be worse than none, because it
    would look like access control — this returns None and the dashboard
    renders a visible "not authenticated" banner.

    When PROJ-392 lands, enforce it here: this is the single place the
    dashboard and /api/stats consult.
    """
    return None


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Dashboard shell — KPI counters and nav."""
    from app.web.dashboard import INDEX_HTML

    return HTMLResponse(content=INDEX_HTML)


# -- Contacts (PROJ-417, 418, 419, 420) ------------------------
@app.get("/contacts", response_class=HTMLResponse, include_in_schema=False)
def contacts_page() -> HTMLResponse:
    from app.web.contacts_ui import LIST_HTML

    return HTMLResponse(content=LIST_HTML)


@app.get("/contacts/new", response_class=HTMLResponse, include_in_schema=False)
def contact_new() -> HTMLResponse:
    from app.web.contacts_ui import render_form

    return HTMLResponse(content=render_form())


@app.get("/contacts/import", response_class=HTMLResponse, include_in_schema=False)
def contact_import_page() -> HTMLResponse:
    from app.web.contacts_ui import IMPORT_HTML

    return HTMLResponse(content=IMPORT_HTML)


@app.get("/contacts/{contact_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def contact_edit(contact_id: int) -> HTMLResponse:
    from app.web.contacts_ui import render_form

    return HTMLResponse(content=render_form(str(contact_id)))


@app.get("/contacts/{contact_id}", response_class=HTMLResponse, include_in_schema=False)
def contact_profile(contact_id: int) -> HTMLResponse:
    from app.web.contacts_ui import render_profile

    return HTMLResponse(content=render_profile(contact_id))


@app.get("/api/contacts")
def api_list_contacts(q: str | None = None, consent_state: str | None = None) -> dict:
    """Contacts for the current org, name-sorted."""
    from app.web import contacts

    try:
        rows = contacts.list_contacts(q=q, consent_state=consent_state)
    except contacts.ValidationError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "contacts": rows}


@app.get("/api/contacts/{contact_id}")
def api_get_contact(contact_id: int) -> dict:
    from app.web import consent, contacts

    row = contacts.get_contact(contact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="contact not found")
    return {
        **row,
        "consent_history": consent.history(contact_id),
        # Whether a send would be allowed right now, so the profile can say so
        # before a reminder is scheduled rather than after it is blocked.
        "send_decision": consent.check_send(contact_id).to_dict(),
    }


@app.post("/api/contacts", status_code=201)
def api_create_contact(payload: dict) -> dict:
    from app.web import contacts

    try:
        return contacts.create_contact(payload)
    except contacts.ValidationError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})


@app.patch("/api/contacts/{contact_id}")
def api_update_contact(contact_id: int, payload: dict) -> dict:
    from app.web import contacts

    try:
        row = contacts.update_contact(contact_id, payload)
    except contacts.ValidationError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})
    if row is None:
        raise HTTPException(status_code=404, detail="contact not found")
    return row


@app.delete("/api/contacts/{contact_id}", status_code=204)
def api_delete_contact(contact_id: int) -> Response:
    from app.web import contacts

    if not contacts.delete_contact(contact_id):
        raise HTTPException(status_code=404, detail="contact not found")
    return Response(status_code=204)


@app.post("/api/contacts/import")
async def api_import_contacts(request: Request, dry_run: bool = False) -> dict:
    """
    CSV bulk import (PROJ-420).

    Reports every row individually: one malformed number does not reject the
    other 499. dry_run=true validates and reports without writing.
    """
    from app.web import contacts

    raw = await request.body()
    try:
        return contacts.import_csv(raw, dry_run=dry_run)
    except contacts.ValidationError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})


@app.get("/api/contacts-template.csv", include_in_schema=False)
def api_csv_template() -> Response:
    from app.web import contacts

    return Response(
        content=contacts.csv_template(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts-template.csv"},
    )


# -- Consent (PROJ-441) ----------------------------------------
@app.post("/api/contacts/{contact_id}/consent")
def api_set_consent(contact_id: int, payload: dict) -> dict:
    """
    Change consent state, recorded in the append-only audit trail.

    opt_in refuses to reverse an opt-out - that needs separately evidenced
    action, not a flag flip.
    """
    from app.web import consent

    state = str(payload.get("state") or "").strip().lower()
    source = str(payload.get("source") or "manual").strip().lower()
    detail = payload.get("detail")

    try:
        if state == "opted_in":
            row = consent.opt_in(contact_id, source=source, detail=detail)
        elif state == "opted_out":
            row = consent.opt_out(contact_id, source=source, detail=detail)
        else:
            row = consent.set_state(contact_id, state, source=source, detail=detail)
    except PermissionError as exc:
        return JSONResponse(status_code=409, content={"errors": {"state": str(exc)}})
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"errors": {"state": str(exc)}})

    if row is None:
        raise HTTPException(status_code=404, detail="contact not found")
    return {**row, "consent_history": consent.history(contact_id)}


# -- Reminders (PROJ-438, PROJ-439) ----------------------------
@app.get("/reminders", response_class=HTMLResponse, include_in_schema=False)
def reminders_list_page() -> HTMLResponse:
    from app.web.reminders_list import LIST_HTML

    return HTMLResponse(content=LIST_HTML)


@app.get("/reminders/new", response_class=HTMLResponse, include_in_schema=False)
def reminder_new() -> HTMLResponse:
    from app.web.reminder_form import render

    return HTMLResponse(content=render())


@app.get("/reminders/{reminder_id}/edit", response_class=HTMLResponse, include_in_schema=False)
def reminder_edit(reminder_id: int) -> HTMLResponse:
    from app.web.reminder_form import render

    return HTMLResponse(content=render(str(reminder_id)))


@app.get("/api/reminders")
def list_reminders(
    q: str | None = None,
    status: str | None = None,
    contact_id: int | None = None,
    sort: str = "send_at_asc",
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    """Reminders, filtered and searched. `total` is pre-paging."""
    from app.web import reminders

    try:
        items = reminders.list_reminders()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        page, total = reminders.query(
            items, q=q, status=status, contact_id=contact_id,
            sort=sort, limit=limit, offset=offset,
        )
    except reminders.ValidationError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})

    return {
        "count": len(page),
        "total": total,
        "unfiltered_total": len(items),
        "reminders": page,
    }


@app.get("/api/reminders/{reminder_id}")
def get_reminder(reminder_id: int) -> dict:
    from app.web import reminders

    item = reminders.get_reminder(reminder_id)
    if item is None:
        raise HTTPException(status_code=404, detail="reminder not found")
    return {**item, "dispatch": reminders.dispatch_check(reminder_id)}


@app.post("/api/reminders", status_code=201)
def create_reminder(payload: dict) -> dict:
    from app.web import reminders

    try:
        return reminders.create_reminder(payload)
    except reminders.ValidationError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})


@app.patch("/api/reminders/{reminder_id}")
def update_reminder(reminder_id: int, payload: dict) -> dict:
    from app.web import reminders

    try:
        row = reminders.update_reminder(reminder_id, payload)
    except reminders.ValidationError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})
    if row is None:
        raise HTTPException(status_code=404, detail="reminder not found")
    return row


@app.delete("/api/reminders/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: int) -> Response:
    from app.web import reminders

    if not reminders.delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="reminder not found")
    return Response(status_code=204)


@app.get("/api/reminders/{reminder_id}/dispatch-check")
def reminder_dispatch_check(reminder_id: int) -> dict:
    """Would this send right now? The gate PROJ-395 must call (PROJ-441)."""
    from app.web import reminders

    result = reminders.dispatch_check(reminder_id)
    if result.get("code") == "no_reminder":
        raise HTTPException(status_code=404, detail="reminder not found")
    return result


@app.get("/api/stats")
def api_stats() -> dict:
    """
    Metrics behind the dashboard's KPI row.

    Metrics whose data source does not exist yet report `available: false` and
    name the ticket blocking them. They deliberately do NOT report 0 — a zero
    meaning "no store yet" is indistinguishable from a measured zero.
    """
    from app.web import stats

    payload = stats.summary()
    payload["authenticated"] = current_user() is not None
    return payload


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
