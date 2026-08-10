# tests/test_calendar_client.py — agent/calendar_client.py (PROJ-354, PROJ-209-218)
import sys
import types

import pytest

from agent import calendar_client


@pytest.fixture(autouse=True)
def _configured(tmp_path, monkeypatch):
    """Point at a fake-but-existing key file so is_configured() is True
    by default; individual tests override as needed."""
    key_path = tmp_path / "fake-key.json"
    key_path.write_text("{}")
    monkeypatch.setattr(calendar_client, "GOOGLE_CALENDAR_KEY_PATH", str(key_path))
    monkeypatch.setattr(calendar_client, "GOOGLE_CALENDAR_ID", "test-cal@group.calendar.google.com")


@pytest.fixture
def fake_google_auth(monkeypatch):
    """Stub out google.oauth2.service_account + google.auth.transport.requests
    so _get_access_token() succeeds without real credentials."""

    class _FakeCreds:
        token = "fake-access-token"

        def refresh(self, request):
            pass

    class _FakeServiceAccount:
        @staticmethod
        def Credentials():
            pass

    fake_service_account_module = types.ModuleType("google.oauth2.service_account")
    fake_service_account_module.Credentials = types.SimpleNamespace(
        from_service_account_file=lambda path, scopes: _FakeCreds()
    )

    fake_transport_module = types.ModuleType("google.auth.transport.requests")
    fake_transport_module.Request = lambda: object()

    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", fake_service_account_module)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", fake_transport_module)
    # Make sure parent packages resolve too
    monkeypatch.setitem(sys.modules, "google.oauth2", types.ModuleType("google.oauth2"))
    monkeypatch.setitem(sys.modules, "google.auth.transport", types.ModuleType("google.auth.transport"))
    monkeypatch.setitem(sys.modules, "google.auth", types.ModuleType("google.auth"))
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))


def test_is_configured_true_when_key_and_id_set():
    assert calendar_client.is_configured() is True


def test_is_configured_false_when_key_path_missing(monkeypatch):
    monkeypatch.setattr(calendar_client, "GOOGLE_CALENDAR_KEY_PATH", "")
    assert calendar_client.is_configured() is False


def test_is_configured_false_when_key_file_absent(monkeypatch):
    monkeypatch.setattr(calendar_client, "GOOGLE_CALENDAR_KEY_PATH", "/nowhere/key.json")
    assert calendar_client.is_configured() is False


def test_book_appointment_not_configured(monkeypatch):
    monkeypatch.setattr(calendar_client, "GOOGLE_CALENDAR_KEY_PATH", "")
    result = calendar_client.book_appointment(
        "Test", "2026-08-10T14:00:00", "2026-08-10T14:30:00"
    )
    assert result["ok"] is False
    assert "not configured" in result["error"]


def test_book_appointment_success(monkeypatch, fake_google_auth):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"htmlLink": "https://calendar.google.com/event?eid=abc123"}

    monkeypatch.setattr(
        "requests.post", lambda url, headers, json, timeout: _FakeResponse()
    )

    result = calendar_client.book_appointment(
        "Consultation", "2026-08-10T14:00:00", "2026-08-10T14:30:00"
    )
    assert result["ok"] is True
    assert result["event_url"] == "https://calendar.google.com/event?eid=abc123"


def test_book_appointment_api_error(monkeypatch, fake_google_auth):
    class _FakeResponse:
        status_code = 403
        text = "Forbidden — calendar not shared with service account"

    monkeypatch.setattr(
        "requests.post", lambda url, headers, json, timeout: _FakeResponse()
    )

    result = calendar_client.book_appointment(
        "Consultation", "2026-08-10T14:00:00", "2026-08-10T14:30:00"
    )
    assert result["ok"] is False
    assert "403" in result["error"]


def test_book_appointment_network_error(monkeypatch, fake_google_auth):
    import requests

    def _raise(*args, **kwargs):
        raise requests.RequestException("connection reset")

    monkeypatch.setattr("requests.post", _raise)

    result = calendar_client.book_appointment(
        "Consultation", "2026-08-10T14:00:00", "2026-08-10T14:30:00"
    )
    assert result["ok"] is False
    assert "Network error" in result["error"]
