"""
app.openclaw — OpenClaw SDK Integration Package

This package wraps the openclaw-sdk and provides:
  - OpenClawWrapper : connects to the OpenClaw runtime and executes skill queries
  - route_query     : classifies an incoming query and routes it to the correct skill

Usage:
    from app.openclaw import OpenClawWrapper, route_query
"""

from app.openclaw.client import OpenClawWrapper
from app.openclaw.router import route_query

__all__ = ["OpenClawWrapper", "route_query"]
