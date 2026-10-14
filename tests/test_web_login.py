# The sign-in page posts {email, password}; organisation owners must be able to
# log in that way, and the original username login must keep working.
import pytest
from fastapi.testclient import TestClient

from app.web_ui.main import app


@pytest.fixture
def anon(tmp_path, monkeypatch):
    # Own database: other tests reassign auth.db.DB_PATH, and org_routes imported
    # the constant by value, so point both at the same fresh file.
    from auth import db as auth_db, org_routes, tenancy

    path = str(tmp_path / "auth_users.db")
    monkeypatch.setattr(auth_db, "DB_PATH", path)
    monkeypatch.setattr(org_routes, "DB_PATH", path)
    auth_db.init_db()
    tenancy.init_tenancy()
    c = TestClient(app)
    c.cookies.clear()
    return c


def _register_org(c, email, password="a-long-password-1"):
    r = c.post("/orgs/register", json={"org_name": "Test Clinic", "email": email, "password": password})
    assert r.status_code in (201, 409)


def test_org_owner_can_log_in_by_email(anon):
    _register_org(anon, "owner.login@example.com")
    r = anon.post("/auth/login", json={"email": "owner.login@example.com", "password": "a-long-password-1"})
    assert r.status_code == 200
    assert r.json()["username"] == "owner.login@example.com"
    # the cookie from that login opens a protected route
    assert anon.get("/activity").status_code == 200


def test_email_login_is_case_insensitive(anon):
    _register_org(anon, "case.test@example.com")
    r = anon.post("/auth/login", json={"email": "CASE.Test@Example.com", "password": "a-long-password-1"})
    assert r.status_code == 200


def test_wrong_password_is_401_with_a_readable_message(anon):
    _register_org(anon, "wrong.pw@example.com")
    r = anon.post("/auth/login", json={"email": "wrong.pw@example.com", "password": "not-the-password"})
    assert r.status_code == 401
    assert isinstance(r.json()["detail"], str)


def test_unknown_email_is_401(anon):
    r = anon.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert r.status_code == 401


def test_username_login_still_works(anon):
    anon.post("/auth/register", json={"username": "plain.user", "password": "a-long-password-1"})
    anon.cookies.clear()
    r = anon.post("/auth/login", json={"username": "plain.user", "password": "a-long-password-1"})
    assert r.status_code == 200


def test_missing_identifier_is_422(anon):
    r = anon.post("/auth/login", json={"password": "x"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
