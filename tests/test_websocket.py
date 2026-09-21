# tests/test_websocket.py
# ──────────────────────────────────────────────────────────────
# Tests for PROJ-469 — WebSocket live dashboard updates.
# Verifies connection, initial_state snapshot, event broadcast,
# keepalive ping-pong, and graceful disconnect handling.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI


# ── Helpers ────────────────────────────────────────────────────

def _make_test_app():
    """Minimal FastAPI app that mounts only the ws_router."""
    from app.web_ui.ws_routes import router as ws_router
    app = FastAPI()
    app.include_router(ws_router)
    return app


# ── DashboardConnectionManager unit tests ─────────────────────

class TestDashboardConnectionManager:
    """Unit tests for the connection manager (no live server needed)."""

    def setup_method(self):
        from app.web_ui.ws_routes import DashboardConnectionManager
        self.mgr = DashboardConnectionManager()

    def test_initial_state_empty(self):
        assert self.mgr.active_connections == []

    @pytest.mark.asyncio
    async def test_connect_adds_connection(self):
        ws = AsyncMock()
        await self.mgr.connect(ws)
        assert ws in self.mgr.active_connections
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        ws = AsyncMock()
        await self.mgr.connect(ws)
        self.mgr.disconnect(ws)
        assert ws not in self.mgr.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_unknown_is_safe(self):
        ws = AsyncMock()
        # Disconnecting a connection that was never added must not raise
        self.mgr.disconnect(ws)

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_connections(self):
        ws1, ws2 = AsyncMock(), AsyncMock()
        with patch("app.web_ui.ws_routes.get_stats_today", return_value={}), \
             patch("app.web_ui.ws_routes.get_delivery_analytics", return_value={"summary": {}}):
            await self.mgr.connect(ws1)
            await self.mgr.connect(ws2)
        # Reset mock call counts so only the broadcast call is measured
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()
        await self.mgr.broadcast("test_event", {"key": "val"})
        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_awaited_once()

        payload = ws1.send_json.call_args[0][0]
        assert payload["type"] == "test_event"
        assert payload["data"]["key"] == "val"
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_broadcast_skips_dead_connections(self):
        """A send error on one client must not crash the whole broadcast."""
        good = AsyncMock()
        bad  = AsyncMock()

        with patch("app.web_ui.ws_routes.get_stats_today", return_value={}), \
             patch("app.web_ui.ws_routes.get_delivery_analytics", return_value={"summary": {}}):
            await self.mgr.connect(good)
            await self.mgr.connect(bad)
        good.send_json.reset_mock()
        bad.send_json.reset_mock()
        bad.send_json.side_effect = RuntimeError("connection gone")
        # Should not raise
        await self.mgr.broadcast("event", {})
        good.send_json.assert_awaited_once()
        # bad is removed after send failure
        assert bad not in self.mgr.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_noop_when_no_clients(self):
        """Broadcast with zero connections must be a silent no-op."""
        # Should not raise
        await self.mgr.broadcast("event", {"x": 1})

    @pytest.mark.asyncio
    async def test_connect_sends_initial_state(self):
        ws = AsyncMock()
        with patch(
            "app.web_ui.ws_routes.get_stats_today",
            return_value={"calls": 3, "sms": 5},
        ), patch(
            "app.web_ui.ws_routes.get_delivery_analytics",
            return_value={"summary": {"sent": 2}},
        ):
            await self.mgr.connect(ws)
        ws.send_json.assert_awaited_once()
        snapshot = ws.send_json.call_args[0][0]
        assert snapshot["type"] == "initial_state"
        assert snapshot["stats"]["calls"] == 3


# ── broadcast_dashboard_event helper ─────────────────────────

def test_broadcast_dashboard_event_sync_no_loop():
    """broadcast_dashboard_event called outside an event loop must not raise."""
    from app.web_ui.ws_routes import broadcast_dashboard_event
    # No active loop: asyncio.run() path
    broadcast_dashboard_event("test", {"a": 1})


@pytest.mark.asyncio
async def test_broadcast_dashboard_event_inside_loop():
    """broadcast_dashboard_event called inside a running loop schedules a task."""
    from app.web_ui.ws_routes import broadcast_dashboard_event, manager
    manager.active_connections.clear()
    # Should not raise
    broadcast_dashboard_event("test", {"b": 2})


# ── REST endpoint /ws/status ──────────────────────────────────

def test_ws_status_endpoint():
    """/ws/status returns online status and correct channel name."""
    app = _make_test_app()
    client = TestClient(app)
    resp = client.get("/ws/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "online"
    assert data["channel"] == "/ws/dashboard"
    assert isinstance(data["active_clients"], int)


# ── WebSocket endpoint /ws/dashboard ────────────────────────

def test_ws_dashboard_accepts_connection():
    """/ws/dashboard accepts a WebSocket connection."""
    app = _make_test_app()
    with TestClient(app) as client:
        with patch("app.web_ui.ws_routes.get_stats_today", return_value={}), \
             patch("app.web_ui.ws_routes.get_delivery_analytics", return_value={"summary": {}}):
            with client.websocket_connect("/ws/dashboard") as ws:
                # Should receive initial_state immediately
                data = ws.receive_json()
                assert data["type"] == "initial_state"


def test_ws_dashboard_ping_pong():
    """/ws/dashboard responds to a 'ping' with 'pong'."""
    app = _make_test_app()
    with TestClient(app) as client:
        with patch("app.web_ui.ws_routes.get_stats_today", return_value={}), \
             patch("app.web_ui.ws_routes.get_delivery_analytics", return_value={"summary": {}}):
            with client.websocket_connect("/ws/dashboard") as ws:
                ws.receive_json()  # initial_state
                ws.send_text("ping")
                pong = ws.receive_text()
                assert pong == "pong"


def test_ws_dashboard_refresh_returns_stats():
    """/ws/dashboard returns a stats_update on 'refresh'."""
    app = _make_test_app()
    with TestClient(app) as client:
        with patch("app.web_ui.ws_routes.get_stats_today", return_value={"calls": 7}), \
             patch("app.web_ui.ws_routes.get_delivery_analytics", return_value={"summary": {"sent": 4}}):
            with client.websocket_connect("/ws/dashboard") as ws:
                ws.receive_json()  # initial_state
                ws.send_text("refresh")
                update = ws.receive_json()
                assert update["type"] == "stats_update"
                assert update["data"]["stats"]["calls"] == 7


def test_ws_active_clients_count():
    """Active client count in /ws/status reflects connected sockets."""
    from app.web_ui.ws_routes import manager
    manager.active_connections.clear()
    app = _make_test_app()
    with TestClient(app) as client:
        with patch("app.web_ui.ws_routes.get_stats_today", return_value={}), \
             patch("app.web_ui.ws_routes.get_delivery_analytics", return_value={"summary": {}}):
            with client.websocket_connect("/ws/dashboard"):
                resp = client.get("/ws/status")
                assert resp.json()["active_clients"] >= 1
