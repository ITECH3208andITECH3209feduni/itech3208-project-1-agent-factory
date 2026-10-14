"""PROJ-501: activity, delivery history, analytics and the live feed are per organisation."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.web_ui import activity_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_db, "MEMORY_DB", str(tmp_path / "activity.db"))
    monkeypatch.setattr(activity_db, "_db", None)
    yield activity_db
    if activity_db._db is not None:
        activity_db._db.close()
    monkeypatch.setattr(activity_db, "_db", None)


@pytest.fixture
def client(db, monkeypatch):
    """A client whose organisation is chosen per request with an X-Test-Org header."""
    import auth.rbac as rbac
    from app.web_ui.main import app

    def fake_identity(request):
        return {"username": "tester", "org_id": int(request.headers.get("x-org", "1")), "role": "admin"}

    monkeypatch.setattr(rbac, "get_current_identity", fake_identity)
    return TestClient(app)


def _seed(db):
    # org 1 is the default organisation; org 2 is a second tenant; one legacy row has no org
    db.log_activity("sms", "+15550000001", "faq", "org one text", org_id=1)
    db.log_activity("voice", "CA-two", "appointment", "org two call", org_id=2)
    db.log_activity("sms", "+15550000009", "general", "legacy row")  # org_id NULL
    db.log_delivery_event("M-ONE", "+15550000001", "sms", status="delivered", org_id=1)
    db.log_delivery_event("M-TWO", "+15550000002", "email", status="failed", org_id=2)
    db.log_delivery_event("M-LEGACY", "+15550000009", "sms", status="delivered")


def test_activity_feed_is_per_organisation_and_legacy_rows_belong_to_org_one(db, client):
    _seed(db)
    one = {r["summary"] for r in client.get("/activity", headers={"x-org": "1"}).json()}
    two = {r["summary"] for r in client.get("/activity", headers={"x-org": "2"}).json()}
    three = client.get("/activity", headers={"x-org": "3"}).json()
    assert one == {"org one text", "legacy row"}
    assert two == {"org two call"}
    assert three == []


def test_stats_tiles_count_only_the_callers_organisation(db, client):
    _seed(db)
    assert client.get("/activity/stats", headers={"x-org": "2"}).json()["calls"] == 1
    assert client.get("/activity/stats", headers={"x-org": "2"}).json()["sms"] == 0
    assert client.get("/activity/stats", headers={"x-org": "1"}).json()["sms"] == 2
    assert client.get("/activity/stats", headers={"x-org": "3"}).json()["calls"] == 0


def test_analytics_and_exports_are_per_organisation(db, client):
    _seed(db)
    two = client.get("/analytics/summary", headers={"x-org": "2"}).json()
    one = client.get("/analytics/summary", headers={"x-org": "1"}).json()
    assert two["summary"]["total_sent"] == 1 and two["summary"]["failed"] == 1
    assert one["summary"]["total_sent"] == 2 and one["summary"]["failed"] == 0
    assert client.get("/analytics/summary", headers={"x-org": "3"}).json()["summary"]["total_sent"] == 0

    def rows(org):
        text = client.get("/analytics/export.csv", headers={"x-org": org}).text
        return [r for r in csv.DictReader(io.StringIO(text))]

    assert sum(int(r["sent"] or 0) for r in rows("2")) == 1
    assert sum(int(r["sent"] or 0) for r in rows("3")) == 0


def test_delivery_history_and_lookup_never_cross_organisations(db, client):
    _seed(db)
    hist_two = client.get("/delivery/history", headers={"x-org": "2"}).json()
    assert [i["message_id"] for i in hist_two["items"]] == ["M-TWO"] and hist_two["total"] == 1
    hist_one = {i["message_id"] for i in client.get("/delivery/history", headers={"x-org": "1"}).json()["items"]}
    assert hist_one == {"M-ONE", "M-LEGACY"}

    assert client.get("/delivery/history/M-TWO", headers={"x-org": "2"}).status_code == 200
    assert client.get("/delivery/history/M-TWO", headers={"x-org": "1"}).status_code == 404
    assert client.get("/delivery/history/M-ONE", headers={"x-org": "2"}).status_code == 404


def test_retry_cannot_touch_another_organisations_delivery(db, client):
    _seed(db)
    assert client.post("/delivery/retry/M-TWO", headers={"x-org": "1"}).status_code == 404
    ok = client.post("/delivery/retry/M-TWO", headers={"x-org": "2"})
    assert ok.status_code == 200 and ok.json()["record"]["retry_count"] == 1


def test_send_records_the_senders_organisation(db, client):
    r = client.post(
        "/delivery/send",
        headers={"x-org": "2"},
        json={"channel": "sms", "recipient": "+15550000042", "message": "hi", "reminder_type": "general"},
    )
    assert r.status_code == 200
    mid = r.json()["message_id"]
    assert client.get(f"/delivery/history/{mid}", headers={"x-org": "2"}).status_code == 200
    assert client.get(f"/delivery/history/{mid}", headers={"x-org": "1"}).status_code == 404


def test_call_summaries_follow_their_organisation(db):
    db.log_activity("voice", "CA-1", "faq", "turn", org_id=2)
    db.save_call_summary("CA-1", "+15550000002", "Asked about hours.", "neutral", "low", 1, org_id=2)
    assert db.get_recent(10, org_id=2)[0]["call_summary"] is True
    assert db.get_recent(10, org_id=1) == []


def test_old_databases_are_migrated_in_place(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE activity (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, channel TEXT NOT NULL, caller TEXT NOT NULL DEFAULT '', intent TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '')")
    conn.execute("INSERT INTO activity (timestamp, channel, caller, intent, summary) VALUES ('2026-01-01T00:00:00+00:00','sms','x','faq','before the column existed')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(activity_db, "MEMORY_DB", str(path))
    monkeypatch.setattr(activity_db, "_db", None)
    try:
        assert [r["summary"] for r in activity_db.get_recent(5, org_id=1)] == ["before the column existed"]
        assert activity_db.get_recent(5, org_id=2) == []
    finally:
        activity_db._db.close()
        monkeypatch.setattr(activity_db, "_db", None)


def test_live_feed_events_only_reach_their_own_organisation():
    from app.web_ui.ws_routes import DashboardConnectionManager

    mgr = DashboardConnectionManager()
    a, b, untagged = object(), object(), object()
    mgr._org_of[id(a)] = 1
    mgr._org_of[id(b)] = 2
    assert mgr._wants(a, 1) and not mgr._wants(a, 2)
    assert mgr._wants(b, 2) and not mgr._wants(b, 1)
    # an event with no organisation is legacy single-tenant data: org 1 only
    assert mgr._wants(a, None) and not mgr._wants(b, None)
    assert mgr._wants(untagged, 7) and mgr._wants(untagged, None)


def test_inbound_twilio_text_is_filed_under_the_number_owners_organisation(db, monkeypatch):
    import app.web_ui.twilio_routes as twilio_routes
    from app.web_ui.main import app

    monkeypatch.setattr(twilio_routes, "handle_inbound", lambda body, frm, to: None)
    monkeypatch.setattr(twilio_routes, "resolve_org_by_twilio_number", lambda n: 2 if n == "+18020000002" else None)
    monkeypatch.setattr(twilio_routes._receptionist, "handle",
                        lambda message, **kw: {"answer": "hello", "intent": "faq"})
    client = TestClient(app)
    r = client.post("/twilio/sms", data={"Body": "hi", "From": "+15551234567", "To": "+18020000002"})
    assert r.status_code == 200
    assert [x["caller"] for x in db.get_recent(10, org_id=2)] == ["+15551234567"]
    assert db.get_recent(10, org_id=3) == []
