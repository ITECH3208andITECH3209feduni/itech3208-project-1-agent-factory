#!/usr/bin/env python3
# scripts/test_reminders_list.py
# ──────────────────────────────────────────────────────────────
# Reminders list view — filter, search, status (PROJ-438).
#
# Rewritten for the published contract (PROJ-404): message / send_at /
# blocked / int ids. CRUD and validation are covered in test_contacts.py;
# this file focuses on query behaviour — sorting, paging, combined filters,
# and the two empty states.
#
# Run: python scripts/test_reminders_list.py
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
    print("Reminders list view on the PROJ-404 contract (PROJ-438)\n")

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"  SKIP  TestClient unavailable ({exc})")
        return 0

    from app.web import reminders, store
    from app.web.main import app

    tmp = Path(tempfile.mkdtemp(prefix="af-list-"))
    for name in ("contacts", "reminders", "consent_events"):
        store.set_table(name, store.JsonTable(tmp / f"{name}.json", name))

    client = TestClient(app)

    try:
        # Two contacts, so the contact filter has something to bite on.
        from app.web import contacts

        alice = contacts.create_contact({"phone_number": "0400000101", "name": "Alice"})
        bobby = contacts.create_contact({"phone_number": "0400000102", "name": "Bobby"})

        # Seeded through the store so past dates and engine-owned statuses can
        # be set — the API correctly refuses both.
        seed = [
            ("Acme renewal call", iso(days=1), alice["id"], "scheduled", None),
            ("Bravo follow-up", iso(days=5), alice["id"], "scheduled", None),
            ("Charlie onboarding", iso(days=-2), bobby["id"], "sent", iso(days=-2)),
            ("Delta stopped by consent", iso(days=3), bobby["id"], "blocked", None),
            ("Echo bounced", iso(days=-1), bobby["id"], "failed", None),
            ("Stuck scheduled item", iso(days=-3), alice["id"], "scheduled", None),
        ]
        for msg, when, cid, status, sent in seed:
            reminders.reminders_table().insert({
                "contact_id": cid, "message": msg, "send_at": when,
                "sent_at": sent, "status": status,
                "created_at": iso(seconds=-len(msg)), "updated_at": iso(),
            })
        check("seeded 6 reminders", len(reminders.list_reminders()) == 6)

        # ── Page ──────────────────────────────────────────────
        r = client.get("/reminders")
        check("GET /reminders returns 200", r.status_code == 200)
        html = r.text
        check("has exactly one filter row", html.count('class="filters"') == 1)
        for f in ('id="q"', 'id="status"', 'id="contact"', 'id="sort"'):
            check(f"filter row has {f}", f in html)
        check("status options match the contract",
              "blocked" in html and "cancelled" not in html)
        check("distinguishes the two empty states",
              "No reminders yet" in html and "Nothing matches these filters" in html)
        check("calls out overdue scheduled rows", "Overdue" in html)
        check("shows the contact column", "Contact</th>" in html)
        check("escapes interpolated values", "const esc" in html)
        check("no CDN dependency", "https://" not in html and "cdn." not in html)

        # ── Unfiltered ────────────────────────────────────────
        d = client.get("/api/reminders").json()
        check("returns all 6", d["total"] == 6, str(d["total"]))
        check("reports unfiltered_total", d["unfiltered_total"] == 6)
        check("default sort is soonest send_at",
              [x["send_at"] for x in d["reminders"]]
              == sorted(x["send_at"] for x in d["reminders"]))

        # ── Search over message ───────────────────────────────
        d = client.get("/api/reminders?q=acme").json()
        check("search is case-insensitive", d["total"] == 1, str(d["total"]))
        d = client.get("/api/reminders?q=CONSENT").json()
        check("search matches mid-message", d["total"] == 1, str(d["total"]))
        d = client.get("/api/reminders?q=zzznope").json()
        check("no matches returns 0", d["total"] == 0)
        check("no-match keeps unfiltered_total", d["unfiltered_total"] == 6)

        # ── Status ────────────────────────────────────────────
        d = client.get("/api/reminders?status=scheduled").json()
        check("status filter works", d["total"] == 3, str(d["total"]))
        d = client.get("/api/reminders?status=blocked,failed").json()
        check("comma-separated statuses work", d["total"] == 2, str(d["total"]))
        r = client.get("/api/reminders?status=cancelled")
        check("the removed 'cancelled' status is now a 422", r.status_code == 422)
        r = client.get("/api/reminders?status=schedulled")
        check("misspelled status is 422, not ignored", r.status_code == 422)
        check("error names the bad value", "schedulled" in str(r.json()["errors"]))

        # ── Contact filter ────────────────────────────────────
        d = client.get(f"/api/reminders?contact_id={alice['id']}").json()
        check("contact filter works", d["total"] == 3, str(d["total"]))
        check("contact filter returns only that contact's",
              all(x["contact_id"] == alice["id"] for x in d["reminders"]))

        # ── Combined ──────────────────────────────────────────
        d = client.get(f"/api/reminders?contact_id={bobby['id']}&status=sent").json()
        check("filters combine (AND)", d["total"] == 1, str(d["total"]))
        d = client.get("/api/reminders?q=acme&status=sent").json()
        check("contradictory filters return 0", d["total"] == 0)

        # ── Sort ──────────────────────────────────────────────
        d = client.get("/api/reminders?sort=send_at_desc").json()
        check("send_at_desc reverses",
              [x["send_at"] for x in d["reminders"]]
              == sorted((x["send_at"] for x in d["reminders"]), reverse=True))
        d = client.get("/api/reminders?sort=message_asc").json()
        msgs = [x["message"].lower() for x in d["reminders"]]
        check("message_asc sorts alphabetically", msgs == sorted(msgs), str(msgs[:2]))
        r = client.get("/api/reminders?sort=sideways")
        check("unknown sort is 422", r.status_code == 422)

        # ── Paging ────────────────────────────────────────────
        d = client.get("/api/reminders?limit=2").json()
        check("limit caps the page", d["count"] == 2)
        check("total ignores the limit", d["total"] == 6, str(d["total"]))
        page2 = client.get("/api/reminders?limit=2&offset=2").json()
        check("offset pages forward", page2["count"] == 2)
        check("offset returns different rows",
              page2["reminders"][0]["id"] != d["reminders"][0]["id"])
        for bad in ("limit=0", "limit=99999", "offset=-1"):
            check(f"{bad} is rejected", client.get(f"/api/reminders?{bad}").status_code == 422)

        # ── Dashboard helpers ─────────────────────────────────
        up = reminders.next_upcoming(5)
        check("next_upcoming excludes the overdue one", len(up) == 2, str([r["message"] for r in up]))
        check("next_upcoming is soonest first", up[0]["message"].startswith("Acme"))
        hist = reminders.recent_history(5)
        check("recent_history covers sent/blocked/failed", len(hist) == 3, str(len(hist)))
        check("recent_history excludes scheduled",
              all(r["status"] in ("sent", "blocked", "failed") for r in hist))
        check("upcoming_count agrees", reminders.upcoming_count() == 2)
        check("sent_count counts only sent", reminders.sent_count() == 1)
        check("blocked_count counts only blocked", reminders.blocked_count() == 1)

        # ── query() is pure ───────────────────────────────────
        items = reminders.list_reminders()
        before = [r["id"] for r in items]
        page, total = reminders.query(items, limit=3)
        check("query returns (page, total)", len(page) == 3 and total == 6)
        reminders.query(items, sort="message_asc")
        check("query does not mutate its input", [r["id"] for r in items] == before)

        # ── Corrupt store ─────────────────────────────────────
        (tmp / "reminders.json").write_text("{ broken", encoding="utf-8")
        store.set_table("reminders", store.JsonTable(tmp / "reminders.json", "reminders"))
        check("corrupt store is a 500, not an empty list",
              client.get("/api/reminders?status=scheduled").status_code == 500)
    finally:
        for name in ("contacts", "reminders", "consent_events"):
            store.set_table(name, None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
