# tests/test_org_profile.py — auth/org_routes.py's /orgs/claim, /orgs/me (PROJ-409)
#
# Closes the gap left open in PROJ-392/409: the org profile endpoints
# now run on get_current_username (agent/auth.py's working session-
# cookie login), not the unwired JWT current_user dependency, via an
# org_id column added to agent/auth.py's own users table.
import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import agent.auth as auth_module
    from auth import db as auth_db, tenancy

    monkeypatch.setattr(auth_module, "AUTH_DB", str(tmp_path / "auth.db"))
    auth_db.DB_PATH = str(tmp_path / "auth_users.db")
    auth_db.init_db()
    tenancy.init_tenancy()

    from app.web_ui.main import app

    return TestClient(app)


def _register_and_login(client, username="owner1", password="correcthorsebattery"):
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return client


def test_org_me_404s_before_claiming(client):
    _register_and_login(client)
    r = client.get("/orgs/me")
    assert r.status_code == 409
    assert "claim" in r.json()["detail"].lower()


def test_claim_creates_and_links_org(client):
    _register_and_login(client)
    r = client.post("/orgs/claim", json={
        "org_name": "Zakir Consulting", "email": "zakir@example.com",
        "password": "unused1234", "timezone": "Australia/Melbourne",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Zakir Consulting"
    assert body["timezone"] == "Australia/Melbourne"


def test_org_me_returns_the_claimed_org(client):
    _register_and_login(client)
    client.post("/orgs/claim", json={
        "org_name": "Zakir Consulting", "email": "zakir@example.com", "password": "unused1234",
    })
    r = client.get("/orgs/me")
    assert r.status_code == 200
    assert r.json()["name"] == "Zakir Consulting"


def test_org_me_patch_updates_only_supplied_fields(client):
    _register_and_login(client)
    client.post("/orgs/claim", json={
        "org_name": "Zakir Consulting", "email": "zakir@example.com", "password": "unused1234",
        "timezone": "Australia/Melbourne",
    })
    r = client.patch("/orgs/me", json={"name": "Zakir Consulting Pty Ltd"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Zakir Consulting Pty Ltd"
    assert body["timezone"] == "Australia/Melbourne"  # untouched


def test_cannot_claim_a_second_org(client):
    _register_and_login(client)
    client.post("/orgs/claim", json={
        "org_name": "First Org", "email": "a@example.com", "password": "unused1234",
    })
    r = client.post("/orgs/claim", json={
        "org_name": "Second Org", "email": "b@example.com", "password": "unused1234",
    })
    assert r.status_code == 409


def test_two_different_users_get_isolated_orgs(client):
    client1 = _register_and_login(client, username="alice")
    r1 = client1.post("/orgs/claim", json={
        "org_name": "Alice Org", "email": "alice@example.com", "password": "unused1234",
    })
    assert r1.status_code == 201

    client2 = TestClient(client.app)
    client2.cookies.clear()
    _register_and_login(client2, username="bob")
    r2 = client2.post("/orgs/claim", json={
        "org_name": "Bob Org", "email": "bob@example.com", "password": "unused1234",
    })
    assert r2.status_code == 201
    assert r2.json()["id"] != r1.json()["id"]

    # Bob's session must see Bob's org, not Alice's.
    me = client2.get("/orgs/me")
    assert me.json()["name"] == "Bob Org"


def test_org_id_persists_across_agent_auth_module(client, tmp_path):
    from agent.auth import get_user_org_id

    _register_and_login(client, username="carol")
    assert get_user_org_id("carol") is None

    r = client.post("/orgs/claim", json={
        "org_name": "Carol Org", "email": "carol@example.com", "password": "unused1234",
    })
    org_id = r.json()["id"]
    assert get_user_org_id("carol") == org_id
