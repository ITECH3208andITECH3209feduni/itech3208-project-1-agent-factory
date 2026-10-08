# tests/test_auth_regression.py
# ──────────────────────────────────────────────────────────────
# PROJ-464 — end-to-end auth regression suite
#
# This suite exists to prove the surviving auth model (JWT, per
# ADR-001) still works after PROJ-463 deletes the retired API-key
# model. It drives the real FastAPI app over HTTP rather than
# calling functions directly, so it catches routing and dependency
# wiring problems that unit tests miss — the /status handler that
# went missing in an earlier edit, for example, would have been
# caught here.
#
# Every test uses a throwaway database. The suite never touches
# auth_users.db and can run repeatedly.
# ──────────────────────────────────────────────────────────────

import importlib
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """A TestClient wired to a fresh database per test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("AUTH_DB_PATH", path)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-not-a-real-key-0123456789")

    # Modules read config at import time, so drop anything already
    # imported and let the app rebuild against the temp database.
    for mod in [m for m in list(sys.modules) if m.startswith(("auth", "app.web_ui"))]:
        del sys.modules[mod]

    import app.web_ui.main as main_mod
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        yield c

    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture()
def org_a(client):
    """A registered organisation with a logged-in owner."""
    client.post("/orgs/register", json={
        "org_name": "Org A", "email": "a@example.com", "password": "passwordA123",
    })
    r = client.post("/auth/login", json={
        "email": "a@example.com", "password": "passwordA123",
    })
    tokens = r.json()
    return {
        "email": "a@example.com",
        "password": "passwordA123",
        "access": tokens["access_token"],
        "refresh": tokens["refresh_token"],
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


# ── Health check stays open ────────────────────────────────────
def test_status_requires_no_auth(client):
    """
    Monitoring has no token. This also guards the specific bug
    where /status lost its handler and inherited another route's
    auth dependency.
    """
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "agent": "ready"}


# ── Registration ───────────────────────────────────────────────
def test_register_creates_org_and_owner(client):
    r = client.post("/orgs/register", json={
        "org_name": "New Co", "email": "owner@newco.com", "password": "securepass1",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "owner"
    assert body["org"]["name"] == "New Co"


def test_duplicate_email_rejected(client):
    payload = {"org_name": "First", "email": "dup@example.com", "password": "securepass1"}
    assert client.post("/orgs/register", json=payload).status_code == 201
    payload["org_name"] = "Second"
    assert client.post("/orgs/register", json=payload).status_code == 409


def test_short_password_rejected(client):
    r = client.post("/orgs/register", json={
        "org_name": "Weak", "email": "weak@example.com", "password": "short",
    })
    assert r.status_code == 422


# ── Login ──────────────────────────────────────────────────────
def test_login_returns_token_pair(client, org_a):
    r = client.post("/auth/login", json={
        "email": org_a["email"], "password": org_a["password"],
    })
    assert r.status_code == 200
    assert r.json()["access_token"]
    assert r.json()["refresh_token"]


def test_wrong_password_rejected(client, org_a):
    r = client.post("/auth/login", json={
        "email": org_a["email"], "password": "wrongpassword",
    })
    assert r.status_code == 401


def test_unknown_email_gives_same_error_as_wrong_password(client, org_a):
    """Don't let an attacker tell registered addresses from unregistered."""
    unknown = client.post("/auth/login", json={
        "email": "nobody@example.com", "password": "whatever123",
    })
    wrong = client.post("/auth/login", json={
        "email": org_a["email"], "password": "wrongpassword",
    })
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


# ── Token validation ───────────────────────────────────────────
def test_valid_token_is_accepted(client, org_a):
    r = client.get("/auth/me", headers=org_a["headers"])
    assert r.status_code == 200
    assert r.json()["email"] == org_a["email"]


def test_missing_token_rejected(client):
    assert client.get("/auth/me").status_code == 401


