#!/usr/bin/env python3
# scripts/test_reminders_list.py
# ──────────────────────────────────────────────────────────────
# Checks for the reminders list view — filter, search, status (PROJ-438).
# Run: python scripts/test_reminders_list.py
#
# Uses a temporary store seeded with known records, so the developer's own
# store/reminders.json is never touched.
# ──────────────────────────────────────────────────────────────

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

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


def iso(**kw) -> str:
    return (datetime.now().astimezone() + timedelta(**kw)).isoformat()


def main() -> int:
    print("Reminders list view (PROJ-438)\n")

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"  SKIP  TestClient unavailable ({exc})")
        return 0

    from app.web import reminders
    from app.web.main import app

    tmpdir = tempfile.mkdtemp(prefix="af-list-")
    store = reminders.JsonFileStore(Path(tmpdir) / "reminders.json")
    reminders.set_store(store)
    client = TestClient(app)

    try:
        # ── Seed ──────────────────────────────────────────────
        # Created through the store directly so past dates and engine-owned
        # statuses can be set — the API correctly refuses both.
        seed = [
            {"title": "Acme renewal call", "due_at": iso(days=1),  "channel": "telegram",
             "status": "scheduled", "notes": "Discuss pricing"},
            {"title": "Bravo follow-up",   "due_at": iso(days=5),  "channel": "email",
             "status": "scheduled", "notes": ""},
            {"title": "Charlie onboarding", "due_at": iso(days=-2), "channel": "sms",
             "status": "sent", "notes": "welcome pack"},
            {"title": "Delta cancelled thing", "due_at": iso(days=3), "channel": "email",
             "status": "cancelled", "notes": ""},
            {"title": "Echo bounced", "due_at": iso(days=-1), "channel": "sms",
             "status": "failed", "notes": "bad number"},
            {"title": "Stuck scheduled item", "due_at": iso(days=-3), "channel": "email",
             "status": "scheduled", "notes": "overdue on purpose"},
        ]
        for s in seed:
            store.create(s)
        check("seeded 6 reminders", len(store.list()) == 6, str(len(store.list())))

        # ── Page ──────────────────────────────────────────────
        r = client.get("/reminders")
        check("GET /reminders returns 200", r.status_code == 200, f"got {r.status_code}")
        html = r.text
        check("list page is HTML", "text/html" in r.headers.get("content-type", ""))

        # One filter row above the table, not per-row filters.
        check("has exactly one filter row", html.count('class="filters"') == 1)
        for f in ("id=\"q\"", "id=\"status\"", "id=\"channel\"", "id=\"sort\""):
            check(f"filter row has {f}", f in html)
        check("has a clear-filters control", 'id="clear"' in html)
        check("escapes interpolated values", "const esc" in html)
        check("no external dependencies", "https://" not in html and "cdn." not in html)
        check("links to the create form", "/reminders/new" in html)

        # Status must not be colour-only.
        check("status renders a dot and a word", 'class="dot"' in html and "STATUS_LABEL" in html)
        check("distinguishes the two empty states", "No reminders yet" in html
              and "Nothing matches these filters" in html)

        # ── Unfiltered ────────────────────────────────────────
        d = client.get("/api/reminders").json()
        check("returns all 6 unfiltered", d["total"] == 6, str(d["total"]))
        check("reports unfiltered_total", d["unfiltered_total"] == 6)
        check(
            "default sort is soonest due first",
            [x["due_at"] for x in d["reminders"]] == sorted(x["due_at"] for x in d["reminders"]),
        )

        # ── Search ────────────────────────────────────────────
        d = client.get("/api/reminders?q=acme").json()
        check("search is case-insensitive on title", d["total"] == 1, str(d["total"]))
        check("search returns the right row", d["reminders"][0]["title"].startswith("Acme"))

        d = client.get("/api/reminders?q=welcome+pack").json()
        check("search also matches notes", d["total"] == 1, str(d["total"]))

        d = client.get("/api/reminders?q=zzzznope").json()
        check("search with no matches returns 0", d["total"] == 0)
        check("no-match response still reports unfiltered_total", d["unfiltered_total"] == 6)

        # ── Status filter ─────────────────────────────────────
        d = client.get("/api/reminders?status=scheduled").json()
        check("status filter works", d["total"] == 3, str(d["total"]))
        check("status filter returns only that status",
              all(x["status"] == "scheduled" for x in d["reminders"]))

        d = client.get("/api/reminders?status=sent,failed").json()
        check("status accepts a comma-separated list", d["total"] == 2, str(d["total"]))

        # A mistyped filter must not silently return everything.
        r = client.get("/api/reminders?status=schedulled")
        check("misspelled status is 422, not ignored", r.status_code == 422, f"got {r.status_code}")
        check("error names the bad value", "schedulled" in str(r.json().get("errors", {})))

        # ── Channel filter ────────────────────────────────────
        d = client.get("/api/reminders?channel=email").json()
        check("channel filter works", d["total"] == 3, str(d["total"]))
        r = client.get("/api/reminders?channel=pigeon")
        check("unknown channel is 422", r.status_code == 422)

        # ── Combined ──────────────────────────────────────────
        d = client.get("/api/reminders?status=scheduled&channel=email").json()
        check("filters combine (AND)", d["total"] == 2, str(d["total"]))
        d = client.get("/api/reminders?q=bravo&status=scheduled").json()
        check("search combines with filters", d["total"] == 1, str(d["total"]))
        d = client.get("/api/reminders?q=bravo&status=sent").json()
        check("contradictory filters return 0", d["total"] == 0)

        # ── Sort ──────────────────────────────────────────────
        d = client.get("/api/reminders?sort=due_desc").json()
        check(
            "due_desc reverses the order",
            [x["due_at"] for x in d["reminders"]] == sorted((x["due_at"] for x in d["reminders"]), reverse=True),
        )
        d = client.get("/api/reminders?sort=title_asc").json()
        titles = [x["title"].lower() for x in d["reminders"]]
        check("title_asc sorts alphabetically", titles == sorted(titles), str(titles[:3]))
        r = client.get("/api/reminders?sort=sideways")
        check("unknown sort is 422", r.status_code == 422)

        # ── Paging ────────────────────────────────────────────
        d = client.get("/api/reminders?limit=2").json()
        check("limit caps the page", d["count"] == 2, str(d["count"]))
        check("total ignores the limit", d["total"] == 6, str(d["total"]))
        d = client.get("/api/reminders?limit=2&offset=2").json()
        check("offset pages forward", d["count"] == 2)
        first_page = client.get("/api/reminders?limit=2").json()["reminders"]
        check(
            "offset returns different rows",
            d["reminders"][0]["id"] != first_page[0]["id"],
        )
        r = client.get("/api/reminders?limit=0")
        check("limit=0 is rejected", r.status_code == 422)
        r = client.get("/api/reminders?limit=99999")
        check("absurd limit is rejected", r.status_code == 422)
        r = client.get("/api/reminders?offset=-1")
        check("negative offset is rejected", r.status_code == 422)

        # ── Dashboard panel helpers ───────────────────────────
        # "Upcoming" must exclude the deliberately overdue scheduled row —
        # a past scheduled reminder is stuck, not upcoming.
        upcoming = reminders.next_upcoming(5)
        check("next_upcoming excludes overdue", len(upcoming) == 2, str([r.title for r in upcoming]))
        check("next_upcoming is soonest first", upcoming[0].title.startswith("Acme"))
        check("next_upcoming honours the count", len(reminders.next_upcoming(1)) == 1)

        history = reminders.recent_history(5)
        check("recent_history has the 3 finished ones", len(history) == 3, str(len(history)))
        check(
            "recent_history excludes scheduled",
            all(r.status in ("sent", "failed", "cancelled") for r in history),
        )

        check("upcoming_count matches next_upcoming", reminders.upcoming_count() == 2)
        check("sent_count counts only sent", reminders.sent_count() == 1)

        # ── Dashboard wiring ──────────────────────────────────
        dash = client.get("/dashboard").text
        check("dashboard nav links to the list", 'href="/reminders"' in dash)
        # Check the nav no longer carries a *pending tag* for PROJ-438, rather
        # than that the string is absent: a ticket reference in a CSS comment
        # is fine and desirable, and matching the bare string picks it up.
        check(
            "dashboard no longer tags the list as blocked",
            '<span class="tag">PROJ-438</span>' not in dash,
        )
        check(
            "dashboard still tags the genuinely blocked sections",
            '<span class="tag">PROJ-417</span>' in dash,
        )
        check("dashboard has both panel containers",
              'id="panel-upcoming"' in dash and 'id="panel-history"' in dash)
        check("dashboard panels fetch the API", "/api/reminders?status=scheduled" in dash)

        # ── query() directly, including the pure-function contract ──
        items = store.list()
        page, total = reminders.query(items, limit=3)
        check("query returns (page, total)", len(page) == 3 and total == 6, f"{len(page)},{total}")
        before = [r.id for r in items]
        reminders.query(items, sort="title_asc")
        check("query does not mutate its input", [r.id for r in items] == before)

        # ── Corrupt store ─────────────────────────────────────
        (Path(tmpdir) / "reminders.json").write_text("{ broken", encoding="utf-8")
        reminders.set_store(reminders.JsonFileStore(Path(tmpdir) / "reminders.json"))
        r = client.get("/api/reminders?status=scheduled")
        check("corrupt store is a 500, not an empty list", r.status_code == 500, f"got {r.status_code}")
    finally:
        reminders.set_store(None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
