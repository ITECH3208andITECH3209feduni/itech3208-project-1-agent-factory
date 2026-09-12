#!/usr/bin/env python3
# scripts/test_reminders.py
# ──────────────────────────────────────────────────────────────
# Checks for the create/edit reminder form and its backend (PROJ-439).
# Run: python scripts/test_reminders.py
#
# Uses a temporary store, so the developer's own store/reminders.json is never
# read or written.
# ──────────────────────────────────────────────────────────────

import json
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


def future(hours=24) -> str:
    return (datetime.now().astimezone() + timedelta(hours=hours)).isoformat()


def past(hours=24) -> str:
    return (datetime.now().astimezone() - timedelta(hours=hours)).isoformat()


def main() -> int:
    print("Reminder form and backend (PROJ-439)\n")

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"  SKIP  TestClient unavailable ({exc})")
        return 0

    from app.web import reminders, stats
    from app.web.main import app

    tmpdir = tempfile.mkdtemp(prefix="af-reminders-")
    store_path = Path(tmpdir) / "reminders.json"
    reminders.set_store(reminders.JsonFileStore(store_path))

    client = TestClient(app)

    try:
        # ── Pages ─────────────────────────────────────────────
        r = client.get("/reminders/new")
        check("GET /reminders/new returns 200", r.status_code == 200, f"got {r.status_code}")
        html = r.text
        check("create form is HTML", "text/html" in r.headers.get("content-type", ""))
        check("create form says 'New reminder'", "New reminder" in html)
        check("create form has an empty id", 'id="rid" value=""' in html)

        r = client.get("/reminders/abc-123/edit")
        check("GET /reminders/{id}/edit returns 200", r.status_code == 200)
        check("edit form carries the id", 'value="abc-123"' in r.text)
        check("edit form says 'Edit reminder'", "Edit reminder" in r.text)

        # No duplicate ids — getElementById silently returns only the first.
        import re

        ids = re.findall(r'\bid="([a-zA-Z_-]+)"', html)
        dupes = {i for i in ids if ids.count(i) > 1}
        check("form has no duplicate element ids", not dupes, str(dupes))

        check("form is honest about the provisional store", "PROJ-422" in html and "Provisional" in html)
        check("form has no external dependencies", "https://" not in html and "cdn." not in html)

        # ── Create: validation ────────────────────────────────
        r = client.post("/api/reminders", json={})
        check("empty create is 422", r.status_code == 422, f"got {r.status_code}")
        errs = r.json().get("errors", {})
        check("reports every missing field at once", set(errs) >= {"title", "due_at", "channel"}, str(errs))

        r = client.post("/api/reminders", json={"title": "x", "due_at": "not-a-date", "channel": "email"})
        check("unparseable date is 422", r.status_code == 422)
        check("date error is on due_at", "due_at" in r.json().get("errors", {}))

        r = client.post("/api/reminders", json={"title": "x", "due_at": past(), "channel": "email"})
        check("past due date is rejected", r.status_code == 422)
        check(
            "past-date message explains why",
            "never send" in r.json()["errors"].get("due_at", ""),
            str(r.json()["errors"]),
        )

        r = client.post("/api/reminders", json={"title": "x", "due_at": future(), "channel": "pigeon"})
        check("unknown channel is rejected", r.status_code == 422)

        r = client.post("/api/reminders", json={"title": "x" * 201, "due_at": future(), "channel": "email"})
        check("over-long title is rejected", r.status_code == 422)

        r = client.post("/api/reminders", json={
            "title": "x", "due_at": future(), "channel": "email", "notes": "n" * 2001})
        check("over-long notes are rejected", r.status_code == 422)

        # The client must not be able to claim something was sent.
        r = client.post("/api/reminders", json={
            "title": "x", "due_at": future(), "channel": "email", "status": "sent"})
        check("client cannot set status 'sent'", r.status_code == 422, f"got {r.status_code}")
        check(
            "message points at the engine",
            "PROJ-395" in r.json()["errors"].get("status", ""),
            str(r.json()["errors"]),
        )

        # A typo'd field must not look like it saved.
        r = client.post("/api/reminders", json={
            "title": "x", "due_at": future(), "channel": "email", "tittle": "oops"})
        check("unknown fields are rejected", r.status_code == 422)
        check("unknown-field error names it", "tittle" in str(r.json().get("errors", {})))

        # ── Create: success ───────────────────────────────────
        due = future(48)
        r = client.post("/api/reminders", json={
            "title": "  Follow up with Acme  ",
            "due_at": due,
            "channel": "telegram",
            "notes": "Renewal call",
            "contact_id": "c-1",
        })
        check("valid create returns 201", r.status_code == 201, f"got {r.status_code}: {r.text[:120]}")
        created = r.json()
        rid = created["id"]
        check("create assigns an id", bool(rid))
        check("title is trimmed", created["title"] == "Follow up with Acme", repr(created["title"]))
        check("status defaults to scheduled", created["status"] == "scheduled")
        check("org_id is null until PROJ-392", created["org_id"] is None)
        check("contact_id is kept as given", created["contact_id"] == "c-1")
        check("created_at and updated_at are set", bool(created["created_at"]) and bool(created["updated_at"]))

        # Naive input must be normalised to an offset-bearing timestamp.
        r = client.post("/api/reminders", json={
            "title": "naive", "due_at": "2099-01-01T09:00", "channel": "email"})
        check("naive datetime is accepted", r.status_code == 201, r.text[:120])
        stored = r.json()["due_at"]
        check("naive datetime is stored with an offset", ("+" in stored[10:]) or stored.endswith("+00:00"), stored)
        naive_id = r.json()["id"]

        # ── Read ──────────────────────────────────────────────
        r = client.get(f"/api/reminders/{rid}")
        check("GET one returns 200", r.status_code == 200)
        check("GET one returns the right record", r.json()["id"] == rid)

        r = client.get("/api/reminders/does-not-exist")
        check("GET unknown id is 404", r.status_code == 404, f"got {r.status_code}")

        r = client.get("/api/reminders")
        body = r.json()
        check("list returns both records", body["count"] == 2, str(body["count"]))
        check(
            "list is sorted soonest first",
            body["reminders"][0]["due_at"] <= body["reminders"][1]["due_at"],
        )

        # ── Update ────────────────────────────────────────────
        r = client.patch(f"/api/reminders/{rid}", json={"title": "Renamed"})
        check("partial update returns 200", r.status_code == 200, r.text[:120])
        check("update applies the change", r.json()["title"] == "Renamed")
        check("update preserves untouched fields", r.json()["channel"] == "telegram")
        check(
            "updated_at moves",
            r.json()["updated_at"] >= created["updated_at"],
            f"{r.json()['updated_at']} vs {created['updated_at']}",
        )

        r = client.patch(f"/api/reminders/{rid}", json={"title": ""})
        check("update rejects an empty title", r.status_code == 422)

        r = client.patch(f"/api/reminders/{rid}", json={"status": "cancelled"})
        check("update can cancel", r.status_code == 200 and r.json()["status"] == "cancelled")

        # Once cancelled, a past due date is history rather than an error.
        r = client.patch(f"/api/reminders/{rid}", json={"due_at": past()})
        check("past date allowed on a cancelled reminder", r.status_code == 200, r.text[:140])

        r = client.patch("/api/reminders/nope", json={"title": "x"})
        check("update unknown id is 404", r.status_code == 404)

        # ── Metrics go live off this store ────────────────────
        s = client.get("/api/stats").json()
        upcoming = next(m for m in s["metrics"] if m["key"] == "reminders_upcoming")
        sent = next(m for m in s["metrics"] if m["key"] == "reminders_sent")
        check("upcoming reminders metric is now live", upcoming["available"] is True, str(upcoming))
        check(
            "upcoming counts only future scheduled ones",
            upcoming["value"] == 1,
            f"got {upcoming['value']} (one cancelled, one future scheduled)",
        )
        check("upcoming metric flags the provisional store", "PROJ-422" in upcoming["note"])
        check("sent metric is live and zero", sent["available"] is True and sent["value"] == 0, str(sent))
        check("sent metric explains the zero", "PROJ-395" in sent["note"], str(sent))

        # ── Delete ────────────────────────────────────────────
        r = client.delete(f"/api/reminders/{naive_id}")
        check("delete returns 204", r.status_code == 204, f"got {r.status_code}")
        check("deleted record is gone", client.get(f"/api/reminders/{naive_id}").status_code == 404)
        check("delete unknown id is 404", client.delete("/api/reminders/nope").status_code == 404)

        # ── Persistence and durability ────────────────────────
        check("store file exists on disk", store_path.exists())
        rows = json.loads(store_path.read_text(encoding="utf-8"))
        check("store holds the surviving record", len(rows) == 1, str(len(rows)))
        check("no temp file left behind", not store_path.with_suffix(".json.tmp").exists())

        # A fresh store over the same file must see the same data.
        reminders.set_store(reminders.JsonFileStore(store_path))
        check("data survives a new store instance", len(reminders.get_store().list()) == 1)

        # A corrupt file must be reported, not silently treated as empty —
        # "all your reminders vanished" is the worst possible failure here.
        store_path.write_text("{ not json", encoding="utf-8")
        reminders.set_store(reminders.JsonFileStore(store_path))
        r = client.get("/api/reminders")
        check("corrupt store surfaces as 500, not empty", r.status_code == 500, f"got {r.status_code}")
        s = client.get("/api/stats").json()
        up = next(m for m in s["metrics"] if m["key"] == "reminders_upcoming")
        check("corrupt store degrades the metric, not the page", up["available"] is False, str(up))

        # ── Provisional contract is published ─────────────────
        schema = Path(ROOT) / "docs" / "contracts" / "reminder.provisional.schema.json"
        check("provisional contract is written down", schema.exists(), str(schema))
        if schema.exists():
            doc = json.loads(schema.read_text(encoding="utf-8"))
            check("contract is marked provisional", "PROVISIONAL" in doc.get("title", ""))
            check("contract names PROJ-404 as the authority", "PROJ-404" in doc.get("$comment", ""))
            props = set(doc.get("properties", {}))
            from dataclasses import fields as dc_fields

            model = {f.name for f in dc_fields(reminders.Reminder)}
            check("contract and model agree on fields", props == model, f"schema-only={props-model} model-only={model-props}")
    finally:
        reminders.set_store(None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
