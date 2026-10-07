# tests/test_delivery.py — agent/delivery/* (PROJ-431)
import smtplib

import pytest
from twilio.base.exceptions import TwilioRestException

from agent.delivery.base import DeliveryResult, RetryPolicy, send_with_retry
from agent.delivery.email_channel import EmailChannel
from agent.delivery.sms_channel import SMSChannel
from agent.delivery.voice_channel import VoiceChannel


# ── Common interface + retry/backoff (PROJ-430) ─────────────────


def test_send_with_retry_succeeds_first_try():
    calls = []

    def attempt():
        calls.append(1)
        return DeliveryResult(ok=True, channel="x", to="t")

    result = send_with_retry(attempt, RetryPolicy(max_attempts=3), sleep=lambda s: None)
    assert result.ok is True
    assert result.attempts == 1
    assert len(calls) == 1


def test_send_with_retry_succeeds_after_retriable_failures():
    attempts = {"n": 0}

    def attempt():
        attempts["n"] += 1
        if attempts["n"] < 3:
            return DeliveryResult(ok=False, channel="x", to="t", retriable=True)
        return DeliveryResult(ok=True, channel="x", to="t")

    result = send_with_retry(attempt, RetryPolicy(max_attempts=5), sleep=lambda s: None)
    assert result.ok is True
    assert result.attempts == 3
    assert attempts["n"] == 3


def test_send_with_retry_exhausts_max_attempts():
    attempts = {"n": 0}

    def attempt():
        attempts["n"] += 1
        return DeliveryResult(ok=False, channel="x", to="t", retriable=True)

    result = send_with_retry(attempt, RetryPolicy(max_attempts=3), sleep=lambda s: None)
    assert result.ok is False
    assert result.attempts == 3
    assert attempts["n"] == 3


def test_send_with_retry_stops_immediately_on_non_retriable():
    attempts = {"n": 0}

    def attempt():
        attempts["n"] += 1
        return DeliveryResult(ok=False, channel="x", to="t", retriable=False)

    result = send_with_retry(attempt, RetryPolicy(max_attempts=5), sleep=lambda s: None)
    assert result.ok is False
    assert attempts["n"] == 1


def test_send_with_retry_uses_exponential_backoff():
    sleeps = []

    def attempt():
        return DeliveryResult(ok=False, channel="x", to="t", retriable=True)

    send_with_retry(
        attempt,
        RetryPolicy(max_attempts=4, base_delay=1.0, backoff_factor=2.0, max_delay=30.0),
        sleep=lambda s: sleeps.append(s),
    )
    assert sleeps == [1.0, 2.0, 4.0]


def test_retry_policy_caps_delay_at_max_delay():
    policy = RetryPolicy(base_delay=1.0, backoff_factor=10.0, max_delay=5.0)
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 5.0  # would be 10.0 uncapped
    assert policy.delay_for(3) == 5.0  # would be 100.0 uncapped


# ── SMS adapter (PROJ-427) ───────────────────────────────────────


