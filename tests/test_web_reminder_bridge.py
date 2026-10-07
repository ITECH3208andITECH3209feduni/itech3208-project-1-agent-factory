# tests/test_web_reminder_bridge.py — agent/reminders/web_bridge.py
#
# Verifies the Reminders Engine (PROJ-395) actually drives sends for
# reminders created through the dashboard UI (PROJ-438/439), per
# app/web/reminders.py's own documented intent.
from datetime import timedelta

import pytest

from agent.delivery.base import DeliveryResult
from agent.reminders.web_bridge import WebReminderBridge


class _FakeChannel:
    def __init__(self, ok=True, error=None):
        self.ok = ok
        self.error = error
        self.sent = []

    def send(self, to, message, **kwargs):
        self.sent.append((to, message, kwargs))
        return DeliveryResult(ok=self.ok, channel="fake", to=to, error=self.error)


@pytest.fixture
def app_web(tmp_path, monkeypatch):
    """Isolate app/web/store.py's JSON tables and auth.tenancy's SQLite
    contacts table, matching the pattern in scripts/test_contacts.py."""
    from app.web import store
    from auth import db as auth_db, tenancy

    auth_db.DB_PATH = str(tmp_path / "auth_users.db")
    auth_db.init_db()
    tenancy.init_tenancy()
    for name in ("reminders", "consent_events"):
        store.set_table(name, store.JsonTable(tmp_path / f"{name}.json", name))
    yield
    for name in ("reminders", "consent_events"):
        store.set_table(name, None)


def _make_contact(preferred_channel="sms", phone="+15551234567", email=None, org_id=1):
    from auth import tenancy

    cid = tenancy.create_contact(
        org_id, phone, "Test Contact",
        email=email, consent_state="opted_in", preferred_channel=preferred_channel,
    )
    return cid


def _make_due_reminder(contact_id, message="Your appointment is tomorrow.", org_id=1):
    from app.web import reminders

    past = (reminders._now() - timedelta(minutes=1)).isoformat()
    # validate() rejects a past send_at for creation, so write directly.
    return reminders.reminders_table().insert(
        {
            "contact_id": contact_id, "message": message, "send_at": past,
            "sent_at": None, "status": "scheduled",
            "created_at": reminders._now().isoformat(), "updated_at": reminders._now().isoformat(),
        },
        org_id=org_id,
    )


def test_sends_due_sms_reminder_and_marks_sent(app_web):
    from app.web import reminders

    cid = _make_contact(preferred_channel="sms")
    r = _make_due_reminder(cid)

    fake_sms = _FakeChannel(ok=True)
    bridge = WebReminderBridge(channels={"sms": fake_sms, "email": _FakeChannel()})
    results = bridge.tick()

    assert results == [{"reminder_id": r["id"], "ok": True}]
    assert fake_sms.sent[0][0] == "+15551234567"
    assert reminders.get_reminder(r["id"])["status"] == "sent"


def test_sends_due_email_reminder(app_web):
    from app.web import reminders

    cid = _make_contact(preferred_channel="email", email="person@example.com")
    r = _make_due_reminder(cid)

    fake_email = _FakeChannel(ok=True)
    bridge = WebReminderBridge(channels={"sms": _FakeChannel(), "email": fake_email})
    bridge.tick()

    assert fake_email.sent[0][0] == "person@example.com"
    assert reminders.get_reminder(r["id"])["status"] == "sent"


def test_ignores_reminders_not_yet_due(app_web):
    from app.web import reminders

    cid = _make_contact()
    future = (reminders._now() + timedelta(hours=1)).isoformat()
    reminders.reminders_table().insert(
        {"contact_id": cid, "message": "hi", "send_at": future, "sent_at": None,
         "status": "scheduled", "created_at": reminders._now().isoformat(),
         "updated_at": reminders._now().isoformat()},
        org_id=1,
    )
    bridge = WebReminderBridge(channels={"sms": _FakeChannel(), "email": _FakeChannel()})
    assert bridge.tick() == []


def test_opted_out_contact_is_blocked_not_sent(app_web):
    from app.web import reminders
    from auth import tenancy

    cid = tenancy.create_contact(1, "+15551234567", "Opted Out", consent_state="opted_out")
    r = _make_due_reminder(cid)

    fake_sms = _FakeChannel(ok=True)
    bridge = WebReminderBridge(channels={"sms": fake_sms, "email": _FakeChannel()})
    results = bridge.tick()

    assert results[0]["ok"] is False
    assert results[0]["blocked"] is True
    assert fake_sms.sent == []
    assert reminders.get_reminder(r["id"])["status"] == "blocked"


def test_delivery_failure_marks_failed_not_blocked(app_web):
    from app.web import reminders

    cid = _make_contact()
    r = _make_due_reminder(cid)

    fake_sms = _FakeChannel(ok=False, error="invalid number")
    bridge = WebReminderBridge(channels={"sms": fake_sms, "email": _FakeChannel()})
    bridge.tick()

    assert reminders.get_reminder(r["id"])["status"] == "failed"


def test_unsupported_channel_marks_failed_with_clear_reason(app_web):
    from app.web import reminders

    cid = _make_contact(preferred_channel="telegram")
    r = _make_due_reminder(cid)

    bridge = WebReminderBridge(channels={"sms": _FakeChannel(), "email": _FakeChannel()})
    results = bridge.tick()

    assert results[0]["ok"] is False
    assert "telegram" in results[0]["error"]
    assert reminders.get_reminder(r["id"])["status"] == "failed"
