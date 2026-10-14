"""The dashboard's numbers come from real records, never from invented defaults."""

from datetime import datetime, timedelta, timezone

import pytest

from app.web_ui import activity_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_db, "MEMORY_DB", str(tmp_path / "activity.db"))
    monkeypatch.setattr(activity_db, "_db", None)
    yield activity_db
    if activity_db._db is not None:
        activity_db._db.close()
    monkeypatch.setattr(activity_db, "_db", None)


def _at(db, table, when, **where):
    """Back-date the newest row of a table so ordering in the tests is explicit."""
    conn = db._get_db()
    col = "sent_at" if table == "delivery_history" else "timestamp"
    conn.execute(f"UPDATE {table} SET {col} = ? WHERE id = (SELECT MAX(id) FROM {table})", (when.isoformat(),))
    conn.commit()


def test_empty_system_reports_no_rates_instead_of_inventing_them(db):
    s = db.get_delivery_analytics()["summary"]
    assert s["delivery_rate_pct"] is None
    assert s["failure_rate_pct"] is None
    assert s["response_rate_pct"] is None
    assert s["total_sent"] == 0 and s["demo_records"] == 0


def test_activity_alone_no_longer_produces_a_response_rate(db):
    db.log_activity("sms", "+15550000001", "faq", "hello")
    db.log_activity("voice", "CA1", "faq", "a call")
    assert db.get_delivery_analytics()["summary"]["response_rate_pct"] is None


def test_delivery_and_failure_rates_are_computed_from_the_records(db):
    for i, status in enumerate(["delivered", "delivered", "delivered", "failed"]):
        db.log_delivery_event(f"M{i}", f"+1555000000{i}", "sms", status=status)
    s = db.get_delivery_analytics()["summary"]
    assert s["delivery_rate_pct"] == 75.0
    assert s["failure_rate_pct"] == 25.0


def test_reply_rate_counts_people_who_texted_back_after_being_texted(db):
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    for i, who in enumerate(["+15550000001", "+15550000002", "+15550000003"]):
        db.log_delivery_event(f"S{i}", who, "sms", status="delivered")
        _at(db, "delivery_history", t0)
    # A replied after the text; B texted us BEFORE we texted them; C never replied
    db.log_activity("sms", "+15550000001", "confirm", "yes"); _at(db, "activity", t0 + timedelta(minutes=30))
    db.log_activity("sms", "+15550000002", "faq", "earlier"); _at(db, "activity", t0 - timedelta(minutes=30))
    # an email recipient and a voice call never count on either side
    db.log_delivery_event("E1", "someone@example.com", "email", status="delivered")
    db.log_delivery_event("V1", "+15550000004", "voice", status="delivered")

    s = db.get_delivery_analytics()["summary"]
    assert (s["sms_recipients"], s["sms_replied"]) == (3, 1)
    assert s["response_rate_pct"] == 33.3


def test_reply_rate_is_per_organisation(db):
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    db.log_delivery_event("A1", "+15550000001", "sms", status="delivered", org_id=1); _at(db, "delivery_history", t0)
    db.log_activity("sms", "+15550000001", "confirm", "yes", org_id=2); _at(db, "activity", t0 + timedelta(minutes=5))
    assert db.get_delivery_analytics(org_id=1)["summary"]["response_rate_pct"] == 0.0
    assert db.get_delivery_analytics(org_id=2)["summary"]["response_rate_pct"] is None


def test_sample_records_are_counted_so_the_dashboard_can_label_them(db):
    db.log_delivery_event("D1", "+15550000005", "sms", status="delivered", metadata={"source": "demo_seed"})
    db.log_delivery_event("L1", "+15550000006", "sms", status="delivered", metadata={"source": "twilio"})
    s = db.get_delivery_analytics()["summary"]
    assert s["total_sent"] == 2 and s["demo_records"] == 1


def test_dashboard_front_end_shows_a_dash_not_a_made_up_number():
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "?? 100}%" not in js and "?? 0}%" not in js
    assert 'v === null || v === undefined ? "—"' in js
