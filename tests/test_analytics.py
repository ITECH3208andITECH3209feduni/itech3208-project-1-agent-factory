# tests/test_analytics.py
# ──────────────────────────────────────────────────────────────
# Unit and integration tests for Analytics Aggregation & Reporting
# PROJ-398 (Epic: Analytics)
# PROJ-435 (Analytics aggregation: delivery rate, response rate)
# PROJ-436 (Analytics charts endpoints)
# ──────────────────────────────────────────────────────────────

import pytest
from fastapi.testclient import TestClient
from app.web_ui.main import app
from app.web_ui.activity_db import log_activity, log_delivery_event, update_delivery_status


@pytest.fixture
def client():
    return TestClient(app)


def test_analytics_aggregation_summary(client):
    """Verify GET /analytics/summary computes delivery rate and metrics (PROJ-435)."""
    # Seed known records
    log_delivery_event("ANALYTICS-S1", "+614111", "sms", "appointment", "delivered")
    log_delivery_event("ANALYTICS-S2", "+614222", "sms", "appointment", "delivered")
    log_delivery_event("ANALYTICS-S3", "test@feduni.au", "email", "alert", "failed")
    update_delivery_status("ANALYTICS-S3", "failed", "550", "Mailbox full")

    # Inbound response
    log_activity(channel="sms", caller="+614111", intent="confirm", summary="Yes confirming")

    resp = client.get("/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert "summary" in data
    summary = data["summary"]
    assert "delivery_rate_pct" in summary
    assert "response_rate_pct" in summary
    assert "total_sent" in summary
    assert summary["total_sent"] >= 3
    assert summary["delivered"] >= 2
    assert summary["failed"] >= 1


def test_analytics_channels_breakdown(client):
    """Verify GET /analytics/channels groups metrics by SMS, Email, Voice (PROJ-435)."""
    resp = client.get("/analytics/channels")
    assert resp.status_code == 200
    channels = resp.json().get("channels", {})
    assert "sms" in channels
    assert "email" in channels
    assert "voice" in channels
    assert "total" in channels["sms"]
    assert "delivered" in channels["sms"]


def test_analytics_trends_for_charts(client):
    """Verify GET /analytics/trends returns daily time-series data for charts (PROJ-436)."""
    resp = client.get("/analytics/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert "daily_trends" in data
    assert isinstance(data["daily_trends"], list)


def test_analytics_seed_demo_data(client):
    """Verify POST /analytics/seed-demo-data populates sample data (PROJ-435, PROJ-436)."""
    resp = client.post("/analytics/seed-demo-data?count=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["seeded_records"] == 10
    assert "summary" in data["analytics"]
