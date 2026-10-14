# agent/calendar_client.py
# ──────────────────────────────────────────────────────────────
# Google Calendar booking for the AI Receptionist (PROJ-209-213, 218)
#
# Deliberate design match to the NanoClaw Telegram bot's calendar
# integration (src/calendar.ts): service-account auth via the
# lightweight `google-auth` package + a raw REST call, rather than
# pulling in the full google-api-python-client typed surface. Reuses
# the SAME service account key + calendar ID already configured for
# the Telegram bot (see config/settings.py / .env) — nothing new to
# set up.
#
# Runs inside the FastAPI process only. The key file path comes from
# GOOGLE_CALENDAR_KEY_PATH (gitignored — see .gitignore's secrets/
# entry) and is never sent to the frontend or logged.
# ──────────────────────────────────────────────────────────────

import hashlib
import os
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from config.settings import GOOGLE_CALENDAR_ID, GOOGLE_CALENDAR_KEY_PATH

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class CalendarError(Exception):
    """Raised for any booking failure with a user-facing message."""


def is_configured() -> bool:
    return bool(
        GOOGLE_CALENDAR_KEY_PATH
        and GOOGLE_CALENDAR_ID
        and os.path.exists(GOOGLE_CALENDAR_KEY_PATH)
    )


def _get_access_token() -> str:
    """Exchange the service account key for a short-lived OAuth2 access
    token. Raises CalendarError with a clear message if google-auth
    isn't installed or the key file is bad — both are real possible
    states, not hypotheticals, since this reuses whatever was set up
    for the Telegram bot."""
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleAuthRequest
    except ImportError:
        raise CalendarError(
            "Calendar booking needs the 'google-auth' package — "
            "run: pip install -r requirements.txt"
        )

    try:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CALENDAR_KEY_PATH, scopes=CALENDAR_SCOPES
        )
        creds.refresh(GoogleAuthRequest())
    except Exception as exc:
        raise CalendarError(f"Couldn't authenticate with Google Calendar: {exc}")

    return creds.token


def book_appointment(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    attendee_email: str | None = None,
    timezone: str = "Australia/Melbourne",
    contact_channel: str | None = None,
    contact_address: str | None = None,
) -> dict:
    """Create a calendar event. Returns {"ok": True, "event_url": ...}
    on success, or {"ok": False, "error": ...} on failure — mirrors the
    TS side's BookAppointmentResult shape so both bots behave the same
    way toward whoever's reading the response."""
    if not GOOGLE_CALENDAR_KEY_PATH or not GOOGLE_CALENDAR_ID:
        return {
            "ok": False,
            "error": "Calendar not configured — set GOOGLE_CALENDAR_KEY_PATH "
            "and GOOGLE_CALENDAR_ID in .env",
        }

    try:
        token = _get_access_token()
    except CalendarError as exc:
        return {"ok": False, "error": str(exc)}

    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{quote(GOOGLE_CALENDAR_ID, safe='')}/events"
    )
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
    }
    if attendee_email:
        body["attendees"] = [{"email": attendee_email}]
    if contact_channel and contact_address:
        body["extendedProperties"] = {"private": {
            "agent_factory_contact_key": _contact_key(contact_channel, contact_address)
        }}

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Network error reaching Google Calendar: {exc}"}

    if resp.status_code >= 400:
        return {
            "ok": False,
            "error": f"Google Calendar API error {resp.status_code}: {resp.text[:300]}",
        }

    data = resp.json()
    return {
        "ok": True,
        "event_url": data.get("htmlLink"),
        "event_id": data.get("id"),
    }
def _contact_key(contact_channel: str, contact_address: str) -> str:
    """Return a stable, non-plaintext caller identifier across channels."""
    channel = contact_channel.strip().lower()
    address = contact_address.strip().casefold()

    if channel in {"sms", "voice"}:
        address = "".join(
            character for character in address
            if character.isdigit() or character == "+"
        )
        identity = f"phone:{address}"
    elif channel == "email":
        identity = f"email:{address}"
    else:
        identity = f"{channel}:{address}"

    return hashlib.sha256(identity.encode("utf-8")).hexdigest()

def find_upcoming_appointments(
    contact_channel: str,
    contact_address: str,
) -> dict:
    """Find future events that were created with this caller's private key."""
    if not is_configured():
        return {"ok": False, "error": "Calendar not configured", "events": []}
    if not contact_channel or not contact_address:
        return {"ok": False, "error": "Caller contact details are required", "events": []}

    try:
        token = _get_access_token()
    except CalendarError as exc:
        return {"ok": False, "error": str(exc), "events": []}

    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{quote(GOOGLE_CALENDAR_ID, safe='')}/events"
    )
    params = {
        "privateExtendedProperty": (
            "agent_factory_contact_key="
            f"{_contact_key(contact_channel, contact_address)}"
        ),
        "timeMin": datetime.now(timezone.utc).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": 50,
    }

    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=15,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Network error reaching Google Calendar: {exc}", "events": []}

    if response.status_code >= 400:
        return {
            "ok": False,
            "error": f"Google Calendar API error {response.status_code}: {response.text[:300]}",
            "events": [],
        }

    try:
        events = response.json().get("items", [])
    except (ValueError, AttributeError):
        return {"ok": False, "error": "Google Calendar returned an invalid response", "events": []}

    events = [event for event in events if event.get("status") != "cancelled"]
    return {"ok": True, "events": events}


def update_appointment(
    event_id: str,
    start_iso: str,
    end_iso: str,
    timezone: str = "Australia/Melbourne",
) -> dict:
    """Move an existing event without creating a duplicate."""
    if not is_configured():
        return {"ok": False, "error": "Calendar not configured"}
    if not event_id:
        return {"ok": False, "error": "A calendar event ID is required"}

    try:
        token = _get_access_token()
    except CalendarError as exc:
        return {"ok": False, "error": str(exc)}

    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{quote(GOOGLE_CALENDAR_ID, safe='')}/events/{quote(event_id, safe='')}"
    )
    body = {
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
    }

    try:
        response = requests.patch(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Network error reaching Google Calendar: {exc}"}

    if response.status_code >= 400:
        return {
            "ok": False,
            "error": f"Google Calendar API error {response.status_code}: {response.text[:300]}",
        }

    try:
        data = response.json()
    except ValueError:
        return {"ok": False, "error": "Google Calendar returned an invalid response"}

    return {
        "ok": True,
        "event_id": data.get("id", event_id),
        "event_url": data.get("htmlLink"),
        "event": data,
    }
