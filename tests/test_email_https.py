# tests/test_email_https.py — email over Brevo's HTTPS API, for hosts that
# block outgoing SMTP (Render's free plan).
import pytest

import agent.delivery.email_channel as ec
from agent.delivery import EmailChannel


class _Resp:
    def __init__(self, status, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture
def brevo(monkeypatch):
    monkeypatch.setattr(ec, "BREVO_API_KEY", "test-key-not-real")
    monkeypatch.setattr(ec, "SMTP_FROM_EMAIL", "clinic@example.com")
    monkeypatch.setattr(ec, "SMTP_HOST", "")
    monkeypatch.setenv("BRAND_NAME", "Bright Smile Dental")
    calls = []

    def answer(status, body=None, text=""):
        def post(url, json=None, headers=None, timeout=None):
            calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
            return _Resp(status, body, text)
        import requests
        monkeypatch.setattr(requests, "post", post)
    return calls, answer


def test_sends_through_brevo_when_the_key_is_set(brevo):
    calls, answer = brevo
    answer(201, {"messageId": "<abc@smtp-relay.mailin.fr>"})
    result = EmailChannel(smtp_client_factory=lambda: pytest.fail("SMTP must not be used")).send(
        "patient@example.com", "Hello", subject="Please confirm")
    assert result.ok and result.provider_id == "<abc@smtp-relay.mailin.fr>"
    sent = calls[0]
    assert sent["url"] == "https://api.brevo.com/v3/smtp/email"
    assert sent["headers"]["api-key"] == "test-key-not-real"
    assert sent["json"] == {"sender": {"email": "clinic@example.com", "name": "Bright Smile Dental"},
                            "to": [{"email": "patient@example.com"}], "subject": "Please confirm",
                            "textContent": "Hello"}


def test_a_rejected_request_is_not_retried(brevo):
    calls, answer = brevo
    answer(400, {"code": "invalid_parameter", "message": "sender is not valid"})
    result = EmailChannel().send("patient@example.com", "Hello", subject="x")
    assert not result.ok and "Brevo 400" in result.error and "sender is not valid" in result.error
    assert len(calls) == 1, "4xx is final"


def test_server_errors_are_retried(brevo):
    calls, answer = brevo
    answer(503, None, "busy")
    result = EmailChannel().send("patient@example.com", "Hello", subject="x", sleep=lambda s: None)
    assert not result.ok and result.retriable and len(calls) > 1


def test_without_a_key_smtp_is_used(monkeypatch):
    monkeypatch.setattr(ec, "BREVO_API_KEY", "")
    monkeypatch.setattr(ec, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(ec, "SMTP_FROM_EMAIL", "clinic@example.com")
    monkeypatch.setattr(ec, "SMTP_USERNAME", "")
    sent = []

    class _SMTP:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def send_message(self, msg):
            sent.append(msg["To"])

    result = EmailChannel(smtp_client_factory=_SMTP).send("patient@example.com", "Hello", subject="x")
    assert result.ok and sent == ["patient@example.com"]


def test_brevo_counts_as_configured_without_smtp(monkeypatch):
    monkeypatch.setattr(ec, "BREVO_API_KEY", "k")
    monkeypatch.setattr(ec, "SMTP_HOST", "")
    monkeypatch.setattr(ec, "SMTP_FROM_EMAIL", "clinic@example.com")
    assert EmailChannel().is_configured()


def test_password_reset_uses_brevo_when_set(monkeypatch):
    from auth import password_reset
    from config import settings
    from agent.delivery.base import DeliveryResult

    monkeypatch.setattr(settings, "BREVO_API_KEY", "k")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "clinic@example.com")
    sent = []
    monkeypatch.setattr(ec, "send_via_brevo", lambda to, subject, body: sent.append((to, subject, body))
                        or DeliveryResult(ok=True, channel="email", to=to))
    assert password_reset.deliver_reset_link("owner@example.com", "tok123") == "smtp"
    assert sent[0][0] == "owner@example.com" and "tok123" in sent[0][2] and "password" in sent[0][1]
