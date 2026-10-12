# tests/test_twilio_signature.py — PROJ-466
#
# Every Twilio webhook must verify X-Twilio-Signature once the app is on a
# public URL. Before this, only /twilio/sms did: /twilio/voice,
# /twilio/voice/reply and /twilio/status-callback accepted anything posted at
# them, so a forged status callback could rewrite delivery records and a forged
# /twilio/voice could spend Claude tokens on demand.
#
# The routes stay open when TWILIO_VALIDATE_SIGNATURE is unset so local dev and
# the rest of the suite keep working; these tests turn it on explicitly.
import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

import app.web_ui.twilio_routes as twilio_routes
from app.web_ui.main import app

TOKEN = "test-auth-token"

# Every signature-checked route, with a form body each one accepts.
ROUTES = [
    ("/twilio/sms", {"Body": "hello", "From": "+15551234567", "To": "+18024448729"}),
    ("/twilio/voice", {"From": "+15551234567", "CallSid": "CA123"}),
    ("/twilio/voice/reply", {"SpeechResult": "what are your hours", "CallSid": "CA123"}),
    ("/twilio/status-callback", {"MessageSid": "SM123", "MessageStatus": "delivered"}),
]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    """Keep the webhooks off the network, the DB and the Claude API."""
    monkeypatch.setattr(twilio_routes, "log_activity", lambda **kw: None)
    monkeypatch.setattr(twilio_routes, "handle_inbound", lambda body, frm, to: None)
    monkeypatch.setattr(twilio_routes, "update_delivery_status", lambda **kw: True)
    monkeypatch.setattr(twilio_routes, "log_delivery_event", lambda **kw: None)
    monkeypatch.setattr(
        twilio_routes._receptionist,
        "handle",
        lambda *a, **kw: {"answer": "Nine to five.", "intent": "faq"},
    )


@pytest.fixture
def validating(monkeypatch):
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "true")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)


def sign(url: str, params: dict) -> str:
    return RequestValidator(TOKEN).compute_signature(url, params)


@pytest.mark.parametrize("path,form", ROUTES)
def test_rejects_request_with_no_signature(client, validating, path, form):
    """The actual hole PROJ-466 closes: anyone posting at the public URL."""
    r = client.post(path, data=form)
    assert r.status_code == 403, f"{path} accepted an unsigned request"


@pytest.mark.parametrize("path,form", ROUTES)
def test_rejects_request_with_wrong_signature(client, validating, path, form):
    r = client.post(path, data=form, headers={"X-Twilio-Signature": "obviously-not-it"})
    assert r.status_code == 403, f"{path} accepted a forged signature"


@pytest.mark.parametrize("path,form", ROUTES)
def test_accepts_correctly_signed_request(client, validating, path, form):
    url = f"http://testserver{path}"
    r = client.post(path, data=form, headers={"X-Twilio-Signature": sign(url, form)})
    assert r.status_code == 200, f"{path} rejected a validly signed request"


@pytest.mark.parametrize("path,form", ROUTES)
def test_open_when_validation_disabled(client, monkeypatch, path, form):
    """Default-off, so local development and the existing suite are unaffected."""
    monkeypatch.delenv("TWILIO_VALIDATE_SIGNATURE", raising=False)
    r = client.post(path, data=form)
    assert r.status_code == 200


@pytest.mark.parametrize("path,form", ROUTES)
def test_fails_closed_when_token_missing(client, monkeypatch, path, form):
    """
    Validation asked for but impossible is a misconfiguration, not a reason to
    accept traffic — otherwise forgetting one secret silently reopens the hole.
    """
    monkeypatch.setenv("TWILIO_VALIDATE_SIGNATURE", "true")
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    r = client.post(path, data=form)
    assert r.status_code == 403


def test_signature_is_checked_before_any_side_effect(client, validating, monkeypatch):
    """A rejected request must not reach the receptionist or the delivery log."""
    called = []
    monkeypatch.setattr(
        twilio_routes._receptionist, "handle",
        lambda *a, **kw: called.append("receptionist") or {"answer": "x", "intent": ""},
    )
    monkeypatch.setattr(
        twilio_routes, "update_delivery_status",
        lambda **kw: called.append("delivery") or True,
    )

    client.post("/twilio/sms", data={"Body": "hi", "From": "+15551234567"})
    client.post("/twilio/status-callback", data={"MessageSid": "SM1", "MessageStatus": "sent"})

    assert called == []
