# tests/test_ical.py — agent/ical.py (PROJ-354, PROJ-294-298)
from agent.ical import generate_ics


def _unfold(raw: str) -> str:
    """Reverse RFC 5545 line folding for easier assertions."""
    return raw.replace("\r\n ", "")


def test_generates_valid_vcalendar_structure():
    ics = generate_ics("Consultation", "2026-08-10T14:00:00", "2026-08-10T14:30:00")
    text = _unfold(ics.decode("utf-8"))
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip("\r\n").endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" in text
    assert "END:VEVENT" in text
    assert "VERSION:2.0" in text


def test_includes_summary_and_times():
    ics = generate_ics("Consultation", "2026-08-10T14:00:00", "2026-08-10T14:30:00")
    text = _unfold(ics.decode("utf-8"))
    assert "SUMMARY:Consultation" in text
    assert "DTSTART;TZID=Australia/Melbourne:20260810T140000" in text
    assert "DTEND;TZID=Australia/Melbourne:20260810T143000" in text


def test_custom_timezone():
    ics = generate_ics(
        "Call", "2026-08-10T09:00:00", "2026-08-10T09:30:00", timezone="America/New_York"
    )
    text = _unfold(ics.decode("utf-8"))
    assert "DTSTART;TZID=America/New_York:20260810T090000" in text


def test_escapes_special_characters_in_summary():
    ics = generate_ics(
        "Meeting, re: budget; notes\nfollow-up",
        "2026-08-10T14:00:00",
        "2026-08-10T14:30:00",
    )
    text = _unfold(ics.decode("utf-8"))
    # RFC 5545 §3.3.11 only requires escaping backslash, comma,
    # semicolon, and newline in TEXT values — colons are left as-is.
    assert "Meeting\\, re: budget\\; notes\\nfollow-up" in text


def test_description_and_location_optional_fields():
    ics = generate_ics(
        "Consultation",
        "2026-08-10T14:00:00",
        "2026-08-10T14:30:00",
        description="Discuss Q3 roadmap",
        location="123 Example St",
    )
    text = _unfold(ics.decode("utf-8"))
    assert "DESCRIPTION:Discuss Q3 roadmap" in text
    assert "LOCATION:123 Example St" in text


def test_no_description_line_when_not_provided():
    ics = generate_ics("Consultation", "2026-08-10T14:00:00", "2026-08-10T14:30:00")
    text = ics.decode("utf-8")
    assert "DESCRIPTION:" not in text


def test_each_event_gets_a_unique_uid():
    ics1 = generate_ics("A", "2026-08-10T14:00:00", "2026-08-10T14:30:00")
    ics2 = generate_ics("B", "2026-08-10T15:00:00", "2026-08-10T15:30:00")
    uid1 = [l for l in ics1.decode().splitlines() if l.startswith("UID:")][0]
    uid2 = [l for l in ics2.decode().splitlines() if l.startswith("UID:")][0]
    assert uid1 != uid2


def test_long_line_gets_folded():
    long_description = "x" * 200
    ics = generate_ics(
        "Consultation",
        "2026-08-10T14:00:00",
        "2026-08-10T14:30:00",
        description=long_description,
    )
    raw = ics.decode("utf-8")
    # A folded continuation line starts with CRLF + a single space
    assert "\r\n " in raw
    # And unfolding it recovers the full description unbroken
    assert f"DESCRIPTION:{long_description}" in _unfold(raw)
