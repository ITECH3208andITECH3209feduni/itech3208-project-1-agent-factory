# app/web_ui/calendar_routes.py
# ──────────────────────────────────────────────────────────────
# iCal (.ics) download endpoint (PROJ-294-298)
#
# Endpoint:
#   GET /calendar/ics — returns a downloadable .ics invite
#
# Stateless: takes the appointment details as query params and
# generates the file on the fly. No database involved, so this works
# regardless of whether the Google Calendar booking succeeded —
# useful both as the "non-Google users" fallback the ticket calls for,
# and as a "add this to your own calendar too" option for anyone.
# ──────────────────────────────────────────────────────────────

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from agent.ical import generate_ics
from app.web_ui.auth_routes import get_current_username
from config.settings import TIMEZONE

router = APIRouter()


@router.get("/calendar/ics")
async def download_ics(
    summary: str = Query(..., min_length=1),
    start: str = Query(..., description="Local ISO datetime, e.g. 2026-08-10T14:00:00"),
    end: str = Query(..., description="Local ISO datetime, e.g. 2026-08-10T14:30:00"),
    description: str | None = None,
    username: str = Depends(get_current_username),
):
    """Generate and return a single-event .ics file for download."""
    try:
        ics_bytes = generate_ics(
            summary=summary,
            start_iso=start,
            end_iso=end,
            description=description,
            timezone=TIMEZONE,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date/time: {exc}")

    filename = "".join(c if c.isalnum() else "_" for c in summary)[:40] or "appointment"
    return Response(
        content=ics_bytes,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}.ics"'},
    )
