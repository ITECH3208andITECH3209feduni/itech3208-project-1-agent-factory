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

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from app.web_ui.routes import router
from app.web_ui.auth_routes import router as auth_router
from app.web_ui.receptionist_routes import router as receptionist_router
from app.web_ui.calendar_routes import router as calendar_router
from app.web_ui.kb_routes import router as kb_router
from app.web_ui.twilio_routes import router as twilio_router
from app.web_ui.dashboard_routes import router as dashboard_router
from app.web_ui.delivery_routes import router as delivery_router
from app.web_ui.analytics_routes import router as analytics_router
from app.web_ui.settings_routes import router as settings_router

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

_SITE_DIR = os.path.join(_PROJECT, "site")
if os.path.isdir(_SITE_DIR):
    app.mount("/site-assets", StaticFiles(directory=_SITE_DIR), name="site-assets")

# Create the org/user tenancy tables if they don't exist yet (PROJ-405).
# auth/db.py's users table (PROJ-406's org registration writes to it)
# is a separate SQLite file from Sprint 3's own auth — the two auth
# systems aren't unified yet, see auth/org_routes.py's header comment.
from auth.db import init_db
from auth.tenancy import init_tenancy
init_db()
init_tenancy()
from auth.password_reset import init_reset_table
init_reset_table()
# /auth/forgot-password and /auth/reset-password (app/web_ui/auth_routes.py,
# PROJ-481) use this token store for the email accounts in auth/db.
from auth.consent import init_consent
init_consent()
from auth.consent_audit import init_consent_audit
init_consent_audit()
from auth.sms_routing import init_sms_routing
init_sms_routing()
from integrations.sms_sender import init_send_log
init_send_log()

# Include API routes
from auth.org_routes import router as org_router
from auth.api_keys import router as api_keys_router

app.include_router(auth_router)          # /auth/register, /auth/login, /auth/logout, /auth/me
app.include_router(org_router)           # /orgs — PROJ-406 organisation registration
app.include_router(api_keys_router)      # /orgs/api-keys — PROJ-473 organisation API keys
app.include_router(router)               # /query, /literature, /amazon, /integrity, /seller, /export, /history, /status
app.include_router(receptionist_router)  # /receptionist (POST)
app.include_router(calendar_router)      # /calendar/ics
app.include_router(kb_router)            # /kb/upload, /kb/list, /kb/{id}, /kb/search
app.include_router(twilio_router)        # /twilio/sms, /twilio/voice, /twilio/voice/reply, /twilio/status-callback
app.include_router(dashboard_router)     # /activity, /activity/stats, /escalations, /calendar/appointments
app.include_router(delivery_router)      # /delivery/history, /delivery/retry, /delivery/email/bounce
app.include_router(analytics_router)     # /analytics/summary, /analytics/trends, /analytics/channels
app.include_router(settings_router)      # /api/user/settings (PROJ-444)

# Contacts CRM, Dashboard, Notification Preferences (PROJ-394, 399,
# 400 — Prabhjot Singh) — mounted, not merged into this app's own
# routing. It's a genuinely separate FastAPI app (app/web/main.py)
# with its own /query, /dashboard, /contacts, /reminders, /api/* and
# its own JSON-file persistence (app/web/store.py). That store.py is
# explicit that it's a placeholder for exactly the account/contact
# system PROJ-392/405/406 would bring — those are merged now (see
# agent/reminders/ and auth/tenancy.py) but wiring this app onto them
# is real integration work (unifying three independently-designed
# contact/reminder data models), not a merge-conflict decision.
# Mounting keeps every one of Prabhjot's routes and its own tests
# (scripts/test_contacts.py etc.) working exactly as built, reachable
# in the real running app at /crm/*, without guessing at that
# unification. Follow-up: point app/web/store.py at the real DB.
from app.web.main import app as crm_app

app.mount("/crm", crm_app)


# ── Default-deny login check ───────────────────────────────────
# Everything needs a session cookie except this explicit public list. The
# /crm mount, /delivery/send, /activity and friends previously answered
# anonymous requests, so a public URL exposed contacts and could send SMS.
_PUBLIC_EXACT = {
    "/", "/status", "/status/scheduler", "/login", "/register",
    "/forgot-password", "/reset-password", "/favicon.ico",
    "/site", "/showcase", "/orgs/register",
    "/integrity",  # deliberately public (tests/test_integrity.py)
}
_PUBLIC_PREFIXES = (
    "/static/", "/site-assets/", "/site/",
    "/auth/",     # login, register, logout, me
    "/twilio/",   # Twilio webhooks verify their own X-Twilio-Signature
)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES):
        return await call_next(request)

    if path == "/crm" or path.startswith("/crm/"):
        from auth.rbac import get_current_identity
        try:
            get_current_identity(request)
        except HTTPException as exc:
            if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)

    from app.web_ui.auth_routes import get_current_username
    try:
        get_current_username(request)
    except HTTPException:
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "Not logged in"}, status_code=401)

    return await call_next(request)


# ── Root — serve the chat UI ───────────────────────────────────
@app.get("/", include_in_schema=False)
async def serve_index():
    """Serve the main chat interface."""
    index = os.path.join(_STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    return {"message": "Agent Factory API is running. Static files not found."}


# ── /literature — serve the dedicated literature search page ────
@app.get("/forgot-password", include_in_schema=False)
async def serve_forgot():
    return FileResponse(os.path.join(_STATIC_DIR, "forgot-password.html"))


@app.get("/reset-password", include_in_schema=False)
async def serve_reset():
    return FileResponse(os.path.join(_STATIC_DIR, "reset-password.html"))


@app.get("/login", include_in_schema=False)
async def serve_login():
    return FileResponse(os.path.join(_STATIC_DIR, "login.html"))

@app.get("/register", include_in_schema=False)
async def serve_register():
    return FileResponse(os.path.join(_STATIC_DIR, "register.html"))

@app.get("/literature", include_in_schema=False)
async def serve_literature():
    """Serve the standalone literature search interface."""
    page = os.path.join(_STATIC_DIR, "literature.html")
    if os.path.exists(page):
        return FileResponse(page, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    return {"message": "literature.html not found."}


# ── /showcase & /site — serve the information website (PROJ-403) ───
@app.get("/showcase", include_in_schema=False)
@app.get("/site", include_in_schema=False)
async def serve_showcase():
    """Serve the information website home page.

    The pages use relative links (css/site.css, features.html) so they also work
    on GitHub Pages. Served from /showcase or /site those would resolve against
    the site root, so point them at /site/ with a <base> tag.
    """
    site_index = os.path.join(_SITE_DIR, "index.html")
    if not os.path.exists(site_index):
        return {"message": "Showcase site not found."}
    with open(site_index, encoding="utf-8") as fh:
        html = fh.read().replace("<head>", '<head>\n  <base href="/site/">', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@app.get("/site/{page_name:path}", include_in_schema=False)
async def serve_site_page(page_name: str):
    """Serve the information website's pages and assets (features, pricing, about, faq, css, js)."""
    if page_name in ("", "index", "index.html"):
        return await serve_showcase()
    if "." not in os.path.basename(page_name):
        page_name += ".html"
    root = os.path.realpath(_SITE_DIR)
    page_path = os.path.realpath(os.path.join(root, page_name))
    if page_path.startswith(root + os.sep) and os.path.isfile(page_path):
        return FileResponse(page_path, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found.")



# ── Dev server ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
