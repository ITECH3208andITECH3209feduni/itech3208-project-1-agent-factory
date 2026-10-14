# tests/test_twilio_routes_receptionist.py — app/web_ui/twilio_routes.py
#
# Covers switching the real inbound SMS/voice webhooks from the generic
# Orchestrator to the Receptionist (FAQ, escalation, appointment
# booking, and the PROJ-445/446 booking->reminder tie-in), and that
# contact_channel/contact_address are passed through so that tie-in can
# actually fire from a real phone call or text.
import pytest
from fastapi.testclient import TestClient

import app.web_ui.twilio_routes as twilio_routes
from app.web_ui.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_activity_and_consent(monkeypatch):
    monkeypatch.setattr(twilio_routes, "log_activity", lambda **kw: None)
    monkeypatch.setattr(twilio_routes, "handle_inbound", lambda body, frm, to: None)


def test_sms_webhook_calls_receptionist_with_contact_info(client, monkeypatch):
    captured = {}

    def fake_handle(message, session_id=None, contact_channel=None, contact_address=None):
        captured.update(
            message=message, session_id=session_id,
            contact_channel=contact_channel, contact_address=contact_address,
        )
        return {"answer": "Sure, here's the answer.", "intent": "faq"}

    monkeypatch.setattr(twilio_routes._receptionist, "handle", fake_handle)

    r = client.post("/twilio/sms", data={"Body": "What are your hours?", "From": "+15551234567", "To": "+18024448729"})
    assert r.status_code == 200
    assert "Sure, here" in r.text
    assert captured["contact_channel"] == "sms"
    assert captured["contact_address"] == "+15551234567"
    assert captured["session_id"] == "+15551234567"


def test_sms_webhook_defaults_empty_body_to_hello(client, monkeypatch):
    captured = {}

    def fake_handle(message, **kw):
        captured["message"] = message
        return {"answer": "hi", "intent": "general"}

    monkeypatch.setattr(twilio_routes._receptionist, "handle", fake_handle)
    client.post("/twilio/sms", data={"From": "+15551234567"})
    assert captured["message"] == "Hello"


def test_sms_webhook_strips_markdown_from_receptionist_answer(client, monkeypatch):
    monkeypatch.setattr(
        twilio_routes._receptionist, "handle",
        lambda message, **kw: {"answer": "**Booked!** See [details](http://x)", "intent": "appointment"},
    )
    r = client.post("/twilio/sms", data={"Body": "book me in", "From": "+15551234567"})
    assert "**" not in r.text
    assert "Booked!" in r.text


def test_voice_reply_calls_receptionist_with_contact_info(client, monkeypatch):
    captured = {}

    def fake_handle(message, session_id=None, contact_channel=None, contact_address=None):
        captured.update(
            message=message, session_id=session_id,
            contact_channel=contact_channel, contact_address=contact_address,
        )
        return {"answer": "Your appointment is booked.", "intent": "appointment"}

    monkeypatch.setattr(twilio_routes._receptionist, "handle", fake_handle)

    r = client.post(
        "/twilio/voice/reply",
        data={"SpeechResult": "book me a consultation", "CallSid": "CA123", "From": "+15559876543"},
    )
    assert r.status_code == 200
    assert "appointment is booked" in r.text
    assert captured["contact_channel"] == "voice"
    assert captured["contact_address"] == "+15559876543"
    assert captured["session_id"] == "CA123"


def test_voice_reply_goodbye_never_reaches_receptionist(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        twilio_routes._receptionist, "handle",
        lambda *a, **kw: calls.append(1) or {"answer": "", "intent": "general"},
    )
    r = client.post("/twilio/voice/reply", data={"SpeechResult": "goodbye", "CallSid": "CA1", "From": "+1555"})
    assert calls == []
    assert "Goodbye" in r.text


def test_sms_stop_keyword_never_reaches_receptionist(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        twilio_routes._receptionist, "handle",
        lambda *a, **kw: calls.append(1) or {"answer": "", "intent": "general"},
    )
    monkeypatch.setattr(twilio_routes, "handle_inbound", lambda body, frm, to: "You've been unsubscribed.")

    r = client.post("/twilio/sms", data={"Body": "STOP", "From": "+15551234567", "To": "+18024448729"})
    assert calls == []
    assert "unsubscribed" in r.text


def test_voice_text_drops_emoji_and_markdown():
    """Polly reads emoji aloud by name, so voice replies must not contain them."""
    from app.web_ui.twilio_routes import _speakable

    out = _speakable("**Hello!** 😊 We offer research 📚 and Amazon tools 🛒 ✅ — call anytime 👍🏽")
    assert out == "Hello! We offer research and Amazon tools — call anytime"
    assert _speakable("Plain sentence, no emoji.") == "Plain sentence, no emoji."


def test_goodbye_triggers_post_call_summary(client, monkeypatch):
    calls = []
    monkeypatch.setattr(twilio_routes, "_summarise_call_later", lambda sid, caller, org_id=None: calls.append((sid, caller)))
    r = client.post("/twilio/voice/reply", data={"SpeechResult": "okay goodbye", "CallSid": "CA77", "From": "+15551234567"})
    assert r.status_code == 200 and "Hangup" in r.text
    assert calls == [("CA77", "+15551234567")]


def test_completed_voice_status_callback_triggers_post_call_summary(client, monkeypatch):
    calls = []
    monkeypatch.setattr(twilio_routes, "_summarise_call_later", lambda sid, caller, org_id=None: calls.append((sid, caller)))
    monkeypatch.setattr(twilio_routes, "update_delivery_status", lambda **kw: True)
    r = client.post("/twilio/status-callback", data={"CallSid": "CA78", "CallStatus": "completed", "From": "+15551234567", "To": "+18024448729"})
    assert r.status_code == 200
    assert calls == [("CA78", "+15551234567")]


def test_hangup_without_goodbye_is_not_summarised_until_the_call_completes(client, monkeypatch):
    calls = []
    monkeypatch.setattr(twilio_routes, "_summarise_call_later", lambda sid, caller, org_id=None: calls.append(sid))
    monkeypatch.setattr(twilio_routes, "update_delivery_status", lambda **kw: True)
    client.post("/twilio/status-callback", data={"CallSid": "CA79", "CallStatus": "ringing", "From": "+15551234567"})
    assert calls == []
