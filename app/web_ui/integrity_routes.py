# app/web_ui/integrity_routes.py
# ──────────────────────────────────────────────────────────────
# FastAPI route for the Integrity Check tab (PROJ-364-368).
#
# Endpoint:
#   POST /integrity — {"text": "..."} -> {ai_probability, summary, details}
#
# Wires up the frontend's existing (previously dead) sendIntegrityCheck()
# in static/js/app.js — see agent/integrity.py for the honest scope
# note on what this heuristic can and can't tell you.
#
# Requires login (same pattern as /receptionist, /kb/*) since the
# plagiarism half of the check reads the current user's own KB
# documents.
# ──────────────────────────────────────────────────────────────

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent.integrity import run_integrity_check, IntegrityError
from agent.kb_store import list_documents_with_content
from app.web_ui.auth_routes import get_current_username

router = APIRouter()


class IntegrityRequest(BaseModel):
    text: str


class IntegrityResponse(BaseModel):
    ai_probability: float
    summary: str
    details: list[str]


@router.post("/integrity", response_model=IntegrityResponse)
async def integrity_check(
    body: IntegrityRequest, username: str = Depends(get_current_username)
):
    kb_documents = list_documents_with_content(username)
    try:
        result = run_integrity_check(body.text, kb_documents)
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return IntegrityResponse(**result)
