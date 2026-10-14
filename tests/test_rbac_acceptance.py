import pytest
from fastapi.testclient import TestClient

from auth import api_keys, db, tenancy


@pytest.fixture
def client(tmp_path, monkeypatch):
    import agent.auth as session_auth
    from auth import org_routes

    monkeypatch.setattr(
        session_auth,
        "AUTH_DB",
        str(tmp_path / "sessions.db"),
    )
    monkeypatch.setattr(
        db,
        "DB_PATH",
        str(tmp_path / "organisations.db"),
    )
    monkeypatch.setattr(
        org_routes,
        "DB_PATH",
        str(tmp_path / "organisations.db"),
    )

    db.init_db()
    tenancy.init_tenancy()

    from app.web_ui.main import app

    return TestClient(app)


def test_email_owner_can_create_list_and_revoke_api_key(client):
    email = "api-admin@example.com"
    password = "correcthorsebattery"

    registration = client.post(
        "/orgs/register",
        json={
            "org_name": "API Test Organisation",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 201, registration.text

    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login.status_code == 200, login.text

    created = client.post(
        "/orgs/api-keys",
        json={"label": "Integration key"},
    )
    assert created.status_code == 201, created.text

    result = created.json()
    assert result["key"].startswith("afk_")

    listed = client.get("/orgs/api-keys")
    assert listed.status_code == 200, listed.text
    assert listed.json()["keys"][0]["id"] == result["id"]
    assert "key" not in listed.json()["keys"][0]

    revoked = client.delete(
        f"/orgs/api-keys/{result['id']}"
    )
    assert revoked.status_code == 200, revoked.text

    identity = api_keys.authenticate_api_key(result["key"])
    assert identity is None


def test_staff_cannot_change_settings_or_send_messages(client):
    registration = client.post(
        "/auth/register",
        json={
            "username": "staffuser",
            "password": "correcthorsebattery",
        },
    )
    assert registration.status_code == 200, registration.text

    claimed = client.post(
        "/orgs/claim",
        json={
            "org_name": "Staff Test Organisation",
            "email": "staff-contact@example.com",
            "password": "unused1234",
        },
    )
    assert claimed.status_code == 201, claimed.text

    settings = client.post(
        "/api/user/settings",
        json={"theme": "dark"},
    )
    assert settings.status_code == 403, settings.text

    send = client.post(
        "/delivery/send",
        json={
            "recipient": "+15551234567",
            "channel": "sms",
            "message": "Permission test",
        },
    )
    assert send.status_code == 403, send.text


def test_unauthenticated_user_cannot_manage_api_keys(client):
    client.cookies.clear()

    response = client.post(
        "/orgs/api-keys",
        json={"label": "Unauthorised key"},
    )
    assert response.status_code == 401, response.text
def test_valid_api_key_can_reach_crm_without_session_cookie(client):
    registration = client.post(
        "/orgs/register",
        json={
            "org_name": "CRM API Organisation",
            "email": "crm-api@example.com",
            "password": "correcthorsebattery",
        },
    )
    assert registration.status_code == 201, registration.text

    login = client.post(
        "/auth/login",
        json={
            "email": "crm-api@example.com",
            "password": "correcthorsebattery",
        },
    )
    assert login.status_code == 200, login.text

    created = client.post(
        "/orgs/api-keys",
        json={"label": "CRM test key"},
    )
    assert created.status_code == 201, created.text

    raw_key = created.json()["key"]
    client.cookies.clear()

    response = client.get(
        "/crm/api/contacts",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 200, response.text