def test_malformed_token_rejected(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


def test_token_signed_with_wrong_secret_rejected(client, org_a):
    """A forged token must not pass — this is what the secret protects."""
    from jose import jwt
    forged = jwt.encode(
        {"sub": "1", "type": "access", "jti": "x", "exp": 9999999999},
        "wrong-secret", algorithm="HS256",
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_refresh_token_rejected_as_access_token(client, org_a):
    """Token types are not interchangeable."""
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {org_a['refresh']}"})
    assert r.status_code == 401


def test_expired_token_rejected(client, org_a):
    from jose import jwt
    expired = jwt.encode(
        {"sub": "1", "type": "access", "jti": "x", "exp": 1000000000},
        os.environ["JWT_SECRET_KEY"], algorithm="HS256",
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


# ── Refresh and rotation ───────────────────────────────────────
def test_refresh_issues_new_pair(client, org_a):
    r = client.post("/auth/refresh", json={"refresh_token": org_a["refresh"]})
    assert r.status_code == 200
    assert r.json()["access_token"] != org_a["access"]


def test_old_refresh_token_dies_after_rotation(client, org_a):
    """A stolen refresh token is useless once the real user refreshes."""
    client.post("/auth/refresh", json={"refresh_token": org_a["refresh"]})
    second = client.post("/auth/refresh", json={"refresh_token": org_a["refresh"]})
    assert second.status_code == 401


def test_logout_revokes_refresh_token(client, org_a):
    assert client.post("/auth/logout", json={"refresh_token": org_a["refresh"]}).status_code == 204
    after = client.post("/auth/refresh", json={"refresh_token": org_a["refresh"]})
    assert after.status_code == 401


# ── Protected routes ───────────────────────────────────────────
@pytest.mark.parametrize("method,path,payload", [
    ("get",  "/history", None),
    ("get",  "/auth/me", None),
    ("get",  "/orgs/me", None),
    ("post", "/query", {"query": "test"}),
    ("post", "/literature", {"topic": "test"}),
    ("post", "/integrity", {"text": "test"}),
    ("post", "/seller", {"query": "test"}),
    ("post", "/export", {"data": {}, "format": "pdf"}),
    ("get",  "/export/download?path=x.pdf", None),
])
def test_protected_routes_reject_anonymous_callers(client, method, path, payload):
    """
    Every route that touches data or runs a skill needs a token.
    Six of these were unauthenticated before PROJ-407 — this test
    is what stops that regressing.
    """
    r = client.request(method.upper(), path, json=payload)
    assert r.status_code in (401, 403), f"{method.upper()} {path} allowed anonymous access"


# ── Org scoping ────────────────────────────────────────────────
def test_token_only_reaches_its_own_org(client, org_a):
    client.post("/orgs/register", json={
        "org_name": "Org B", "email": "b@example.com", "password": "passwordB123",
    })
    b = client.post("/auth/login", json={
        "email": "b@example.com", "password": "passwordB123",
    }).json()
    b_headers = {"Authorization": f"Bearer {b['access_token']}"}

    a_org = client.get("/orgs/me", headers=org_a["headers"]).json()
    b_org = client.get("/orgs/me", headers=b_headers).json()

    assert a_org["id"] != b_org["id"]
    assert a_org["name"] == "Org A"
    assert b_org["name"] == "Org B"


def test_member_cannot_edit_org_profile(client, org_a):
    """Only owners change the org. Role is enforced, not just identity."""
    import auth.db as db
    import auth.tenancy as tenancy
    from auth.security import hash_password

    org_id = client.get("/orgs/me", headers=org_a["headers"]).json()["id"]
    member_id = db.create_user("member@example.com", hash_password("memberpass1"))
    tenancy.assign_user_to_org(member_id, org_id, "member")

    m = client.post("/auth/login", json={
        "email": "member@example.com", "password": "memberpass1",
    }).json()
    r = client.patch("/orgs/me",
                     headers={"Authorization": f"Bearer {m['access_token']}"},
                     json={"name": "Hijacked"})
    assert r.status_code == 403


# ── Password reset ─────────────────────────────────────────────
def test_forgot_password_does_not_reveal_registration(client, org_a):
    known = client.post("/auth/forgot-password", json={"email": org_a["email"]})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json()["message"] == unknown.json()["message"]


def test_reset_token_is_single_use(client, org_a):
    from auth.db import get_user_by_email
    from auth.password_reset import create_reset_token

    user = get_user_by_email(org_a["email"])
    token = create_reset_token(user["id"])

    first = client.post("/auth/reset-password", json={
        "token": token, "new_password": "brandnewpass1",
    })
    assert first.status_code == 200

    second = client.post("/auth/reset-password", json={
        "token": token, "new_password": "anotherpass1",
    })
    assert second.status_code == 400


def test_reset_kills_existing_sessions(client, org_a):
    """A password change must log the user out everywhere."""
    from auth.db import get_user_by_email
    from auth.password_reset import create_reset_token

    user = get_user_by_email(org_a["email"])
    token = create_reset_token(user["id"])
    client.post("/auth/reset-password", json={
        "token": token, "new_password": "brandnewpass1",
    })

    # The refresh token issued before the reset must no longer work.
    r = client.post("/auth/refresh", json={"refresh_token": org_a["refresh"]})
    assert r.status_code == 401


def test_old_password_stops_working_after_reset(client, org_a):
    from auth.db import get_user_by_email
    from auth.password_reset import create_reset_token

    user = get_user_by_email(org_a["email"])
    token = create_reset_token(user["id"])
    client.post("/auth/reset-password", json={
        "token": token, "new_password": "brandnewpass1",
    })

    old = client.post("/auth/login", json={
        "email": org_a["email"], "password": org_a["password"],
    })
    new = client.post("/auth/login", json={
        "email": org_a["email"], "password": "brandnewpass1",
    })
    assert old.status_code == 401
    assert new.status_code == 200


# ── Retired model is gone (PROJ-463 guard) ─────────────────────
@pytest.mark.parametrize("path", ["/api/literature?q=test", "/api/amazon?q=test"])
def test_retired_api_endpoints_do_not_exist(client, path):
    """
    ADR-001 retired the API-key model. These paths must stay gone —
    if someone reintroduces them, this fails.
    """
    assert client.get(path).status_code == 404


def test_api_key_header_grants_nothing(client):
    """
    X-API-Key was the retired model's credential. It must not
    authenticate anything on the surviving model.
    """
    r = client.get("/auth/me", headers={"X-API-Key": "any-value"})
    assert r.status_code == 401