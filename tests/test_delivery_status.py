# tests/test_delivery.py
# ──────────────────────────────────────────────────────────────
# Unit and integration tests for Delivery Status & History
# PROJ-397 (Delivery Status & History)
# PROJ-432 (Twilio status callback webhook)
# PROJ-433 (Email bounce / failure handling)
# PROJ-434 (Delivery history view per reminder)
# ──────────────────────────────────────────────────────────────

import pytest
from fastapi.testclient import TestClient
from app.web_ui.main import app
from app.web_ui.activity_db import (
    add_email_suppression,
    get_delivery_by_id,
    get_delivery_history,
    is_email_suppressed,
    log_delivery_event,
    update_delivery_status,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_log_delivery_event_and_retrieve():
    """Verify log_delivery_event records the message and can be retrieved (PROJ-434)."""
    msg_id = "TEST-SMS-001"
    record = log_delivery_event(
        message_id=msg_id,
        recipient="+61412345678",
        channel="sms",
        reminder_type="appointment",
        status="sent",
        metadata={"note": "Test reminder"},
    )
    assert record["message_id"] == msg_id
    assert record["recipient"] == "+61412345678"
    assert record["status"] == "sent"

    retrieved = get_delivery_by_id(msg_id)
    assert retrieved is not None
    assert retrieved["message_id"] == msg_id
    assert retrieved["reminder_type"] == "appointment"


def test_update_delivery_status():
    """Verify status updates and delivery timestamps (PROJ-432, PROJ-434)."""
    msg_id = "TEST-SMS-UPDATE"
    log_delivery_event(
        message_id=msg_id,
        recipient="+61498765432",
        channel="sms",
        reminder_type="alert",
        status="sent",
    )

    updated = update_delivery_status(
        message_id=msg_id,
        status="delivered",
    )
    assert updated is not None
    assert updated["status"] == "delivered"
    assert updated["delivered_at"] != ""


def test_twilio_status_callback_webhook(client):
    """Verify POST /twilio/status-callback processes delivery status updates (PROJ-432)."""
    msg_id = "SM_TWILIO_TEST_123"
    # Pre-register sent message
    log_delivery_event(
        message_id=msg_id,
        recipient="+61455556666",
        channel="sms",
        reminder_type="appointment",
        status="sent",
    )

    # Simulate Twilio webhook callback
    resp = client.post(
        "/twilio/status-callback",
        data={
            "MessageSid": msg_id,
            "MessageStatus": "delivered",
            "To": "+61455556666",
            "From": "+61400000000",
        },
    )
    assert resp.status_code == 200
    assert "Response" in resp.text

    rec = get_delivery_by_id(msg_id)
    assert rec is not None
    assert rec["status"] == "delivered"


def test_twilio_status_callback_failure(client):
    """Verify Twilio status callback records error codes on delivery failure (PROJ-432)."""
    msg_id = "SM_TWILIO_FAIL_456"
    resp = client.post(
        "/twilio/status-callback",
        data={
            "MessageSid": msg_id,
            "MessageStatus": "undelivered",
            "To": "+61411112222",
            "ErrorCode": "30008",
            "ErrorMessage": "Unknown carrier delivery error",
        },
    )
    assert resp.status_code == 200

    rec = get_delivery_by_id(msg_id)
    assert rec is not None
    assert rec["status"] == "undelivered"
    assert rec["error_code"] == "30008"
    assert "Unknown carrier delivery error" in rec["error_message"]


def test_email_bounce_handling_and_suppression(client):
    """Verify email bounce webhook updates status and suppresses hard bounces (PROJ-433)."""
    test_email = "invalid_user_bounce@example.com"
    msg_id = "EM_BOUNCE_TEST_001"

    # Log initial send
    log_delivery_event(
        message_id=msg_id,
        recipient=test_email,
        channel="email",
        reminder_type="followup",
        status="sent",
    )

    # Post bounce webhook
    bounce_payload = {
        "email": test_email,
        "message_id": msg_id,
        "bounce_type": "hard_bounce",
        "reason": "550 5.1.1 User unknown",
        "diagnostic_code": "550",
    }
    resp = client.post("/delivery/email/bounce", json=bounce_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify message status became 'bounced'
    rec = get_delivery_by_id(msg_id)
    assert rec is not None
    assert rec["status"] == "bounced"
    assert "550" in rec["error_code"]

    # Verify email is now suppressed
    assert is_email_suppressed(test_email) is True

    # Attempting to send to suppressed email should now be rejected (400)
    send_resp = client.post(
        "/delivery/send",
        json={"recipient": test_email, "channel": "email", "message": "Test"},
    )
    assert send_resp.status_code == 400
    assert "suppressed" in send_resp.json()["detail"]


def test_delivery_history_filtering_and_pagination(client):
    """Verify GET /delivery/history supports filtering by status, channel, search (PROJ-434)."""
    # Seed unique items
    log_delivery_event("FILTER-TEST-1", "alice@example.com", "email", "appointment", "delivered")
    log_delivery_event("FILTER-TEST-2", "+61499998888", "sms", "alert", "failed")

    resp = client.get("/delivery/history?limit=10&status=failed")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert all(item["status"] == "failed" for item in data["items"])

    resp_sms = client.get("/delivery/history?channel=sms")
    assert resp_sms.status_code == 200
    assert all(item["channel"] == "sms" for item in resp_sms.json()["items"])


def test_delivery_retry_action(client):
    """Verify POST /delivery/retry resets status to queued and increments retry_count (PROJ-434)."""
    msg_id = "RETRY-TEST-001"
    rec = log_delivery_event(msg_id, "+61400112233", "sms", "appointment", "failed")
    
    retry_resp = client.post(f"/delivery/retry/{rec['id']}")
    assert retry_resp.status_code == 200
    retried_record = retry_resp.json()["record"]
    assert retried_record["status"] == "queued"
    assert retried_record["retry_count"] >= 1


def _fake_channel(monkeypatch, result):
    from app.web_ui import delivery_routes

    calls = []

    class Fake:
        def send(self, to, message, **kw):
            calls.append((to, message, kw))
            return result

    monkeypatch.setattr(delivery_routes, "_channel_for", lambda name: Fake())
    return calls


def test_send_really_hands_the_message_to_the_channel(client, monkeypatch):
    """POST /delivery/send must call the provider, not only write a history row."""
    from agent.delivery import DeliveryResult

    calls = _fake_channel(monkeypatch, DeliveryResult(ok=True, channel="email", to="a@example.com"))
    resp = client.post(
        "/delivery/send",
        json={"recipient": "a@example.com", "channel": "email", "message": "See you Friday"},
    )
    assert resp.status_code == 200, resp.text
    assert calls and calls[0][0] == "a@example.com" and calls[0][1] == "See you Friday"
    assert get_delivery_by_id(resp.json()["message_id"])["status"] == "sent"


def test_send_failure_is_recorded_as_failed_and_reported(client, monkeypatch):
    from agent.delivery import DeliveryResult

    _fake_channel(
        monkeypatch,
        DeliveryResult(ok=False, channel="email", to="a@example.com", error="535 bad credentials"),
    )
    resp = client.post(
        "/delivery/send",
        json={"recipient": "a@example.com", "channel": "email", "message": "x"},
    )
    assert resp.status_code == 502
    assert "535 bad credentials" in resp.json()["detail"]
    row = client.get("/delivery/history?status=failed&search=a@example.com").json()["items"][0]
    assert row["status"] == "failed" and "535" in row["error_message"]


def test_sms_history_row_uses_the_twilio_sid(client, monkeypatch):
    """So the Twilio status callback can later mark the same row delivered."""
    from agent.delivery import DeliveryResult

    _fake_channel(monkeypatch, DeliveryResult(ok=True, channel="sms", to="+15555550101", provider_id="SM123abc"))
    resp = client.post("/delivery/send", json={"recipient": "+15555550101", "channel": "sms", "message": "x"})
    assert resp.json()["message_id"] == "SM123abc"
