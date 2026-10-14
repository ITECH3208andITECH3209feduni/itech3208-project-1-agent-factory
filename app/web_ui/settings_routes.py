"""User settings routes with organisation-level access control."""

import os
import sys
from typing import List, Dict, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.web_ui.activity_db import (
    get_user_settings,
    reset_user_settings,
    save_user_settings,
)
from auth.rbac import require_admin, require_org_member

router = APIRouter(
    prefix="/api/user/settings",
    tags=["Interface Personalisation"],
)


class UpdateSettingsRequest(BaseModel):
    theme: Optional[str] = Field(default=None)
    accent_color: Optional[str] = Field(default=None)
    widget_order: Optional[List[str]] = Field(default=None)
    widget_visibility: Optional[Dict[str, bool]] = Field(default=None)


@router.get("")
@router.get("/")
async def get_settings(
    identity: dict = Depends(require_org_member),
):
    """Get the authenticated user's own settings."""
    return get_user_settings(identity["username"])


@router.post("")
@router.post("/")
async def update_settings(
    payload: UpdateSettingsRequest,
    identity: dict = Depends(require_admin),
):
    """Only organisation admins may change settings."""
    updated = save_user_settings(
        user_id=identity["username"],
        theme=payload.theme,
        accent_color=payload.accent_color,
        widget_order=payload.widget_order,
        widget_visibility=payload.widget_visibility,
    )
    return {"status": "saved", "settings": updated}


@router.post("/reset")
async def reset_settings(
    identity: dict = Depends(require_admin),
):
    """Only organisation admins may reset settings."""
    result = reset_user_settings(identity["username"])
    return {"status": "reset", "settings": result}