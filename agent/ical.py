# agent/ical.py
# ──────────────────────────────────────────────────────────────
# iCal (.ics) fallback for non-Google calendar users (PROJ-294-298)
#
# Pure Python, RFC 5545-compliant VEVENT generation — no `icalendar`
# package dependency needed for a single-event invite this simple.
# Lets anyone (Google Calendar, Outlook, Apple Calendar, anything that
# reads .ics) add an appointment even if they never went through the
# Google Calendar booking flow, or if that booking failed/isn't
# configured on this server.
# ──────────────────────────────────────────────────────────────

import uuid
from datetime import datetime


def _escape_text(value: str) -> str:
    """RFC 5545 §3.3.11 TEXT escaping: backslash, semicolon, comma, and
    newlines must be escaped in TEXT-valued properties (SUMMARY,
    DESCRIPTION, etc.)."""
    if not value:
        return ""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold_line(line: str) -> str:
    """RFC 5545 §3.1: lines longer than 75 octets must be folded with
    a CRLF followed by a single leading space. Rare for our short
    fields, but a genuinely long description shouldn't produce a
    malformed .ics file."""
    if len(line.encode("utf-8")) <= 75:
        return line
    out = []
    remaining = line
    first = True
    while remaining:
        limit = 75 if first else 74  # continuation lines lose 1 char to the leading space
        chunk, remaining = remaining[:limit], remaining[limit:]
        out.append(chunk if first else " " + chunk)
        first = False
    return "\r\n".join(out)


def _to_ics_datetime(iso_str: str) -> str:
    """Convert "2026-08-10T14:00:00" -> "20260810T140000" (local,
    floating time — paired with a TZID parameter on DTSTART/DTEND so
    calendar apps interpret it in the right zone rather than as UTC)."""
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime("%Y%m%dT%H%M%S")


def generate_ics(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    location: str | None = None,
    timezone: str = "Australia/Melbourne",
    organizer_email: str | None = None,
) -> bytes:
    """Build a single-event .ics file as bytes, ready to serve as a
    file download or email attachment."""
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    uid = f"{uuid.uuid4()}@agent-factory"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Agent Factory//AI Receptionist//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_utc}",
        f"DTSTART;TZID={timezone}:{_to_ics_datetime(start_iso)}",
        f"DTEND;TZID={timezone}:{_to_ics_datetime(end_iso)}",
        f"SUMMARY:{_escape_text(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape_text(description)}")
    if location:
        lines.append(f"LOCATION:{_escape_text(location)}")
    if organizer_email:
        lines.append(f"ORGANIZER:mailto:{organizer_email}")
    lines += ["END:VEVENT", "END:VCALENDAR"]

    folded = [_fold_line(line) for line in lines]
    ics_text = "\r\n".join(folded) + "\r\n"
    return ics_text.encode("utf-8")
