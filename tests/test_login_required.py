# Default-deny: anonymous requests are refused everywhere except the public list.
import pytest
from fastapi.testclient import TestClient

from app.web_ui.main import app


@pytest.fixture
def anon():
    c = TestClient(app)
    c.cookies.clear()
    return c


@pytest.mark.parametrize("method,path", [
    ("GET", "/activity"), ("GET", "/activity/stats"), ("GET", "/escalations"),
    ("GET", "/calendar/appointments"), ("GET", "/analytics/summary"),
    ("GET", "/delivery/history"), ("GET", "/api/user/settings"),
    ("GET", "/crm/api/contacts"), ("GET", "/crm/api/reminders"), ("GET", "/crm/api/stats"),
    ("POST", "/crm/api/contacts"), ("POST", "/delivery/send"),
    ("POST", "/analytics/seed-demo-data"), ("POST", "/amazon"), ("POST", "/receptionist"),
])
def test_anonymous_requests_are_refused(anon, method, path):
    r = anon.request(method, path, json={})
    assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a login"


def test_anonymous_page_visit_redirects_to_login(anon):
    r = anon.get("/crm/contacts", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


@pytest.mark.parametrize("path", ["/status", "/status/scheduler", "/login", "/register", "/site", "/showcase"])
def test_public_paths_stay_public(anon, path):
    # /status/scheduler is 503 when no heartbeat exists; anything but 401/303 means "not login-gated"
    assert anon.get(path, follow_redirects=False).status_code not in (401, 303)


def test_logged_in_user_gets_through():
    c = TestClient(app)  # conftest gives every client a session
    assert c.get("/activity").status_code == 200
