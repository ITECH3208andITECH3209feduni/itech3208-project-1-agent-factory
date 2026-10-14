# tests/test_reminders_export.py — GET /api/reminders/export.csv (PROJ-492)
#
# Exportable CSV report for reminder history: isolates app/web/store.py's
# JSON tables and auth.tenancy's SQLite contacts table, matching the pattern
# in tests/test_web_reminder_bridge.py.
import csv
import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from app.web import store
    from app.web.main import app
    from auth import db as auth_db, tenancy

    auth_db.DB_PATH = str(tmp_path / "auth_users.db")
    auth_db.init_db()
    tenancy.init_tenancy()
    for name in ("reminders", "consent_events"):
        store.set_table(name, store.JsonTable(tmp_path / f"{name}.json", name))
    yield TestClient(app)
    for name in ("reminders", "consent_events"):
        store.set_table(name, None)


def _make_contact(org_id=1, phone="+61400009099", name="Export Test"):
    from auth import tenancy

    return tenancy.create_contact(org_id, phone, name, consent_state="opted_in", preferred_channel="sms")


def test_export_csv_includes_history_not_scheduled(client):
    from app.web import reminders
    from app.web.store import DEFAULT_ORG_ID

    contact_id = _make_contact(DEFAULT_ORG_ID)
    sent = reminders.reminders_table().insert({
        "contact_id": contact_id, "message": "Sent reminder.",
        "send_at": "2020-01-01T09:00:00", "sent_at": "2020-01-01T09:00:05",
        "status": "sent", "created_at": "2020-01-01T08:00:00", "updated_at": "2020-01-01T09:00:05",
    }, org_id=DEFAULT_ORG_ID)
    reminders.reminders_table().insert({
        "contact_id": contact_id, "message": "Still scheduled.",
        "send_at": "2099-01-01T09:00:00", "sent_at": None,
        "status": "scheduled", "created_at": "2020-01-01T08:00:00", "updated_at": "2020-01-01T08:00:00",
    }, org_id=DEFAULT_ORG_ID)

    resp = client.get("/api/reminders/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == str(sent["id"])
    assert row["message"] == "Sent reminder."
    assert row["status"] == "sent"
    assert row["contact_phone"] == "+61400009099"
    assert row["contact_name"] == "Export Test"


def test_export_csv_empty_history_still_returns_header(client):
    resp = client.get("/api/reminders/export.csv")
    assert resp.status_code == 200
    assert resp.text.strip().splitlines() == [",".join([
        "id", "contact_name", "contact_phone", "message", "status",
        "send_at", "sent_at", "blocked_reason", "failed_reason",
        "created_at", "updated_at",
    ])]
