# app/web_ui/settings_routes.py
# ──────────────────────────────────────────────────────────────
# Interface Personalisation & Layout Preferences API
# PROJ-401 (Epic: Interface Personalisation)
# PROJ-442 (Theme / color customization)
# PROJ-443 (Layout preferences: widget order/visibility persisted per user)
# PROJ-444 (Settings persistence + reset to default)
# ──────────────────────────────────────────────────────────────

import os
import sys
from typing import List, Dict, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.web_ui.activity_db import (
    DEFAULT_SETTINGS,
    get_user_settings,
    reset_user_settings,
    save_user_settings,
)

router = APIRouter(prefix="/api/user/settings", tags=["Interface Personalisation"])


class UpdateSettingsRequest(BaseModel):
    theme: Optional[str] = Field(default=None, description="'dark', 'light', or 'contrast'")
    accent_color: Optional[str] = Field(default=None, description="'indigo', 'emerald', 'violet', 'amber', 'rose'")
    widget_order: Optional[List[str]] = Field(default=None, description="Ordered list of widget keys")
    widget_visibility: Optional[Dict[str, bool]] = Field(default=None, description="Visibility toggles per widget key")


def _resolve_user_id(x_user_id: Optional[str] = Header(default=None)) -> str:
    """Extract user identifier or fall back to 'default'."""
    return (x_user_id or "default").strip().lower()


@router.get("")
@router.get("/")
async def get_settings(x_user_id: Optional[str] = Header(default=None)):
    """
    Retrieve user interface preferences:
    - theme (dark / light / contrast)
    - accent_color
    - widget_order
    - widget_visibility
    PROJ-443, PROJ-444
    """
    uid = _resolve_user_id(x_user_id)
    return get_user_settings(uid)


@router.post("")
@router.post("/")
async def update_settings(
    payload: UpdateSettingsRequest,
    x_user_id: Optional[str] = Header(default=None),
):
    """
    Persist updated user preferences.
    PROJ-442, PROJ-443, PROJ-444
    """
    uid = _resolve_user_id(x_user_id)
    updated = save_user_settings(
        user_id=uid,
        theme=payload.theme,
        accent_color=payload.accent_color,
        widget_order=payload.widget_order,
        widget_visibility=payload.widget_visibility,
    )
    return {"status": "saved", "settings": updated}


@router.post("/reset")
async def reset_settings(x_user_id: Optional[str] = Header(default=None)):
    """
    Reset user interface preferences to default factory configuration.
    PROJ-444
    """
    uid = _resolve_user_id(x_user_id)
    res = reset_user_settings(uid)
    return {"status": "reset", "settings": res}
