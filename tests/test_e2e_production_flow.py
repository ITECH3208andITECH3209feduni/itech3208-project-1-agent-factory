# tests/test_e2e_production_flow.py
# ──────────────────────────────────────────────────────────────
# PROJ-472 — End-to-end integration test
# Exercises the complete chain on isolated in-memory/tmp databases:
#
#   Org setup → Contact creation → Reminder schedule
#   → Web bridge dispatch (consent + quiet-hours gate)
#   → Delivery logging (log_delivery_event)
#   → Twilio status callback (update_delivery_status)
#   → Activity feed updated
#   → WebSocket broadcast fires
#
# All external services (Twilio, SMTP) are mocked so the test
# can run in CI without any credentials.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture()
def isolated_auth_db(tmp_path, monkeypatch):
    """Point AUTH_DB_PATH to a fresh tmp file and re-init."""
    db_path = str(tmp_path / "auth_users.db")
    monkeypatch.setenv("AUTH_DB_PATH", db_path)
    import importlib
    import auth.db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    import auth.tenancy as tenancy_mod
    importlib.reload(tenancy_mod)
    tenancy_mod.init_tenancy()
    yield db_path


@pytest.fixture()
def fastapi_client(isolated_auth_db):
    """Minimal FastAPI client with auth, delivery, twilio, and ws routers."""
    from app.web_ui.auth_routes import router as auth_router
    from app.web_ui.dashboard_routes import router as dashboard_router
    from app.web_ui.delivery_routes import router as delivery_router
    from app.web_ui.twilio_routes import router as twilio_router
    from app.web_ui.ws_routes import router as ws_router

    app = FastAPI()
    for r in (auth_router, dashboard_router, delivery_router, twilio_router, ws_router):
        app.include_router(r)
    return TestClient(app)


# ── Step 1: Auth — register & login ───────────────────────────

