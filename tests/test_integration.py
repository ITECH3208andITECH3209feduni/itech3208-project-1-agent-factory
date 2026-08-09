# tests/test_integration.py — live endpoint tests (PROJ-359-363)
# ──────────────────────────────────────────────────────────────
# Unlike the rest of tests/ (which import individual functions), these
# tests spin up the real FastAPI app via TestClient and hit it over
# HTTP-shaped requests — covering routing, auth dependencies, request
# validation, and response shapes end-to-end for every new endpoint
# added this sprint: auth, KB management, calendar .ics, receptionist.
#
# Honest scope note: TestClient calls the app in-process (ASGI
# transport), not over a real socket against a running `uvicorn`
# process. That's the standard, correct way to integration-test a
# FastAPI app without needing a live deployed server for CI — but it's
# worth being precise that "integration test" here means "through the
# real app + real routing + real dependencies", not "against a
# deployed instance". A true live-server smoke test is a different,
# smaller thing that could be added to the CI/CD deploy pipeline
# later (see PROJ-374-378 notes on the still-missing deployment
# smoke-test stage).
# ──────────────────────────────────────────────────────────────

import pytest
from fastapi.testclient import TestClient

from app.web_ui.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """A TestClient that's already registered + logged in as a unique
    test user, with the session cookie carried across requests."""
    import uuid

    username = f"itest_{uuid.uuid4().hex[:10]}"
    resp = client.post(
        "/auth/register", json={"username": username, "password": "correct-horse-battery"}
    )
    assert resp.status_code == 200, resp.text
    return client, username


# ── Auth ─────────────────────────────────────────────────────────


def test_register_then_me_roundtrip(client):
    import uuid

    username = f"itest_{uuid.uuid4().hex[:10]}"
    resp = client.post(
        "/auth/register", json={"username": username, "password": "correct-horse-battery"}
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == username

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == username


def test_me_without_session_is_401(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


# ── KB management (PROJ-279-283) ────────────────────────────────


def test_kb_upload_list_search_delete_full_cycle(auth_client):
    client, _username = auth_client

    upload = client.post(
        "/kb/upload",
        files={"file": ("integration_notes.txt", b"Integration testing covers the full request/response cycle.", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    doc_id = upload.json()["document"]["id"]
    assert upload.json()["document"]["filename"] == "integration_notes.txt"

    listing = client.get("/kb/list")
    assert listing.status_code == 200
    assert any(d["id"] == doc_id for d in listing.json()["documents"])

    search = client.get("/kb/search", params={"q": "request response cycle"})
    assert search.status_code == 200
    assert any(r["id"] == doc_id for r in search.json()["results"])

    delete = client.delete(f"/kb/{doc_id}")
    assert delete.status_code == 200
    assert delete.json()["ok"] is True

    listing_after = client.get("/kb/list")
    assert not any(d["id"] == doc_id for d in listing_after.json()["documents"])


def test_kb_upload_requires_login(client):
    resp = client.post(
        "/kb/upload",
        files={"file": ("x.txt", b"content", "text/plain")},
    )
    assert resp.status_code == 401


def test_kb_upload_rejects_bad_extension(auth_client):
    client, _username = auth_client
    resp = client.post(
        "/kb/upload",
        files={"file": ("image.png", b"\x89PNG", "image/png")},
    )
    assert resp.status_code == 400


def test_kb_documents_are_isolated_between_users(client):
    import uuid

    user_a = f"itest_{uuid.uuid4().hex[:10]}"
    user_b = f"itest_{uuid.uuid4().hex[:10]}"

    client.post("/auth/register", json={"username": user_a, "password": "correct-horse-battery"})
    upload = client.post(
        "/kb/upload",
        files={"file": ("a_only.txt", b"Only user A should see this.", "text/plain")},
    )
    doc_id = upload.json()["document"]["id"]

    client.post("/auth/logout")
    client.post("/auth/register", json={"username": user_b, "password": "correct-horse-battery"})
    listing_b = client.get("/kb/list")
    assert not any(d["id"] == doc_id for d in listing_b.json()["documents"])

    delete_attempt = client.delete(f"/kb/{doc_id}")
    assert delete_attempt.status_code == 404


# ── Calendar .ics fallback (PROJ-294-298) ───────────────────────


def test_calendar_ics_download_requires_login(client):
    resp = client.get(
        "/calendar/ics",
        params={"summary": "Test", "start": "2026-08-10T14:00:00", "end": "2026-08-10T14:30:00"},
    )
    assert resp.status_code == 401


def test_calendar_ics_download_returns_valid_file(auth_client):
    client, _username = auth_client
    resp = client.get(
        "/calendar/ics",
        params={
            "summary": "Integration Test Event",
            "start": "2026-08-10T14:00:00",
            "end": "2026-08-10T14:30:00",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "attachment" in resp.headers["content-disposition"]
    body = resp.content.decode("utf-8")
    assert "BEGIN:VCALENDAR" in body
    assert "SUMMARY:Integration Test Event" in body


def test_calendar_ics_rejects_invalid_datetime(auth_client):
    client, _username = auth_client
    resp = client.get(
        "/calendar/ics",
        params={"summary": "Bad", "start": "not-a-date", "end": "also-not-a-date"},
    )
    assert resp.status_code == 400


# ── AI Receptionist (PROJ-209-218) ──────────────────────────────


def test_receptionist_requires_login(client):
    resp = client.post("/receptionist", json={"message": "hello"})
    assert resp.status_code == 401


def test_receptionist_faq_hit_via_http(auth_client):
    client, _username = auth_client
    resp = client.post("/receptionist", json={"message": "what are your hours?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "faq"
    assert "answer" in data
