# PROJ-468: the scheduler liveness check used by uptime monitoring.
import os
import time

from fastapi.testclient import TestClient

from agent.reminders import heartbeat
from app.web_ui.main import app


def test_missing_heartbeat_is_503(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "HEARTBEAT_PATH", str(tmp_path / "hb"))
    r = TestClient(app).get("/status/scheduler")
    assert r.status_code == 503
    assert r.json()["detail"]["status"] == "stale"


def test_fresh_heartbeat_is_200(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "HEARTBEAT_PATH", str(tmp_path / "hb"))
    heartbeat.beat()
    r = TestClient(app).get("/status/scheduler")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_stale_heartbeat_is_503(tmp_path, monkeypatch):
    path = str(tmp_path / "hb")
    monkeypatch.setattr(heartbeat, "HEARTBEAT_PATH", path)
    with open(path, "w") as f:
        f.write(str(time.time() - heartbeat.max_age_seconds() - 5))
    assert TestClient(app).get("/status/scheduler").status_code == 503


def test_status_stays_public(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "HEARTBEAT_PATH", str(tmp_path / "hb"))
    assert TestClient(app).get("/status").status_code == 200
