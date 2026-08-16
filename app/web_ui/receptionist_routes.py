# app/web_ui/receptionist_routes.py
# ──────────────────────────────────────────────────────────────
# Dashboard data endpoints for the AI Receptionist operator panel.
#
# PROJ-387  GET /activity            — live interaction feed
# PROJ-388  GET /escalations         — escalation queue
# PROJ-389  GET /calendar/appointments — upcoming bookings
# PROJ-390  GET /activity/stats      — stat counters
#
# Assignees: Prabhjot Singh (387, 388) · Saifur Rahman Bhuiyan (389, 390)
# ──────────────────────────────────────────────────────────────

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.web_ui.activity_db import get_recent, get_stats_today
from config.settings import OUTPUT_DIR

router = APIRouter()

_ESCALATIONS_FILE = os.path.join(OUTPUT_DIR, "escalations.jsonl")


# ── PROJ-390 — Stats ───────────────────────────────────────────

@router.get("/activity/stats")
async def activity_stats():
    """
    Today's receptionist counters: calls, SMS, booked appointments,
    and escalations.  Powers the four stat tiles in the operator dashboard.
    """
    stats = get_stats_today()
    stats["escalations"] = _count_escalations_today()
    return stats


# ── PROJ-387 — Activity feed ───────────────────────────────────

@router.get("/activity")
async def activity_feed():
    """
    Last 50 receptionist interactions (voice + SMS + web chat),
    newest first.  Each item has: channel, caller, intent, summary, time.
    """
    return get_recent(50)


# ── PROJ-388 — Escalation queue ───────────────────────────────

@router.get("/escalations")
async def escalations():
    """
    Last 50 escalation records from outputs/escalations.jsonl,
    newest first.  Each item: session_id, reason, priority, time.
    Written by the receptionist whenever a query is flagged for
    human follow-up.
    """
    items = _read_escalations(50)
    return items


# ── PROJ-389 — Calendar appointments ──────────────────────────

@router.get("/calendar/appointments")
async def calendar_appointments():
    """
    Upcoming appointments from Google Calendar.
    Returns items: summary, datetime, caller.
    Falls back to an empty list if credentials are not configured.
    """
    try:
        items = _fetch_google_calendar()
    except Exception:
        items = []
    return items


# ── Helpers ────────────────────────────────────────────────────

def _read_escalations(limit: int) -> list[dict]:
    if not os.path.exists(_ESCALATIONS_FILE):
        return []
    rows: list[dict] = []
    try:
        with open(_ESCALATIONS_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        return []

    # Normalise fields the UI expects and add human-readable time
    result = []
    for r in reversed(rows[-limit:]):
        ts = r.get("timestamp", r.get("time", ""))
        result.append({
            "session_id": r.get("session_id", ""),
            "reason":     r.get("reason", r.get("message", "")),
            "priority":   r.get("priority", "normal"),
            "time":       _time_ago(ts),
            "timestamp":  ts,
        })
    return result


def _count_escalations_today() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items = _read_escalations(500)
    return sum(1 for i in items if (i.get("timestamp") or "").startswith(today))


def _fetch_google_calendar() -> list[dict]:
    """
    Fetch upcoming events from Google Calendar using a service account.
    Requires env vars:
      GOOGLE_CALENDAR_KEY_PATH — path to service-account JSON key file
      GOOGLE_CALENDAR_ID       — calendar ID (e.g. primary or email@group.calendar.google.com)
    Returns [] if either var is missing or the google-api packages are absent.
    """
    key_path = os.getenv("GOOGLE_CALENDAR_KEY_PATH", "")
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    if not key_path or not os.path.exists(key_path):
        return []

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return []

    scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
    creds = service_account.Credentials.from_service_account_file(key_path, scopes=scopes)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.now(timezone.utc).isoformat()
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = []
    for ev in events_result.get("items", []):
        start = ev.get("start", {})
        dt = start.get("dateTime", start.get("date", ""))
        items.append({
            "summary":  ev.get("summary", "(no title)"),
            "datetime": _fmt_dt(dt),
            "caller":   ev.get("organizer", {}).get("email", ""),
            "event_url": ev.get("htmlLink", ""),
        })
    return items


def _fmt_dt(iso: str) -> str:
    """Format an ISO datetime string for display."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%a %d %b · %H:%M")
    except Exception:
        return iso


def _time_ago(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        s = int((datetime.now(timezone.utc) - dt).total_seconds())
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return dt.strftime("%b %d")
    except Exception:
        return (ts or "")[:16]


def log_escalation(session_id: str, reason: str, priority: str = "normal") -> None:
    """
    Append one escalation record to outputs/escalations.jsonl.
    Called from twilio_routes when a query can't be handled.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    record = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "reason":     reason,
        "priority":   priority,
    }
    with open(_ESCALATIONS_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