@pytest.fixture(autouse=True)
def _twilio_configured(monkeypatch):
    monkeypatch.setattr("agent.delivery.sms_channel.TWILIO_ACCOUNT_SID", "ACxxx")
    monkeypatch.setattr("agent.delivery.sms_channel.TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr("agent.delivery.sms_channel.TWILIO_FROM_NUMBER", "+15550000000")
    monkeypatch.setattr("agent.delivery.voice_channel.TWILIO_ACCOUNT_SID", "ACxxx")
    monkeypatch.setattr("agent.delivery.voice_channel.TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr("agent.delivery.voice_channel.TWILIO_FROM_NUMBER", "+15550000000")


class _FakeMessages:
    def __init__(self, side_effect=None, sid="SMxxx"):
        self.side_effect = side_effect
        self.sid = sid
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.side_effect:
            raise self.side_effect
        return type("Msg", (), {"sid": self.sid})()


class _FakeCalls(_FakeMessages):
    def __init__(self, side_effect=None, sid="CAxxx"):
        super().__init__(side_effect=side_effect, sid=sid)


class _FakeSMSClient:
    def __init__(self, messages: _FakeMessages):
        self.messages = messages


class _FakeVoiceClient:
    def __init__(self, calls: _FakeCalls):
        self.calls = calls


def test_sms_not_configured(monkeypatch):
    monkeypatch.setattr("agent.delivery.sms_channel.TWILIO_ACCOUNT_SID", "")
    channel = SMSChannel(client=_FakeSMSClient(_FakeMessages()))
    result = channel._send_once("+15551234567", "Reminder!")
    assert result.ok is False
    assert result.retriable is False
    assert "not configured" in result.error


def test_sms_send_success():
    fake_messages = _FakeMessages(sid="SM123")
    channel = SMSChannel(client=_FakeSMSClient(fake_messages))
    result = channel.send("+15551234567", "Your appointment is tomorrow.", sleep=lambda s: None)
    assert result.ok is True
    assert result.provider_id == "SM123"
    assert fake_messages.calls[0]["to"] == "+15551234567"
    assert fake_messages.calls[0]["from_"] == "+15550000000"


def test_sms_non_retriable_twilio_error_does_not_retry():
    exc = TwilioRestException(status=400, uri="/Messages", msg="invalid number", code=21211)
    fake_messages = _FakeMessages(side_effect=exc)
    channel = SMSChannel(client=_FakeSMSClient(fake_messages))
    result = channel.send("+1bad", "hi", sleep=lambda s: None)
    assert result.ok is False
    assert result.retriable is False
    assert len(fake_messages.calls) == 1


def test_sms_retriable_twilio_error_retries():
    exc = TwilioRestException(status=500, uri="/Messages", msg="server error", code=20500)
    fake_messages = _FakeMessages(side_effect=exc)
    channel = SMSChannel(client=_FakeSMSClient(fake_messages))
    result = channel.send(
        "+15551234567", "hi", retry_policy=RetryPolicy(max_attempts=3), sleep=lambda s: None
    )
    assert result.ok is False
    assert result.retriable is True
    assert len(fake_messages.calls) == 3


def test_sms_unexpected_exception_is_retriable():
    fake_messages = _FakeMessages(side_effect=ConnectionError("reset"))
    channel = SMSChannel(client=_FakeSMSClient(fake_messages))
    result = channel._send_once("+15551234567", "hi")
    assert result.ok is False
    assert result.retriable is True


# ── Voice adapter (PROJ-428) ─────────────────────────────────────


def test_voice_not_configured(monkeypatch):
    monkeypatch.setattr("agent.delivery.voice_channel.TWILIO_FROM_NUMBER", "")
    channel = VoiceChannel(client=_FakeVoiceClient(_FakeCalls()))
    result = channel._send_once("+15551234567", "Your appointment is tomorrow.")
    assert result.ok is False
    assert result.retriable is False


def test_voice_send_success_uses_polly_twiml():
    fake_calls = _FakeCalls(sid="CA123")
    channel = VoiceChannel(client=_FakeVoiceClient(fake_calls))
    result = channel.send("+15551234567", "Your appointment is tomorrow.", sleep=lambda s: None)
    assert result.ok is True
    assert result.provider_id == "CA123"
    twiml = fake_calls.calls[0]["twiml"]
    assert "Polly.Joanna" in twiml
    assert "Your appointment is tomorrow." in twiml


def test_voice_non_retriable_error_does_not_retry():
    exc = TwilioRestException(status=400, uri="/Calls", msg="invalid number", code=21211)
    fake_calls = _FakeCalls(side_effect=exc)
    channel = VoiceChannel(client=_FakeVoiceClient(fake_calls))
    result = channel.send("+1bad", "hi", sleep=lambda s: None)
    assert result.ok is False
    assert len(fake_calls.calls) == 1


# ── Email adapter (PROJ-429) ──────────────────────────────────────


@pytest.fixture(autouse=True)
def _smtp_configured(monkeypatch):
    monkeypatch.setattr("agent.delivery.email_channel.SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr("agent.delivery.email_channel.SMTP_PORT", 587)
    monkeypatch.setattr("agent.delivery.email_channel.SMTP_FROM_EMAIL", "reminders@example.com")
    monkeypatch.setattr("agent.delivery.email_channel.SMTP_USERNAME", "user")
    monkeypatch.setattr("agent.delivery.email_channel.SMTP_PASSWORD", "pass")
    monkeypatch.setattr("agent.delivery.email_channel.SMTP_USE_TLS", True)


class _FakeSMTP:
    def __init__(self, side_effect=None):
        self.side_effect = side_effect
        self.sent = []
        self.logged_in = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, username, password):
        self.logged_in = True

    def send_message(self, msg):
        if self.side_effect:
            raise self.side_effect
        self.sent.append(msg)


def test_email_not_configured(monkeypatch):
    monkeypatch.setattr("agent.delivery.email_channel.SMTP_HOST", "")
    channel = EmailChannel(smtp_client_factory=lambda: _FakeSMTP())
    result = channel._send_once("user@example.com", "hi")
    assert result.ok is False
    assert result.retriable is False


def test_email_invalid_address_is_non_retriable():
    channel = EmailChannel(smtp_client_factory=lambda: _FakeSMTP())
    result = channel._send_once("not-an-email", "hi")
    assert result.ok is False
    assert result.retriable is False


def test_email_send_success():
    fake_smtp = _FakeSMTP()
    channel = EmailChannel(smtp_client_factory=lambda: fake_smtp)
    result = channel.send("user@example.com", "Your appointment is tomorrow.", sleep=lambda s: None)
    assert result.ok is True
    assert fake_smtp.logged_in is True
    assert len(fake_smtp.sent) == 1
    assert fake_smtp.sent[0]["To"] == "user@example.com"


def test_email_recipients_refused_is_non_retriable():
    exc = smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"mailbox unavailable")})
    fake_smtp = _FakeSMTP(side_effect=exc)
    channel = EmailChannel(smtp_client_factory=lambda: fake_smtp)
    result = channel.send("user@example.com", "hi", sleep=lambda s: None)
    assert result.ok is False
    assert result.retriable is False


def test_email_auth_error_is_non_retriable():
    exc = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    fake_smtp = _FakeSMTP(side_effect=exc)
    channel = EmailChannel(smtp_client_factory=lambda: fake_smtp)
    result = channel.send("user@example.com", "hi", sleep=lambda s: None)
    assert result.ok is False
    assert result.retriable is False


def test_email_transient_smtp_error_is_retriable():
    exc = smtplib.SMTPConnectError(421, b"service not available")
    fake_smtp = _FakeSMTP(side_effect=exc)
    channel = EmailChannel(smtp_client_factory=lambda: fake_smtp)
    result = channel.send(
        "user@example.com", "hi", retry_policy=RetryPolicy(max_attempts=2), sleep=lambda s: None
    )
    assert result.ok is False
    assert result.retriable is True
    assert result.attempts == 2
