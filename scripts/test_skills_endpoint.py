#!/usr/bin/env python3
# scripts/test_skills_endpoint.py
# ──────────────────────────────────────────────────────────────
# Checks for the skills registry endpoint and web UI (PROJ-334..338).
# Run: python scripts/test_skills_endpoint.py
# ──────────────────────────────────────────────────────────────

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


def main() -> int:
    print("Skills registry endpoint (PROJ-334..338)\n")

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"  SKIP  TestClient unavailable ({exc})")
        return 0

    from app.web.main import app
    from skills.manifest_loader import MANIFEST_DIR

    client = TestClient(app)

    # ── GET /skills ───────────────────────────────────────────
    r = client.get("/skills")
    check("GET /skills returns 200", r.status_code == 200, f"got {r.status_code}")
    body = r.json()

    check("response is a JSON object with a skills array",
          isinstance(body.get("skills"), list), str(body)[:120])
    check("count matches the array length", body.get("count") == len(body.get("skills", [])))
    check("both skills are discovered", body.get("count") == 2, str(body.get("count")))

    names = sorted(s["name"] for s in body["skills"])
    check("discovers amazon and literature", names == ["amazon", "literature"], str(names))

    # Fields the ticket requires each manifest to carry.
    for s in body["skills"]:
        for field in ("name", "version", "description", "tools", "author"):
            check(f"{s['name']} exposes {field}", field in s)

    # ── Internals must not leak ───────────────────────────────
    for s in body["skills"]:
        internal = [k for k in s if k.startswith("_")]
        check(f"{s['name']} hides internal keys", not internal, str(internal))

    # ── Secret values must never be published ─────────────────
    # The manifest names env vars including API keys. Publishing whether one is
    # set is fine; publishing the value would be a live credential leak.
    raw = json.dumps(body)
    from config import settings

    actual_key = settings.ANTHROPIC_API_KEY or ""
    if actual_key and actual_key != "YOUR_API_KEY_HERE":
        check("no live API key value in the response", actual_key not in raw)
    for s in body["skills"]:
        for cfg in s.get("configuration", []) or []:
            check(f"{s['name']}.{cfg['name']} reports configured as a bool",
                  isinstance(cfg.get("configured"), bool), str(cfg))
            check(f"{s['name']}.{cfg['name']} carries no value field", "value" not in cfg)

    # ── include_tools ─────────────────────────────────────────
    r = client.get("/skills?include_tools=false")
    check("include_tools=false omits tools",
          all("tools" not in s for s in r.json()["skills"]))

    # ── GET /skills/{name} ────────────────────────────────────
    r = client.get("/skills/literature")
    check("GET /skills/literature returns 200", r.status_code == 200, f"got {r.status_code}")
    check("returns the right manifest", r.json().get("name") == "literature")

    r = client.get("/skills/nonexistent")
    check("unknown skill 404s", r.status_code == 404, f"got {r.status_code}")

    # ── GET /skills/{name}/tools ──────────────────────────────
    r = client.get("/skills/amazon/tools")
    check("GET /skills/amazon/tools returns 200", r.status_code == 200)
    d = r.json()
    check("returns 4 amazon tools", d.get("count") == 4, str(d.get("count")))
    check("each tool has a JSON Schema",
          all("inputSchema" in t for t in d.get("tools", [])))

    r = client.get("/skills/nonexistent/tools")
    check("unknown skill tools 404s", r.status_code == 404, f"got {r.status_code}")

    # ── Resilience to a malformed manifest ────────────────────
    # A broken file must not take the registry offline.
    bad = MANIFEST_DIR / "_tmp_broken.skill.json"
    try:
        bad.write_text("{ this is not json", encoding="utf-8")
        r = client.get("/skills")
        check("still 200 with a malformed manifest present", r.status_code == 200,
              f"got {r.status_code}")
        b = r.json()
        check("valid skills still returned", b.get("count") == 2, str(b.get("count")))
        check("malformed manifest is reported, not hidden",
              bool(b.get("errors")), str(b)[:160])
    finally:
        bad.unlink(missing_ok=True)

    # ── Web UI ────────────────────────────────────────────────
    r = client.get("/ui")
    check("GET /ui returns 200", r.status_code == 200, f"got {r.status_code}")
    html = r.text
    check("UI is HTML", "text/html" in r.headers.get("content-type", ""))
    check("UI has a skills sidebar", 'id="skills"' in html)
    check("UI fetches the registry at runtime", 'fetch("/skills")' in html)
    check("UI posts to /query", '"/query"' in html)
    check("UI escapes interpolated values", "const esc" in html)
    # No CDN: the deployment target is a home connection, and a UI that breaks
    # when a CDN is unreachable is worse than a plain one that always works.
    check("UI has no external dependencies",
          "http://" not in html.replace("http://127.0.0.1", "") and "cdn." not in html)

    # ── Root advertises the new routes ────────────────────────
    r = client.get("/")
    check("root links to /skills", r.json().get("skills") == "/skills")
    check("root links to /ui", r.json().get("ui") == "/ui")

    # ── OpenAPI ───────────────────────────────────────────────
    paths = client.get("/openapi.json").json().get("paths", {})
    for p in ("/skills", "/skills/{name}", "/skills/{name}/tools"):
        check(f"OpenAPI documents {p}", p in paths)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
