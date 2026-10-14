# tests/test_password_reset_routes.py — PROJ-481
#
# The forgot/reset password pages posted to endpoints that did not exist.
# These cover the wired-in routes end to end, including the SMTP send with a
# fake server so no real mail goes out.
import pytest
from fastapi.testclient import TestClient

from app.web_ui.main import app

PASSWORD = "a-long-password-1"


@pytest.fixture
def anon(tmp_path, monkeypatch):
    from auth import db as auth_db, org_routes, password_reset, tenancy

    path = str(tmp_path / "auth_users.db")
    monkeypatch.setattr(auth_db, "DB_PATH", path)
    monkeypatch.setattr(org_routes, "DB_PATH", path)
    auth_db.init_db()
    tenancy.init_tenancy()
    password_reset.init_reset_table()
    c = TestClient(app)
    c.cookies.clear()
    return c


@pytest.fixture
def captured(monkeypatch):
    """Catch the reset link instead of mailing or logging it."""
    from auth import password_reset

    sent = []
    monkeypatch.setattr(password_reset, "deliver_reset_link",
                        lambda email, token: sent.append((email, token)) or "smtp")
    return sent


def _register(c, email="owner.reset@example.com"):
    r = c.post("/orgs/register", json={"org_name": "Reset Clinic", "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text


def test_full_reset_flow(anon, captured):
    _register(anon)
    r = anon.post("/auth/forgot-password", json={"email": "Owner.Reset@example.com"})
    assert r.status_code == 202
    assert len(captured) == 1 and captured[0][0] == "owner.reset@example.com"
    token = captured[0][1]

    assert anon.post("/auth/reset-password", json={"token": token, "new_password": "brand-new-pass-2"}).status_code == 200
    assert anon.post("/auth/login", json={"email": "owner.reset@example.com", "password": PASSWORD}).status_code == 401
    assert anon.post("/auth/login", json={"email": "owner.reset@example.com",
                                         "password": "brand-new-pass-2"}).status_code == 200
    # Single use.
    r = anon.post("/auth/reset-password", json={"token": token, "new_password": "third-pass-333"})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_unknown_email_gets_the_same_answer_and_no_send(anon, captured):
    _register(anon)
    known = anon.post("/auth/forgot-password", json={"email": "owner.reset@example.com"}).json()["message"]
    unknown = anon.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert unknown.status_code == 202 and unknown.json()["message"] == known
    assert len(captured) == 1


def test_short_password_and_bad_token_are_refused(anon):
    assert anon.post("/auth/reset-password", json={"token": "x", "new_password": "short"}).status_code == 422
    assert anon.post("/auth/reset-password", json={"token": "made-up", "new_password": "long-enough-1"}).status_code == 400


def test_reset_email_goes_through_smtp_when_configured(anon, monkeypatch):
    from auth import password_reset

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, local_hostname=None):
            sent.append(("connect", host, port))
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            sent.append(("starttls",))
        def login(self, user, password):
            sent.append(("login", user))
        def send_message(self, msg):
            sent.append(("send", msg["To"], msg["From"], msg.get_content()))

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "agentfactory.demo@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "agentfactory.demo@example.com")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr(password_reset, "APP_BASE_URL", "https://agent-factory.example")

    _register(anon)
    r = anon.post("/auth/forgot-password", json={"email": "owner.reset@example.com"})
    assert r.status_code == 202 and "delivery" not in r.json()
    assert ("starttls",) in sent and ("login", "agentfactory.demo@example.com") in sent
    send = next(s for s in sent if s[0] == "send")
    assert send[1] == "owner.reset@example.com" and send[2] == "agentfactory.demo@example.com"
    assert "https://agent-factory.example/reset-password?token=" in send[3]
