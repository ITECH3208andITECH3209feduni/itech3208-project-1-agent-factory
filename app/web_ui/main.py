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
from app.web_ui.twilio_routes import router as twilio_router
from app.web_ui.receptionist_routes import router as receptionist_router

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
app.include_router(router)
app.include_router(twilio_router)
app.include_router(receptionist_router)


# ── Root — serve the chat UI ───────────────────────────────────
@app.get("/", include_in_schema=False)
async def serve_index():
    """Serve the main chat interface."""
    index = os.path.join(_STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Agent Factory API is running. Static files not found."}


# ── /literature — serve the dedicated literature search page ────
@app.get("/literature", include_in_schema=False)
async def serve_literature():
    """Serve the standalone literature search interface."""
    page = os.path.join(_STATIC_DIR, "literature.html")
    if os.path.exists(page):
        return FileResponse(page)
    return {"message": "literature.html not found."}


# ── Dev server ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
