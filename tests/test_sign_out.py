# tests/test_sign_out.py — the dashboard's Sign out button and what it does.
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent import dashboard_help
from app.web_ui.main import app

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_sign_out_ends_the_server_session():
    from agent.auth import create_session_token
    from app.web_ui.auth_routes import COOKIE_NAME

    client = TestClient(app)
    client.cookies.clear()
    # The cookie as the server sets it at sign-in (same domain and path as the browser keeps).
    client.cookies.set(COOKIE_NAME, create_session_token("pytest"), domain="testserver.local", path="/")
    assert client.get("/calendar/appointments").status_code == 200
    r = client.post("/auth/logout", json={})
    assert r.status_code == 200
    assert "af_session=" in r.headers.get("set-cookie", "")
    assert client.get("/calendar/appointments").status_code == 401, "the cookie is gone"


def test_sign_out_is_allowed_without_a_session():
    client = TestClient(app)
    client.cookies.clear()
    assert client.post("/auth/logout", json={}).status_code == 200


def test_dashboard_has_a_sign_out_button():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="sign-out-btn"' in html and 'onclick="Auth.logout()"' in html
    assert "Sign out" in html


def test_logout_always_tells_the_server():
    js = (STATIC / "js" / "auth.js").read_text(encoding="utf-8")
    body = js[js.index("async logout()"):js.index("async me()")]
    assert 'fetch("/auth/logout"' in body
    assert "if (refresh) {" not in body, "the server call must not depend on a refresh token"


@pytest.mark.parametrize("question, topic_start", [
    ("how do I log out", "How do I change my password or sign out"),
    ("where is the sign out button", "How do I change my password or sign out"),
    ("what does unconfirmed mean in the calendar", "How do I see appointments"),
])
def test_myai_knows_about_sign_out_and_booking_status(monkeypatch, question, topic_start):
    monkeypatch.setattr(dashboard_help, "ANTHROPIC_API_KEY", "")
    result = dashboard_help.answer(question)
    assert result.get("topic", "").startswith(topic_start), result
