#!/usr/bin/env python3
# scripts/test_dashboard.py
# ──────────────────────────────────────────────────────────────
# Checks for the dashboard shell — KPI counters and nav (PROJ-437).
# Run: python scripts/test_dashboard.py
# ──────────────────────────────────────────────────────────────

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
    print("Dashboard shell (PROJ-437)\n")

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"  SKIP  TestClient unavailable ({exc})")
        return 0

    from app.web import stats
    from app.web.main import app

    client = TestClient(app)

    # ── Routes ────────────────────────────────────────────────
    r = client.get("/dashboard")
    check("GET /dashboard returns 200", r.status_code == 200, f"got {r.status_code}")
    check("dashboard is HTML", "text/html" in r.headers.get("content-type", ""))
    html = r.text

    r = client.get("/api/stats")
    check("GET /api/stats returns 200", r.status_code == 200, f"got {r.status_code}")
    d = r.json()

    # ── Payload shape ─────────────────────────────────────────
    check("stats has a metrics array", isinstance(d.get("metrics"), list), str(d)[:120])
    check("stats names a hero metric", bool(d.get("hero")), str(d.get("hero")))
    check(
        "hero key exists among the metrics",
        any(m["key"] == d["hero"] for m in d["metrics"]),
        f"hero={d.get('hero')}",
    )
    check(
        "exactly one metric is the hero",
        sum(1 for m in d["metrics"] if m["key"] == d["hero"]) == 1,
    )
    check(
        "counts add up to the metric total",
        d["available_count"] + d["pending_count"] == len(d["metrics"]),
        f"{d['available_count']}+{d['pending_count']} vs {len(d['metrics'])}",
    )

    for m in d["metrics"]:
        for field in ("key", "label", "value", "available", "blocked_by", "note"):
            check(f"{m['key']} has {field}", field in m)
        # Stat-tile contract: label is sentence case with no trailing colon.
        check(f"{m['key']} label has no trailing colon", not m["label"].endswith(":"))

    # ── The central design property ───────────────────────────
    # A metric with no data source must NOT report 0. A zero meaning "no store
    # yet" is indistinguishable from a measured zero, and the whole point of
    # the shell is that it is honest about what is not wired up.
    pending = [m for m in d["metrics"] if not m["available"]]
    check("some metrics are pending (stores not built)", len(pending) >= 1, str(len(pending)))
    for m in pending:
        check(f"{m['key']} reports null, not 0", m["value"] is None, repr(m["value"]))
        check(f"{m['key']} names its blocker", bool(m["blocked_by"]) or bool(m["note"]), str(m))

    available = [m for m in d["metrics"] if m["available"]]
    check("some metrics are live", len(available) >= 1, str(len(available)))
    for m in available:
        check(
            f"{m['key']} has a numeric value",
            isinstance(m["value"], (int, float)),
            repr(m["value"]),
        )

    # A delta without a named period is meaningless, so it must not appear.
    for m in d["metrics"]:
        if m.get("delta") is not None:
            check(f"{m['key']} delta names a period", bool(m.get("delta_period")), str(m))

    # ── Real data cross-check ─────────────────────────────────
    from skills.manifest_loader import discover_manifests

    valid = [x for x in discover_manifests(strict=False) if not x.get("_errors")]
    skills_metric = next((m for m in d["metrics"] if m["key"] == "skills_registered"), None)
    check("skills_registered is present", skills_metric is not None)
    if skills_metric:
        check(
            "skills_registered matches the manifest count",
            skills_metric["value"] == len(valid),
            f"metric={skills_metric['value']} actual={len(valid)}",
        )

    # ── Resilience ────────────────────────────────────────────
    # A broken provider must degrade to unavailable, not take the dashboard down.
    original = stats.PROVIDERS[:]
    try:
        def boom():
            raise RuntimeError("provider exploded")

        stats.PROVIDERS.append(boom)
        collected = stats.collect()
        bad = [m for m in collected if "exploded" in (m.note or "")]
        check("a raising provider degrades to unavailable", len(bad) == 1, str(len(bad)))
        if bad:
            check("the degraded metric is marked unavailable", bad[0].available is False)
            check("the degraded metric has no value", bad[0].value is None)

        r2 = client.get("/api/stats")
        check("/api/stats still 200 with a broken provider", r2.status_code == 200)
    finally:
        stats.PROVIDERS[:] = original

    # ── Auth honesty ──────────────────────────────────────────
    # PROJ-399 wants an authenticated page; accounts are PROJ-392 and unbuilt.
    # Faking a session would be worse than none, so the flag must read false
    # and the page must say so.
    check("stats reports authenticated", "authenticated" in d)
    check("authenticated is false (PROJ-392 not landed)", d.get("authenticated") is False)
    check("dashboard renders an auth warning banner", 'id="authbanner"' in html)
    check("banner names the blocking ticket", "PROJ-392" in html)
    check(
        "banner carries an icon and text, not colour alone",
        'class="ico"' in html and "Not authenticated" in html,
    )

    # ── Form and a11y ─────────────────────────────────────────
    check("has a nav", "<nav>" in html)
    check("nav marks the current page", 'aria-current="page"' in html)
    # Contacts (PROJ-417/418/419) and the reminders list (PROJ-438) are built,
    # so the nav no longer tags anything as blocked. Assert that rather than
    # the old expectation — a nav still advertising shipped work as pending
    # would be the bug now.
    check("nav no longer tags built sections as blocked", 'class="tag">PROJ-' not in html)
    check("nav links to contacts", 'href="/contacts"' in html)
    check("nav links to the reminders list", 'href="/reminders"' in html)
    check("has a KPI row container", 'id="kpis"' in html)
    check("has exactly one hero block", html.count('class="hero"') == 1, str(html.count('class="hero"')))
    check("hero value is >=48px", "font-size: 52px" in html)

    # Proportional figures on big numbers; tabular only in the aligned table.
    # Match the declaration, not the bare token — the source comments mention
    # "tabular-nums" by name, and a substring match picks those up too.
    import re as _re

    def declares(prop_value: str) -> bool:
        return bool(_re.search(r"font-variant-numeric:\s*" + _re.escape(prop_value), html))

    check("big values use proportional figures", declares("proportional-nums"))
    check("table columns use tabular figures", declares("tabular-nums"))

    # The hero must not use tabular figures: equal-width digits make a large
    # standalone number look loose. Check the hero's own rule block.
    hero_rule = _re.search(r"\.hero \.value \{(.*?)\}", html, _re.S)
    check("hero rule found", hero_rule is not None)
    if hero_rule:
        body = hero_rule.group(1)
        check(
            "hero declares proportional, not tabular, figures",
            _re.search(r"font-variant-numeric:\s*proportional-nums", body) is not None
            and _re.search(r"font-variant-numeric:\s*tabular-nums", body) is None,
            body.strip()[:120],
        )

    # Values must be reachable without hover.
    check("has a table view of every metric", 'class="tableview"' in html)
    check("fetches metrics at runtime", '"/api/stats"' in html)
    check("escapes interpolated values", "const esc" in html)

    # Dark mode is a selected set of steps, declared for OS and manual toggle.
    check("declares dark mode via media query", "prefers-color-scheme: dark" in html)
    check("declares dark mode via data-theme", '[data-theme="dark"]' in html)
    check("dark surface is the palette's dark step", "#1a1a19" in html)

    # No CDN, same reasoning as /ui.
    check(
        "no external dependencies",
        "cdn." not in html and "https://" not in html,
    )

    # No chart was drawn, so no legend is needed — but also no fake chart.
    check("no canvas or chart library", "<canvas" not in html and "chart.js" not in html.lower())

    # ── Root and schema ───────────────────────────────────────
    root = client.get("/").json()
    check("root links to /dashboard", root.get("dashboard") == "/dashboard")
    check("root links to /api/stats", root.get("stats") == "/api/stats")
    check("root still links to /skills", root.get("skills") == "/skills")

    paths = client.get("/openapi.json").json().get("paths", {})
    check("OpenAPI documents /api/stats", "/api/stats" in paths)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
