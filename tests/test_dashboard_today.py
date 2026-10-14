"""The dashboard's 'today' is the organisation's local day, not the UTC date."""

import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.web_ui import activity_db, dashboard_routes


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_db, "MEMORY_DB", str(tmp_path / "a.db"))
    monkeypatch.setattr(activity_db, "_db", None)
    yield activity_db
    if activity_db._db is not None:
        activity_db._db.close()
    monkeypatch.setattr(activity_db, "_db", None)


def _insert(db, channel, when_utc, intent=""):
    conn = db._get_db()
    conn.execute(
        "INSERT INTO activity (timestamp, channel, caller, intent, summary) VALUES (?, ?, 'x', ?, '')",
        (when_utc.isoformat(), channel, intent),
    )
    conn.commit()


def test_start_of_today_is_local_midnight_in_utc(monkeypatch):
    monkeypatch.setattr(activity_db, "TIMEZONE", "Australia/Sydney")
    start = datetime.fromisoformat(activity_db.start_of_today_utc())
    local = start.astimezone(ZoneInfo("Australia/Sydney"))
    assert (local.hour, local.minute, local.second) == (0, 0, 0)
    assert timedelta(0) <= datetime.now(timezone.utc) - start < timedelta(hours=25)


def test_a_sydney_morning_call_counts_as_today_even_when_the_utc_date_is_yesterday(db, monkeypatch):
    monkeypatch.setattr(activity_db, "TIMEZONE", "Australia/Sydney")
    start = datetime.fromisoformat(activity_db.start_of_today_utc())
    just_after_midnight_local = start + timedelta(minutes=30)  # UTC date is the previous day for most of the year
    just_before_midnight_local = start - timedelta(minutes=30)
    _insert(db, "voice", just_after_midnight_local)
    _insert(db, "voice", just_before_midnight_local)
    _insert(db, "sms", just_after_midnight_local)
    stats = db.get_stats_today()
    assert stats["calls"] == 1 and stats["sms"] == 1


def test_invalid_timezone_falls_back_to_utc(monkeypatch):
    monkeypatch.setattr(activity_db, "TIMEZONE", "Not/AZone")
    start = datetime.fromisoformat(activity_db.start_of_today_utc())
    assert (start.hour, start.minute) == (0, 0)


def test_escalation_count_uses_the_local_day(monkeypatch):
    monkeypatch.setattr(activity_db, "TIMEZONE", "Australia/Sydney")
    start = datetime.fromisoformat(activity_db.start_of_today_utc())
    rows = [
        {"timestamp": (start + timedelta(minutes=5)).isoformat()},              # today, offset form
        {"timestamp": (start + timedelta(hours=1)).replace(tzinfo=None).isoformat()},  # today, naive = UTC
        {"timestamp": (start - timedelta(minutes=5)).isoformat()},              # yesterday
        {"timestamp": "garbage"},
    ]
    monkeypatch.setattr(dashboard_routes, "_read_escalations", lambda limit: rows)
    assert dashboard_routes._count_escalations_today() == 2
