# tests/test_web_message_templates.py — PROJ-480 (with the PROJ-484/485 minimum)
#
# Template store and CRUD, merge-field rendering, the preview endpoint the
# reminder form calls, and the bridge personalising a message at send time.
from datetime import datetime, timedelta, timezone

import pytest

from agent.delivery.base import DeliveryResult


class _FakeChannel:
    def __init__(self):
        self.sent = []

    def send(self, to, message, **kwargs):
        self.sent.append((to, message))
        return DeliveryResult(ok=True, channel="fake", to=to)


@pytest.fixture
def web(tmp_path):
    from app.web import store
    from auth import db as auth_db, tenancy

    auth_db.DB_PATH = str(tmp_path / "auth_users.db")
    auth_db.init_db()
    tenancy.init_tenancy()
    names = ("reminders", "consent_events", "message_templates")
    for name in names:
        store.set_table(name, store.JsonTable(tmp_path / f"{name}.json", name))
    yield
    for name in names:
        store.set_table(name, None)


@pytest.fixture
def client(web):
    from fastapi.testclient import TestClient

    from app.web.main import app

    return TestClient(app)


def _contact(name="Jane Citizen"):
    from auth import tenancy

    return tenancy.create_contact(1, "+15551234567", name, consent_state="opted_in",
                                  preferred_channel="sms")


BODY = "Hi {first_name}, see you {date} at {time}. — {org}"


# ── Rendering ────────────────────────────────────────────────
def test_render_fills_known_fields_and_leaves_others():
    from app.web import message_templates as mt

    when = datetime(2026, 11, 2, 9, 30, tzinfo=timezone(timedelta(hours=11)))
    values = mt.merge_values({"name": "Jane Citizen"}, when, "Ballarat Dental")
    out = mt.render(BODY + " {not_a_field}", values)
    assert out == "Hi Jane, see you Monday 2 November at 9:30am. — Ballarat Dental {not_a_field}"


def test_render_uses_fallbacks_for_missing_values():
    from app.web import message_templates as mt

    assert mt.render("Hi {first_name}, from {org}", mt.merge_values({"name": ""}, None, None)) \
        == "Hi there, from us"


def test_render_shows_time_in_the_reminder_timezone():
    from app.web import message_templates as mt

    utc = datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc)   # 9am next day in Sydney
    values = mt.merge_values({"name": "A"}, utc, "X", tz_name="Australia/Sydney")
    assert (values["date"], values["time"]) == ("Monday 2 November", "9am")


# ── Store ────────────────────────────────────────────────────
def test_crud_and_validation(web):
    from app.web import message_templates as mt

    t = mt.create_template({"name": "Appointment", "body": BODY})
    assert mt.get_template(t["id"])["body"] == BODY
    with pytest.raises(mt.ValidationError) as exc:
        mt.create_template({"name": "appointment", "body": "x"})
    assert "name" in exc.value.errors
    with pytest.raises(mt.ValidationError) as exc:
        mt.create_template({"name": "Typo", "body": "Hi {frist_name}"})
    assert "frist_name" in exc.value.errors["body"]
    assert mt.update_template(t["id"], {"name": "Appointment"})["name"] == "Appointment"
    assert mt.delete_template(t["id"]) and mt.get_template(t["id"]) is None


# ── HTTP ─────────────────────────────────────────────────────
def test_template_routes_and_preview(client):
    r = client.post("/api/templates", json={"name": "Appointment", "body": BODY})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    listing = client.get("/api/templates").json()
    assert listing["count"] == 1
    assert {f["name"] for f in listing["merge_fields"]} >= {"first_name", "date", "time", "org"}
    assert client.patch(f"/api/templates/{tid}", json={"body": "Hi {bogus}"}).status_code == 422
    assert client.get("/api/templates/999").status_code == 404

    cid = _contact()
    d = client.post("/api/templates/preview", json={
        "body": BODY + " {x}", "contact_id": cid, "send_at": "2026-11-01T22:00:00Z",
        "tz": "Australia/Sydney",
    }).json()
    assert d["rendered"].startswith("Hi Jane, see you Monday 2 November at 9am.")
    assert d["unknown"] == ["x"]

    # Bad input in the preview degrades instead of failing the form.
    d = client.post("/api/templates/preview", json={"body": "Hi {name}", "contact_id": "abc",
                                                    "send_at": "nope", "tz": "Mars/Base"}).json()
    assert d["rendered"] == "Hi there"
    assert client.delete(f"/api/templates/{tid}").status_code == 204


def test_pages_render(client):
    page = client.get("/templates").text
    assert 'id="chips"' in page and "/api/templates" in page
    form = client.get("/reminders/new").text
    assert 'id="template"' in form and 'id="preview"' in form and "/api/templates/preview" in form


# ── Send path ────────────────────────────────────────────────
def test_bridge_personalises_message_when_sending(web):
    from agent.reminders.web_bridge import WebReminderBridge
    from app.web import message_templates as mt, reminders

    cid = _contact("Sam Lee")
    t = mt.create_template({"name": "Appt", "body": "Hi {first_name}, see you at {time}."})
    r = reminders.create_reminder({
        "contact_id": cid, "message": t["body"],
        "send_at": (reminders._now() + timedelta(hours=1)).isoformat(),
    })
    due = (reminders._now() - timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    reminders.reminders_table().update(r["id"], {"send_at": due.isoformat()})

    sms = _FakeChannel()
    WebReminderBridge(channels={"sms": sms}).tick()
    assert sms.sent == [("+15551234567", "Hi Sam, see you at 2pm.")]
    # The stored text keeps its placeholders, so a series re-renders each time.
    assert reminders.get_reminder(r["id"])["message"] == t["body"]
