# app/web_ui/auth_routes.py
# ──────────────────────────────────────────────────────────────
# FastAPI route definitions for Web UI login/register/logout (PROJ-349-353)
#
# Endpoints:
#   POST /auth/register — create an account, log in immediately
#   POST /auth/login    — verify credentials, set session cookie
#   POST /auth/logout   — clear session cookie
#   GET  /auth/me        — current logged-in username, or 401
#
# Session state lives entirely in a signed cookie (see agent/auth.py) —
# no server-side session store to manage.
# ──────────────────────────────────────────────────────────────

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from agent.auth import (
    AuthError,
    create_session_token,
    register_user,
    verify_login,
    verify_session_token,
    SESSION_TTL_SECONDS,
)

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "af_session"


# ── Pydantic models ────────────────────────────────────────────
class Credentials(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    username: str


# ── Shared helpers ──────────────────────────────────────────────
def get_current_username(request: Request) -> str:
    """FastAPI dependency — returns the logged-in username or raises 401.
    Import this into routes.py to protect /query and /history."""
    token = request.cookies.get(COOKIE_NAME)
    username = verify_session_token(token) if token else None
    if not username:
        raise HTTPException(status_code=401, detail="Not logged in")
    return username


def _set_session_cookie(response: Response, username: str) -> None:
    token = create_session_token(username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        # secure=True is intentionally omitted for local dev over http://
        # localhost; set it behind a real HTTPS deployment.
    )


# ── Routes ─────────────────────────────────────────────────────
@router.post("/register", response_model=AuthResponse)
async def register(body: Credentials, response: Response):
    """Create a new account and log the user straight in."""
    try:
        register_user(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _set_session_cookie(response, body.username.strip())
    return AuthResponse(username=body.username.strip())


@router.post("/login", response_model=AuthResponse)
async def login(body: Credentials, response: Response):
    """Verify credentials and set the session cookie."""
    try:
        verify_login(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    username = body.username.strip()
    _set_session_cookie(response, username)
    return AuthResponse(username=username)


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie. Always succeeds — logging out an
    already-logged-out browser is a no-op, not an error."""
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=AuthResponse)
async def me(username: str = Depends(get_current_username)):
    """Return the current logged-in username, or 401 if not logged in.
    Used by the frontend on page load to decide whether to show the
    login modal or the chat UI."""
    return AuthResponse(username=username)
