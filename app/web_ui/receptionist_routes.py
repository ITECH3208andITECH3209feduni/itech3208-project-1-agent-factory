# app/web_ui/receptionist_routes.py
# ──────────────────────────────────────────────────────────────
# FastAPI route for the AI Receptionist tab (PROJ-195, PROJ-209-218)
#
# Endpoint:
#   POST /receptionist — send a message, get back an intent-routed reply
#
# Requires login (same as /query, /history) so conversation history
# and escalation logs are tied to a real user, not an anonymous guest.
# ──────────────────────────────────────────────────────────────

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from agent.receptionist import Receptionist
from app.web_ui.auth_routes import get_current_username

router = APIRouter()

# Shared instance (one per process) — mirrors routes.py's _orchestrator pattern
_receptionist = Receptionist()


class ReceptionistRequest(BaseModel):
    message: str


class ReceptionistResponse(BaseModel):
    answer: str
    intent: str
    booked: bool | None = None
    event_url: str | None = None
    faq_score: float | None = None
    booking_id: int | None = None
    status: str | None = None


@router.post("/receptionist", response_model=ReceptionistResponse)
async def receptionist_message(
    body: ReceptionistRequest, request: Request, username: str = Depends(get_current_username)
):
    """
    Route a message through the AI Receptionist:
    FAQ lookup -> escalation -> appointment booking -> general chat.

    Response.intent is one of: "faq" | "escalate" | "appointment" | "general"
    """
    result = _receptionist.handle(body.message, session_id=username, org_id=_org_of(request))
    return ReceptionistResponse(**result)


def _org_of(request: Request) -> int | None:
    """The signed-in user's clinic, so a booking made in the web chat lands in
    that clinic's calendar. Accounts without one still get an answer."""
    try:
        from auth.rbac import get_current_identity

        return get_current_identity(request).get("org_id")
    except Exception:  # noqa: BLE001
        return None
