# app/web_ui/main.py
# ──────────────────────────────────────────────────────────────
# FastAPI application entry point — Agent Factory Web UI
# PROJ-139 (Dilraj Singh)
#
# Usage:
#   python -m app.web_ui.main
#   uvicorn app.web_ui.main:app --reload --port 8000
#
# Opens: http://localhost:8000
#
# Merge note: this file reconciles two independently-built versions
# of the web app. origin/main's /integrity (routes.py, backed by the
# real skills/academic_integrity.py — Claude classification + real
# DuckDuckGo plagiarism search) supersedes the heuristic /integrity
# route this branch built in app/web_ui/integrity_routes.py before
# that real implementation was discovered during this merge — that
# router is intentionally NOT included below to avoid two handlers
# racing for the same path. See tests/qa/PROJ-369-qa-pass.md / the
# PROJ-364 Jira comment for the full story.
# ──────────────────────────────────────────────────────────────

import os
import sys

# Ensure project root is on the path regardless of working directory
_HERE    = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.abspath(os.path.join(_HERE, "../.."))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.web_ui.routes import router
from app.web_ui.auth_routes import router as auth_router
from app.web_ui.receptionist_routes import router as receptionist_router
from app.web_ui.calendar_routes import router as calendar_router
from app.web_ui.kb_routes import router as kb_router
from app.web_ui.twilio_routes import router as twilio_router
from app.web_ui.dashboard_routes import router as dashboard_router

# ── App setup ──────────────────────────────────────────────────
app = FastAPI(
    title="Agent Factory",
    description="24/7 Research AI — Literature & Amazon Product Search",
    version="2.0.0",
)

# Mount static files (HTML / CSS / JS)
_STATIC_DIR = os.path.join(_PROJECT, "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Include API routes
app.include_router(auth_router)          # /auth/register, /auth/login, /auth/logout, /auth/me
app.include_router(router)               # /query, /literature, /amazon, /integrity, /seller, /export, /history, /status
app.include_router(receptionist_router)  # /receptionist (POST)
app.include_router(calendar_router)      # /calendar/ics
app.include_router(kb_router)            # /kb/upload, /kb/list, /kb/{id}, /kb/search
app.include_router(twilio_router)        # /twilio/sms, /twilio/voice, /twilio/voice/reply
app.include_router(dashboard_router)     # /activity, /activity/stats, /escalations, /calendar/appointments


# ── Root — serve the chat UI ───────────────────────────────────
@app.get("/", include_in_schema=False)
async def serve_index():
    """Serve the main chat interface."""
    index = os.path.join(_STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    return {"message": "Agent Factory API is running. Static files not found."}


# ── /literature — serve the dedicated literature search page ────
@app.get("/literature", include_in_schema=False)
async def serve_literature():
    """Serve the standalone literature search interface."""
    page = os.path.join(_STATIC_DIR, "literature.html")
    if os.path.exists(page):
        return FileResponse(page, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    return {"message": "literature.html not found."}


# ── Dev server ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
