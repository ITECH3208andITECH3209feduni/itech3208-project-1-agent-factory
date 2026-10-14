# /status is the health check used by the Docker smoke test and uptime monitoring,
# so it must answer without a login.
from fastapi.testclient import TestClient

from app.web_ui.main import app


def test_status_is_public_and_healthy():
    r = TestClient(app).get("/status")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "agent": "ready"}
