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
def web(tmp_path, monkeypatch):
    import agent.auth as session_auth
    from app.web import store
    from auth import db as auth_db, tenancy

    monkeypatch.setattr(auth_db, "DB_PATH", str(tmp_path / "auth_users.db"))
    monkeypatch.setattr(session_auth, "AUTH_DB", str(tmp_path / "session_auth.db"))

    auth_db.init_db()
    tenancy.init_tenancy()
    org_id = tenancy.create_org("Template Test Org")

    session_auth.register_user("templateowner", "password123")
    session_auth.set_user_org_id("templateowner", org_id)

    names = ("reminders", "consent_events", "message_templates")
    for name in names:
        store.set_table(name, store.JsonTable(tmp_path / f"{name}.json", name))
    yield
    for name in names:
        store.set_table(name, None)


@pytest.fixture
def client(web):
    from fastapi.testclient import TestClient
    from agent.auth import create_session_token
    from app.web.main import app

    test_client = TestClient(app)
    test_client.cookies.set(
        "af_session", create_session_token("templateowner")
    )
    return test_client


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

def test_template_crud_fields_and_organisation_isolation(client, web):
    from fastapi.testclient import TestClient

    import agent.auth as session_auth
    from app.web.main import app
    from auth import tenancy

    # Organisation 1 creates a template with the new fields.
    created = client.post(
        "/api/templates",
        json={
            "name": "Annual reminder",
            "body": "Hi {name}",
            "channel": "email",
            "subject": "Your annual reminder",
        },
    )
    assert created.status_code == 201, created.text
    template = created.json()
    template_id = template["id"]
    assert template["channel"] == "email"
    assert template["subject"] == "Your annual reminder"

    # Create a second, independent organisation and session user.
    second_org_id = tenancy.create_org("Another Template Org")
    session_auth.register_user("otherowner", "password123")
    session_auth.set_user_org_id("otherowner", second_org_id)

    other = TestClient(app)
    other.cookies.set(
        "af_session", session_auth.create_session_token("otherowner")
    )

    # The second organisation cannot see or modify the first template.
    assert other.get("/api/templates").json()["count"] == 0
    assert other.get(f"/api/templates/{template_id}").status_code == 404
    assert other.patch(
        f"/api/templates/{template_id}",
        json={"subject": "Stolen update"},
    ).status_code == 404
    assert other.delete(f"/api/templates/{template_id}").status_code == 404

    # It can create a template with the same name in its own organisation.
    second = other.post(
        "/api/templates",
        json={
            "name": "Annual reminder",
            "body": "Hello {first_name}",
            "channel": "sms",
            "subject": "",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["org_id"] == second_org_id

    # The original organisation can update its own template.
    updated = client.patch(
        f"/api/templates/{template_id}",
        json={"channel": "voice", "subject": "Updated subject"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["channel"] == "voice"
    assert updated.json()["subject"] == "Updated subject"

    # Invalid channels and misspelled placeholders are rejected.
    invalid_channel = client.post(
        "/api/templates",
        json={
            "name": "Bad channel",
            "body": "Hi {name}",
            "channel": "fax",
        },
    )
    assert invalid_channel.status_code == 422

    invalid_field = client.post(
        "/api/templates",
        json={
            "name": "Bad field",
            "body": "Hi {frist_name}",
        },
    )
    assert invalid_field.status_code == 422

    # Cross-organisation attempts did not change the original template.
    unchanged = client.get(f"/api/templates/{template_id}").json()
    assert unchanged["subject"] == "Updated subject"
    assert unchanged["channel"] == "voice"

def test_template_crud_is_available_under_crm_mount(web):
    from fastapi.testclient import TestClient

    from agent.auth import create_session_token
    from app.web_ui.main import app

    mounted_client = TestClient(app)
    mounted_client.cookies.set(
        "af_session", create_session_token("templateowner")
    )

    created = mounted_client.post(
        "/crm/api/templates",
        json={
            "name": "Mounted API template",
            "body": "Hi {first_name}",
            "channel": "sms",
            "subject": "Appointment reminder",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["channel"] == "sms"
    assert created.json()["subject"] == "Appointment reminder"

    listing = mounted_client.get("/crm/api/templates")
    assert listing.status_code == 200, listing.text
    assert listing.json()["count"] == 1
