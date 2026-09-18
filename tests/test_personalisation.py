# tests/test_personalisation.py
# ──────────────────────────────────────────────────────────────
# Unit and integration tests for Interface Personalisation
# PROJ-401 (Epic: Interface Personalisation)
# PROJ-442 (Theme / color customization)
# PROJ-443 (Layout preferences persisted per user)
# PROJ-444 (Settings persistence + reset to default)
# ──────────────────────────────────────────────────────────────

import pytest
from fastapi.testclient import TestClient
from app.web_ui.main import app
from app.web_ui.activity_db import DEFAULT_SETTINGS, get_user_settings, reset_user_settings


@pytest.fixture
def client():
    return TestClient(app)


def test_get_default_settings(client):
    """Verify default settings are returned if no custom configuration exists (PROJ-444)."""
    reset_user_settings("test_user_1")
    resp = client.get("/api/user/settings", headers={"X-User-Id": "test_user_1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["theme"] == "dark"
    assert data["accent_color"] == "indigo"
    assert "stats" in data["widget_order"]
    assert data["widget_visibility"]["stats"] is True


def test_update_and_persist_settings(client):
    """Verify theme, accent color, and widget order persist per user (PROJ-442, PROJ-443, PROJ-444)."""
    user_id = "user_persisted_test"
    payload = {
        "theme": "light",
        "accent_color": "emerald",
        "widget_order": ["delivery", "stats", "analytics", "activity", "escalations", "calendar"],
        "widget_visibility": {"stats": True, "analytics": True, "activity": False, "delivery": True, "escalations": True, "calendar": True},
    }
    resp = client.post("/api/user/settings", json=payload, headers={"X-User-Id": user_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    # Fetch to verify persistence
    get_resp = client.get("/api/user/settings", headers={"X-User-Id": user_id})
    assert get_resp.status_code == 200
    saved = get_resp.json()
    assert saved["theme"] == "light"
    assert saved["accent_color"] == "emerald"
    assert saved["widget_order"][0] == "delivery"
    assert saved["widget_visibility"]["activity"] is False


def test_reset_settings_to_default(client):
    """Verify reset endpoint restores factory defaults (PROJ-444)."""
    user_id = "user_reset_test"
    # First set non-default values
    client.post(
        "/api/user/settings",
        json={"theme": "contrast", "accent_color": "rose"},
        headers={"X-User-Id": user_id},
    )

    # Now reset
    reset_resp = client.post("/api/user/settings/reset", headers={"X-User-Id": user_id})
    assert reset_resp.status_code == 200
    res = reset_resp.json()
    assert res["status"] == "reset"
    assert res["settings"]["theme"] == "dark"
    assert res["settings"]["accent_color"] == "indigo"
