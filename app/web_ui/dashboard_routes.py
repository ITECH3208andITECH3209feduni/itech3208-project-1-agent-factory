# app/web_ui/dashboard_routes.py
# ──────────────────────────────────────────────────────────────
# Operator dashboard data endpoints — live feed, stats, escalations,
# calendar appointments (PROJ-387, 388, 389, 390)
#
# PROJ-387  GET /activity            — live interaction feed
# PROJ-388  GET /escalations         — escalation queue
# PROJ-389  GET /calendar/appointments — upcoming bookings (receptionist + Google Cal)
# PROJ-390  GET /activity/stats      — stat counters
#
# Assignees: Prabhjot Singh (387, 388) · Saifur Rahman Bhuiyan (389, 390)
# ──────────────────────────────────────────────────────────────

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Depends

from agent import bookings
from auth.rbac import require_org_member

from app.web_ui.activity_db import get_recent, get_stats_today, start_of_today_utc
from config.settings import ESCALATION_LOG

router = APIRouter()

# The same file the receptionist writes to (settings.ESCALATION_LOG).
_ESCALATIONS_FILE = ESCALATION_LOG


# ── PROJ-390 — Stats ───────────────────────────────────────────

@router.get("/activity/stats")
async def activity_stats(identity: dict = Depends(require_org_member)):
    """
    Today's receptionist counters: calls, SMS, booked, escalations.
    Powers the four stat tiles in the operator dashboard.
    """
    stats = get_stats_today(identity["org_id"])
    stats["escalations"] = _count_escalations_today()
    return stats


# ── PROJ-387 — Activity feed ───────────────────────────────────

@router.get("/activity")
async def activity_feed(identity: dict = Depends(require_org_member)):
    """
    Last 50 receptionist interactions (voice + SMS), newest first.
    Each item: channel, caller, intent, summary, time.
    """
    return get_recent(50, identity["org_id"])


# ── PROJ-388 — Escalation queue ───────────────────────────────

@router.get("/escalations")
async def escalations():
    """
    Last 50 escalation records from outputs/escalations.jsonl, newest first.
    Written by agent/receptionist.py _log_escalation().
    """
    return _read_escalations(50)


# ── PROJ-389 — Calendar appointments ──────────────────────────

@router.get("/calendar/appointments")
async def calendar_appointments(identity: dict = Depends(require_org_member)):
    """
    Upcoming appointments for the caller's clinic: bookings the receptionist
    made (each one Unconfirmed until the patient confirms from their link),
    plus Google Calendar events when a calendar is connected.
    """
    items = []
    for b in bookings.list_upcoming(identity["org_id"]):
        items.append({
            "summary":  b["summary"],
            "datetime": _fmt_dt(b["start_local"]),
            "start":    b["start_local"],
            "caller":   " · ".join(x for x in (b["name"], bookings.phone_text(b["phone"]), b["email"]) if x),
            "status":   b["status"],
            "booking_id": b["id"],
        })
    try:
        google = _fetch_google_calendar()
    except Exception:
        google = []
    for g in google:
        g.setdefault("status", "calendar")
    return items + google


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
    """Escalations since local midnight in the configured timezone.

    Timestamps without an offset (written by agent/receptionist.py inside a
    UTC container) are read as UTC.
    """
    start = datetime.fromisoformat(start_of_today_utc())
    count = 0
    for i in _read_escalations(500):
        try:
            ts = datetime.fromisoformat((i.get("timestamp") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= start:
            count += 1
    return count


def _fetch_google_calendar() -> list[dict]:
    key_path = os.getenv("GOOGLE_CALENDAR_KEY_PATH", "")
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    if not key_path or not os.path.exists(key_path):
        return []
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return []

    creds = service_account.Credentials.from_service_account_file(
        key_path,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    now = datetime.now(timezone.utc).isoformat()
    result = (
        service.events()
        .list(calendarId=calendar_id, timeMin=now, maxResults=20,
              singleEvents=True, orderBy="startTime")
        .execute()
    )
    items = []
    for ev in result.get("items", []):
        start = ev.get("start", {})
        dt = start.get("dateTime", start.get("date", ""))
        items.append({
            "summary":   ev.get("summary", "(no title)"),
            "datetime":  _fmt_dt(dt),
            "caller":    ev.get("organizer", {}).get("email", ""),
            "event_url": ev.get("htmlLink", ""),
        })
    return items


def _fmt_dt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%a %d %b · %H:%M")
    except Exception:
        return iso


def _time_ago(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        s = int((datetime.now(timezone.utc) - dt).total_seconds())
        if s < 60:   return f"{s}s ago"
        if s < 3600: return f"{s // 60}m ago"
        if s < 86400: return f"{s // 3600}h ago"
        return dt.strftime("%b %d")
    except Exception:
        return (ts or "")[:16]


def log_escalation(session_id: str, reason: str, priority: str = "normal") -> None:
    """Write one escalation record to outputs/escalations.jsonl."""
    os.makedirs(os.path.dirname(_ESCALATIONS_FILE), exist_ok=True)
    record = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "reason":     reason,
        "priority":   priority,
    }
    with open(_ESCALATIONS_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