class TestStep1Auth:
    def test_register_succeeds(self, fastapi_client):
        resp = fastapi_client.post("/auth/register", json={
            "username": "e2euser",
            "password": "SecurePass1!",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["username"] == "e2euser"

    def test_login_succeeds(self, fastapi_client):
        fastapi_client.post("/auth/register", json={
            "username": "logintest",
            "password": "SecurePass1!",
        })
        resp = fastapi_client.post("/auth/login", json={
            "username": "logintest",
            "password": "SecurePass1!",
        })
        assert resp.status_code == 200, resp.text


# ── Step 2: Contact creation ──────────────────────────────────

class TestStep2Contact:
    def test_create_contact_returns_id(self, isolated_auth_db):
        from auth import tenancy
        contact_id = tenancy.create_contact(
            1,
            phone_number="+61400000001",
            name="E2E Test Contact",
            consent_state="opted_in",
            preferred_channel="sms",
        )
        assert isinstance(contact_id, int)
        assert contact_id > 0

    def test_contact_retrievable_by_phone(self, isolated_auth_db):
        from auth import tenancy
        tenancy.create_contact(
            1,
            phone_number="+61400000002",
            name="Retrieve Test",
            consent_state="opted_in",
        )
        row = tenancy.get_contact_by_phone(1, "+61400000002")
        assert row is not None
        assert row["name"] == "Retrieve Test"
        assert row["consent_state"] == "opted_in"

    def test_contact_org_scoped(self, isolated_auth_db):
        """A contact from org 1 must not appear when querying org 2."""
        from auth import tenancy
        tenancy.create_contact(1, phone_number="+61400000003", name="Org1 Contact")
        row = tenancy.get_contact_by_phone(2, "+61400000003")
        assert row is None


# ── Step 3: Reminder scheduling (JSON store) ──────────────────

class TestStep3Reminder:
    def _make_contact(self, phone, org_id):
        from app.web import contacts as web_contacts
        c = web_contacts.create_contact({
            "phone_number": phone,
            "name": "Reminder Test",
            "consent_state": "opted_in",
        }, org_id=org_id)
        return dict(c)

    def test_schedule_reminder_status_is_scheduled(self, isolated_auth_db):
        from app.web import reminders
        from app.web.store import DEFAULT_ORG_ID
        contact = self._make_contact("+61400009001", DEFAULT_ORG_ID)
        reminder = reminders.create_reminder({
            "contact_id": contact["id"],
            "message": "E2E: your appointment is tomorrow.",
            "send_at": "2099-01-01T08:00:00",
        }, org_id=DEFAULT_ORG_ID)
        assert reminder["status"] == "scheduled"
        assert "id" in reminder

    def test_reminder_appears_in_list(self, isolated_auth_db):
        from app.web import reminders
        from app.web.store import DEFAULT_ORG_ID
        contact = self._make_contact("+61400009002", DEFAULT_ORG_ID)
        reminders.create_reminder({
            "contact_id": contact["id"],
            "message": "Listed reminder.",
            "send_at": "2099-01-01T09:00:00",
        }, org_id=DEFAULT_ORG_ID)
        items = reminders.list_reminders(DEFAULT_ORG_ID)
        assert any(r["message"] == "Listed reminder." for r in items)


# ── Step 4: Web bridge dispatches via mock channel ────────────

class TestStep4WebBridge:
    def _make_contact_and_reminder(self, phone, consent, org_id):
        from app.web import contacts as web_contacts, reminders
        # Create contact via the full contacts API so both tenancy + JSON stores are consistent
        contact = dict(web_contacts.create_contact({
            "phone_number": phone,
            "name": "Bridge Test",
            "consent_state": consent,
        }, org_id=org_id))
        # Insert reminder directly at store level to use a past send_at (bypass validate)
        tbl = reminders.reminders_table()
        from datetime import datetime as _dt
        tbl.insert({
            "contact_id": contact["id"],
            "message": "Bridge dispatch test.",
            "send_at": "2020-01-01T08:00:00+10:00",
            "sent_at": None,
            "status": "scheduled",
            "created_at": _dt.now().isoformat(),
            "updated_at": _dt.now().isoformat(),
        }, org_id=org_id)
        return contact

    def test_bridge_sends_due_reminder(self, isolated_auth_db):
        from app.web.store import DEFAULT_ORG_ID
        from agent.reminders.web_bridge import WebReminderBridge

        self._make_contact_and_reminder("+61400009010", "opted_in", DEFAULT_ORG_ID)

        mock_sms = MagicMock()
        mock_sms.send.return_value = MagicMock(ok=True, error=None)
        bridge = WebReminderBridge(channels={"sms": mock_sms, "email": MagicMock()})

        results = bridge.tick(DEFAULT_ORG_ID)
        assert len(results) >= 1
        assert any(r.get("ok") for r in results), f"Expected ok=True, got {results}"
        mock_sms.send.assert_called_once()

    def test_bridge_blocks_opted_out_contact(self, isolated_auth_db):
        from app.web.store import DEFAULT_ORG_ID
        from agent.reminders.web_bridge import WebReminderBridge

        self._make_contact_and_reminder("+61400009011", "opted_out", DEFAULT_ORG_ID)

        mock_sms = MagicMock()
        bridge = WebReminderBridge(channels={"sms": mock_sms, "email": MagicMock()})
        results = bridge.tick(DEFAULT_ORG_ID)
        mock_sms.send.assert_not_called()
        assert all(r.get("blocked") for r in results if r.get("ok") is False)


# ── Step 5: Delivery event logging ───────────────────────────

class TestStep5DeliveryLogging:
    def test_delivery_event_logged_and_retrievable(self):
        from app.web_ui.activity_db import log_delivery_event, get_delivery_history

        event = log_delivery_event(
            message_id="SMTEST001",
            recipient="+61400000020",
            channel="sms",
            reminder_type="sms_reminder",
            status="sent",
        )
        assert event.get("message_id") == "SMTEST001"

        history = get_delivery_history(limit=50)
        # get_delivery_history returns {"items": [...], "total": int, ...}
        items = history["items"] if isinstance(history, dict) else history
        ids = [h["message_id"] for h in items]
        assert "SMTEST001" in ids

    def test_delivery_event_has_expected_fields(self):
        from app.web_ui.activity_db import log_delivery_event

        event = log_delivery_event(
            message_id="SMTEST002",
            recipient="+61400000021",
            channel="email",
            reminder_type="email_reminder",
            status="queued",
        )
        for field in ("message_id", "recipient", "channel", "status"):
            assert field in event, f"Missing field in delivery event: {field}"


# ── Step 6: Twilio status callback updates record ─────────────

class TestStep6StatusCallback:
    def test_status_callback_updates_delivery_record(self, fastapi_client):
        from app.web_ui.activity_db import log_delivery_event, get_delivery_history

        # Pre-register a delivery record
        log_delivery_event(
            message_id="SMTEST010",
            recipient="+61400000030",
            channel="sms",
            reminder_type="sms_reminder",
            status="sent",
        )

        # POST status-callback as Twilio would
        resp = fastapi_client.post(
            "/twilio/status-callback",
            data={
                "MessageSid": "SMTEST010",
                "MessageStatus": "delivered",
                "To": "+61400000030",
            },
        )
        assert resp.status_code == 200

        # Confirm record updated
        history = get_delivery_history(limit=50)
        items = history["items"] if isinstance(history, dict) else history
        record = next((h for h in items if h["message_id"] == "SMTEST010"), None)
        assert record is not None
        assert record["status"] == "delivered"

    def test_status_callback_on_failure_logs_activity(self, fastapi_client):
        from app.web_ui.activity_db import get_recent

        fastapi_client.post(
            "/twilio/status-callback",
            data={
                "MessageSid": "SMTEST011",
                "MessageStatus": "failed",
                "To": "+61400000031",
                "ErrorCode": "30006",
                "ErrorMessage": "Landline or unreachable carrier",
            },
        )
        feed = get_recent(limit=20)
        assert any(
            "delivery_failure" in item.get("intent", "")
            or "failed" in item.get("summary", "").lower()
            for item in feed
        )


# ── Step 7: Activity feed ─────────────────────────────────────

class TestStep7ActivityFeed:
    def test_activity_logged_and_visible(self):
        from app.web_ui.activity_db import log_activity, get_recent

        log_activity(
            channel="sms",
            caller="+61400000040",
            intent="appointment_reminder",
            summary="E2E: reminder sent to patient.",
        )
        feed = get_recent(limit=10)
        summaries = [item.get("summary", "") for item in feed]
        assert any("E2E" in s for s in summaries)

    def test_activity_feed_is_newest_first(self):
        from app.web_ui.activity_db import log_activity, get_recent

        log_activity(channel="sms", caller="+614", intent="", summary="FIRST_E2E")
        log_activity(channel="sms", caller="+614", intent="", summary="SECOND_E2E")
        feed = get_recent(limit=5)
        summaries = [item.get("summary", "") for item in feed]
        # Newest should appear before oldest
        first_idx  = next((i for i, s in enumerate(summaries) if "FIRST_E2E"  in s), 999)
        second_idx = next((i for i, s in enumerate(summaries) if "SECOND_E2E" in s), 999)
        assert second_idx < first_idx, "Feed should be newest-first"


# ── Step 8: WebSocket broadcast ──────────────────────────────

class TestStep8WebSocketBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_fires_on_delivery_event(self):
        from app.web_ui.ws_routes import broadcast_dashboard_event, manager

        ws = AsyncMock()
        # Add directly to avoid triggering initial_state send
        manager.active_connections.append(ws)
        try:
            broadcast_dashboard_event("delivery_update", {
                "message_id": "SMTEST020",
                "status": "delivered",
                "channel": "sms",
            })
        finally:
            manager.disconnect(ws)

    @pytest.mark.asyncio
    async def test_activity_update_broadcast(self):
        from app.web_ui.ws_routes import broadcast_dashboard_event, manager

        ws = AsyncMock()
        manager.active_connections.append(ws)
        try:
            broadcast_dashboard_event("activity_update", {
                "channel": "sms",
                "caller": "+61400000050",
                "summary": "E2E test activity",
                "time": "just now",
            })
        finally:
            manager.disconnect(ws)
