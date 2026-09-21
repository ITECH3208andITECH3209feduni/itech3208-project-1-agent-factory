# app/web_ui/ws_routes.py
# ──────────────────────────────────────────────────────────────
# WebSocket Live Dashboard Updates API
# PROJ-453 (Real-Time Dashboard & Receptionist Enhancements)
# PROJ-469 (WebSocket live dashboard updates, replacing 30s polling)
# ──────────────────────────────────────────────────────────────

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.web_ui.activity_db import get_delivery_analytics, get_stats_today

log = logging.getLogger("agent_factory.ws")

router = APIRouter(tags=["WebSocket Real-Time Dashboard"])


class DashboardConnectionManager:
    """Manages active browser WebSocket connections and broadcasts real-time events."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info("WebSocket client connected. Total active: %d", len(self.active_connections))

        # Push immediate snapshot upon connection
        try:
            stats = get_stats_today()
            delivery = get_delivery_analytics().get("summary", {})
            await websocket.send_json({
                "type": "initial_state",
                "stats": stats,
                "delivery": delivery,
                "connected_clients": len(self.active_connections),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            log.warning("Failed to send initial WebSocket state: %s", e)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            log.info("WebSocket client disconnected. Total active: %d", len(self.active_connections))

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send event to all currently connected dashboards."""
        if not self.active_connections:
            return

        payload = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(payload)
            except Exception as e:
                log.debug("Error sending to WebSocket client: %s", e)
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


# Global singleton manager
manager = DashboardConnectionManager()


def broadcast_dashboard_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Synchronous/asynchronous helper to broadcast events across active dashboards.
    Can be called safely from database hooks, Twilio webhooks, or reminder dispatchers.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast(event_type, data))
    except RuntimeError:
        # Running outside an active event loop (e.g. background thread or synchronous script)
        try:
            asyncio.run(manager.broadcast(event_type, data))
        except Exception:
            pass


@router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket connection for operator dashboard.
    Streams stats updates, new activity events, and delivery status transitions (PROJ-469).
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keepalive / ping-pong support
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
            elif msg == "refresh":
                stats = get_stats_today()
                delivery = get_delivery_analytics().get("summary", {})
                await websocket.send_json({
                    "type": "stats_update",
                    "data": {"stats": stats, "delivery": delivery},
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        log.debug("WebSocket exception: %s", exc)
        manager.disconnect(websocket)


@router.get("/ws/status")
async def websocket_status():
    """Diagnostic endpoint checking WebSocket connection manager health (PROJ-469)."""
    return {
        "status": "online",
        "active_clients": len(manager.active_connections),
        "channel": "/ws/dashboard",
    }
