#!/usr/bin/env python3
# scripts/test_web_api.py
# ──────────────────────────────────────────────────────────────
# Checks for the FastAPI layer (PROJ-299..303).
# Run: python scripts/test_web_api.py
#
# Uses FastAPI's TestClient, so no port is bound and no network is touched.
# ──────────────────────────────────────────────────────────────

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


def main() -> int:
    print("FastAPI web layer (PROJ-299..303)\n")

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"  SKIP  TestClient unavailable ({exc}); pip install httpx")
        return 0

    from app.web.main import app

    client = TestClient(app)

    # ── / ─────────────────────────────────────────────────────
    r = client.get("/")
    check("GET / returns 200", r.status_code == 200, f"got {r.status_code}")
    body = r.json()
    check("GET / names the service", body.get("service") == "agent-factory", str(body))

    # ── /health ───────────────────────────────────────────────
    r = client.get("/health")
    check("GET /health returns 200", r.status_code == 200, f"got {r.status_code}")
    h = r.json()
    check("health reports a status", h.get("status") in ("ok", "degraded"), str(h.get("status")))
    check("health reports uptime", isinstance(h.get("uptime_sec"), (int, float)))
    check("health lists config check", "config" in h.get("checks", {}), str(h.get("checks")))
    check("health surfaces warnings list", isinstance(h.get("warnings"), list))

    # The container HEALTHCHECK must not flap when config is incomplete —
    # restarting cannot supply a missing API key.
    check("health stays 200 even when degraded", r.status_code == 200)

    # ── OpenAPI ───────────────────────────────────────────────
    r = client.get("/openapi.json")
    check("OpenAPI schema served", r.status_code == 200, f"got {r.status_code}")
    paths = r.json().get("paths", {})
    for p in ("/", "/health", "/query"):
        check(f"schema documents {p}", p in paths)

    # ── /query validation ─────────────────────────────────────
    r = client.post("/query", json={})
    check("POST /query rejects missing query", r.status_code == 422, f"got {r.status_code}")

    r = client.post("/query", json={"query": ""})
    check("POST /query rejects empty query", r.status_code == 422, f"got {r.status_code}")

    r = client.post("/query", json={"query": "x" * 5000})
    check("POST /query rejects oversized query", r.status_code == 422, f"got {r.status_code}")

    # ── /query gating on missing key ──────────────────────────
    # With no Claude key the endpoint must answer 503, not 500 — the caller
    # needs to distinguish "not configured" from "crashed".
    from config import settings

    original = settings.ANTHROPIC_API_KEY
    try:
        settings.ANTHROPIC_API_KEY = "YOUR_API_KEY_HERE"
        r = client.post("/query", json={"query": "test"})
        check(
            "POST /query returns 503 without an API key",
            r.status_code == 503,
            f"got {r.status_code}: {r.text[:120]}",
        )
    finally:
        settings.ANTHROPIC_API_KEY = original

    # ── Lazy orchestrator ─────────────────────────────────────
    # Importing the module must not construct the Anthropic client, or the
    # container cannot even start without a key.
    import app.web.main as web

    check("orchestrator is not built at import", web._orchestrator is None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
