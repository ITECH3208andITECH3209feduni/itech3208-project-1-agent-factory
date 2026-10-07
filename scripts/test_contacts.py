#!/usr/bin/env python3
# scripts/test_contacts.py
# ──────────────────────────────────────────────────────────────
# Contacts CRM, notification preferences, consent, and the reminders
# migration onto the published contract.
#   PROJ-417 schema · PROJ-418 CRUD · PROJ-419 profiles UI
#   PROJ-420 CSV import · PROJ-421 tests · PROJ-440 prefs · PROJ-441 consent
#
# Run: python scripts/test_contacts.py
#
# Uses temporary tables, so the developer's own store/ is never touched.
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


def soon(**kw) -> str:
    return (datetime.now().astimezone() + timedelta(**kw)).isoformat()


def main() -> int:
    print("Contacts CRM, preferences, consent, reminders migration\n")

    try:
        from fastapi.testclient import TestClient
    except ImportError as exc:
        print(f"  SKIP  TestClient unavailable ({exc})")
        return 0

    from contracts.schemas import ConsentState, normalise_phone
    from app.web import consent, contacts, reminders, store
    from app.web.main import app
    from auth import db as auth_db, tenancy

    tmp = Path(tempfile.mkdtemp(prefix="af-contacts-"))
    # Contacts now live in auth.tenancy's real SQLite table (PROJ-392),
    # not app/web/store.py's JSON files — isolate that instead of
    # swapping a JSON table for "contacts". reminders/consent_events
    # are unaffected, still JSON-backed.
    auth_db.DB_PATH = str(tmp / "auth_users.db")
    auth_db.init_db()
    tenancy.init_tenancy()
    for name in ("reminders", "consent_events"):
        store.set_table(name, store.JsonTable(tmp / f"{name}.json", name))

    client = TestClient(app)

    try:
        # ══ PROJ-417: schema and phone normalisation ══════════
        print("-- PROJ-417 schema")
        check("uses the published contract's normaliser",
              normalise_phone("0412 345 678") == "+61412345678")

        r = client.post("/api/contacts", json={"phone_number": "0412 345 678", "name": "Jane Citizen"})
        check("create returns 201", r.status_code == 201, f"{r.status_code}: {r.text[:120]}")
        jane = r.json()
        check("id is an int", isinstance(jane["id"], int), repr(jane["id"]))
        check("org_id is set", isinstance(jane["org_id"], int))
        check("phone stored in E.164", jane["phone_number"] == "+61412345678", jane["phone_number"])
        check("new contact is not opted in",
              jane["consent_state"] == ConsentState.UNKNOWN.value, jane["consent_state"])
        check("default channel is sms", jane["preferred_channel"] == "sms")
        check("created_at is set", bool(jane.get("created_at")))

        # Ids are sequential, not reused.
        r2 = client.post("/api/contacts", json={"phone_number": "0498765432", "name": "Bob Bravo"})
        bob = r2.json()
        check("ids increment", bob["id"] == jane["id"] + 1, f"{jane['id']} -> {bob['id']}")

        # ══ PROJ-418: CRUD and validation ═════════════════════
        print("-- PROJ-418 CRUD")
        r = client.post("/api/contacts", json={})
        check("empty create is 422", r.status_code == 422)
        check("names the missing field", "phone_number" in r.json().get("errors", {}))

        r = client.post("/api/contacts", json={"phone_number": "abcdefg"})
        check("non-numeric phone rejected", r.status_code == 422, r.text[:100])

        # The whole point of normalising first: these are the same person.
        r = client.post("/api/contacts", json={"phone_number": "+61412345678"})
        check("duplicate in another format is rejected", r.status_code == 422)
        check("duplicate error names the existing contact",
              "already exists" in r.json()["errors"].get("phone_number", ""))

        r = client.post("/api/contacts", json={"phone_number": "0411111111", "nmae": "typo"})
        check("unknown field rejected", r.status_code == 422)

        r = client.get("/api/contacts")
        check("list returns both", r.json()["count"] == 2, str(r.json()["count"]))

        r = client.get(f"/api/contacts/{jane['id']}")
        check("get one returns 200", r.status_code == 200)
        check("get one includes consent history", isinstance(r.json().get("consent_history"), list))
        check("get one includes a send decision", "send_decision" in r.json())

        check("unknown contact is 404", client.get("/api/contacts/99999").status_code == 404)

        r = client.patch(f"/api/contacts/{jane['id']}", json={"name": "Jane C."})
        check("patch updates", r.status_code == 200 and r.json()["name"] == "Jane C.")
        check("patch leaves other fields", r.json()["phone_number"] == "+61412345678")
        check("patch unknown id is 404",
              client.patch("/api/contacts/99999", json={"name": "x"}).status_code == 404)

        r = client.get("/api/contacts?q=bravo")
        check("search by name", r.json()["count"] == 1, str(r.json()["count"]))
        r = client.get("/api/contacts?q=61412")
        check("search by phone", r.json()["count"] == 1, str(r.json()["count"]))
        r = client.get("/api/contacts?consent_state=nonsense")
        check("bad consent filter is 422", r.status_code == 422)

        # ══ PROJ-440: preferences ═════════════════════════════
        print("-- PROJ-440 preferences")
        r = client.patch(f"/api/contacts/{jane['id']}", json={"preferred_channel": "email"})
        check("email channel without an address is rejected", r.status_code == 422, r.text[:140])
        check("error explains why",
              "email address" in r.json()["errors"].get("preferred_channel", ""))

        r = client.patch(f"/api/contacts/{jane['id']}",
                         json={"email": "jane@example.com", "preferred_channel": "email"})
        check("email channel works once an address exists", r.status_code == 200, r.text[:140])

        r = client.patch(f"/api/contacts/{jane['id']}", json={"email": "not-an-email"})
        check("malformed email rejected", r.status_code == 422)

        r = client.patch(f"/api/contacts/{jane['id']}", json={"quiet_hours_start": "9am"})
        check("non-HH:MM quiet hours rejected", r.status_code == 422)
        r = client.patch(f"/api/contacts/{jane['id']}", json={"quiet_hours_start": "21:00"})
        check("one-sided quiet hours rejected", r.status_code == 422, r.text[:140])
        r = client.patch(f"/api/contacts/{jane['id']}",
                         json={"quiet_hours_start": "21:00", "quiet_hours_end": "07:00"})
        check("both ends accepted", r.status_code == 200, r.text[:140])

        # Windows crossing midnight are the normal case.
        c = contacts.get_contact(jane["id"])
        at = datetime.now().astimezone()
        check("inside a midnight-crossing window (23:00)",
              contacts.in_quiet_hours(c, at.replace(hour=23, minute=0)) is True)
        check("inside it after midnight (03:00)",
              contacts.in_quiet_hours(c, at.replace(hour=3, minute=0)) is True)
        check("outside it at midday",
              contacts.in_quiet_hours(c, at.replace(hour=12, minute=0)) is False)
        check("no window set means never quiet",
              contacts.in_quiet_hours(contacts.get_contact(bob["id"]), at) is False)

        # ══ PROJ-441: consent capture and enforcement ═════════
        print("-- PROJ-441 consent")
        d = client.get(f"/api/contacts/{bob['id']}").json()["send_decision"]
        check("unknown consent blocks sending", d["allowed"] is False, str(d))
        check("reason names consent", d["code"] == "no_consent", str(d))

        r = client.post(f"/api/contacts/{bob['id']}/consent",
                        json={"state": "opted_in", "source": "web_form"})
        check("opt-in recorded", r.status_code == 200, r.text[:140])
        check("state changed", r.json()["consent_state"] == "opted_in")
        check("audit trail has entries", len(r.json()["consent_history"]) >= 2,
              str(len(r.json()["consent_history"])))

        d = client.get(f"/api/contacts/{bob['id']}").json()["send_decision"]
        check("opted in allows sending", d["allowed"] is True, str(d))

        r = client.post(f"/api/contacts/{bob['id']}/consent",
                        json={"state": "opted_out", "source": "sms_stop"})
        check("opt-out recorded", r.status_code == 200 and r.json()["consent_state"] == "opted_out")

        # Reversing a STOP must not be a casual flag flip.
        r = client.post(f"/api/contacts/{bob['id']}/consent",
                        json={"state": "opted_in", "source": "web_form"})
        check("re-opting-in after a STOP is refused", r.status_code == 409, f"{r.status_code}")
        check("refusal explains what is needed",
              "evidence" in str(r.json().get("errors", {})).lower())

        r = client.post(f"/api/contacts/{bob['id']}/consent", json={"state": "nonsense"})
        check("unknown consent state is 422", r.status_code == 422)

        # Pending is invited, not agreed — still blocks.
        client.post(f"/api/contacts/{jane['id']}/consent",
                    json={"state": "pending", "source": "web_form"})
        d = client.get(f"/api/contacts/{jane['id']}").json()["send_decision"]
        check("pending still blocks sending", d["allowed"] is False, str(d))

        hist = consent.history(bob["id"])
        check("history is newest first",
              hist == sorted(hist, key=lambda h: h["occurred_at"], reverse=True))
        check("history records old and new state",
              any(h.get("old_state") and h.get("new_state") for h in hist))

        # Quiet hours block a send even for an opted-in contact.
        client.post(f"/api/contacts/{jane['id']}/consent",
                    json={"state": "opted_in", "source": "web_form"})
        dec = consent.check_send(jane["id"], when=at.replace(hour=23, minute=30))
        check("quiet hours block an opted-in contact", dec.allowed is False, dec.reason)
        check("quiet-hours block is distinguishable from consent",
              dec.code == "quiet_hours", dec.code)
        dec = consent.check_send(jane["id"], when=at.replace(hour=12, minute=0))
        check("outside quiet hours it is allowed", dec.allowed is True, dec.reason)

        check("check_send with no contact is refused",
              consent.check_send(None).allowed is False)

        # ══ Reminders on the contract ═════════════════════════
        print("-- reminders migrated to the PROJ-404 contract")
        r = client.post("/api/reminders", json={
            "contact_id": jane["id"], "message": "Appointment tomorrow at 2pm",
            "send_at": soon(days=2)})
        check("create returns 201", r.status_code == 201, r.text[:140])
        rem = r.json()
        check("reminder id is an int", isinstance(rem["id"], int))
        check("uses message, not title", "message" in rem and "title" not in rem)
        check("uses send_at, not due_at", "send_at" in rem and "due_at" not in rem)
        check("has sent_at, initially null", rem.get("sent_at") is None)
        check("no per-reminder channel", "channel" not in rem)

        r = client.post("/api/reminders", json={"message": "x", "send_at": soon(days=1)})
        check("contact_id is required", r.status_code == 422)
        r = client.post("/api/reminders", json={
            "contact_id": 99999, "message": "x", "send_at": soon(days=1)})
        check("unknown contact is rejected", r.status_code == 422)
        check("error names the contact", "99999" in str(r.json()["errors"]))

        r = client.post("/api/reminders", json={
            "contact_id": jane["id"], "message": "x" * 1601, "send_at": soon(days=1)})
        check("message over 1600 chars rejected", r.status_code == 422)

        r = client.post("/api/reminders", json={
            "contact_id": jane["id"], "message": "late", "send_at": "2020-01-01T09:00"})
        check("past send_at rejected", r.status_code == 422)

        r = client.post("/api/reminders", json={
            "contact_id": jane["id"], "message": "x", "send_at": soon(days=1), "status": "sent"})
        check("client cannot claim 'sent'", r.status_code == 422)
        check("message points at the engine", "PROJ-395" in str(r.json()["errors"]))

        # 'cancelled' is gone from the contract.
        r = client.post("/api/reminders", json={
            "contact_id": jane["id"], "message": "x", "send_at": soon(days=1), "status": "cancelled"})
        check("'cancelled' is no longer a valid status", r.status_code == 422)
        check("blocked is in the status set", "blocked" in reminders.STATUSES)
        check("cancelled is not", "cancelled" not in reminders.STATUSES)

        # Dispatch check surfaces the consent decision.
        dd = client.get(f"/api/reminders/{rem['id']}/dispatch-check").json()
        check("dispatch-check returns a decision", "allowed" in dd, str(dd))
        check("dispatch-check is scoped to the reminder", dd["reminder_id"] == rem["id"])
        check("dispatch-check 404s for unknown",
              client.get("/api/reminders/99999/dispatch-check").status_code == 404)

        # Engine transitions.
        reminders.mark_blocked(rem["id"], "contact opted out")
        got = reminders.get_reminder(rem["id"])
        check("mark_blocked sets status", got["status"] == "blocked")
        check("mark_blocked keeps the reason", got["blocked_reason"] == "contact opted out")
        reminders.mark_sent(rem["id"])
        got = reminders.get_reminder(rem["id"])
        check("mark_sent sets sent_at", bool(got["sent_at"]))

        r = client.get("/api/reminders?status=sent")
        check("status filter works on the new set", r.json()["total"] == 1, str(r.json()["total"]))
        r = client.get("/api/reminders?contact_id=" + str(jane["id"]))
        check("contact_id filter works", r.json()["total"] >= 1)
        r = client.get("/api/reminders?q=appointment")
        check("search is over message", r.json()["total"] == 1, str(r.json()["total"]))

        # ══ PROJ-420: CSV import ══════════════════════════════
        print("-- PROJ-420 CSV import")
        csv = (
            "phone_number,name,email\n"
            "0400000001,Alpha,\n"
            "0400000002,Beta,beta@example.com\n"
            "0400000001,Alpha Again,\n"          # duplicate within the file
            "+61412345678,Jane Dup,\n"           # already exists
            "not-a-number,Broken,\n"             # invalid
            ",No Phone,\n"                       # empty phone
        )
        r = client.post("/api/contacts/import?dry_run=true", content=csv.encode())
        check("dry run returns 200", r.status_code == 200, r.text[:140])
        d = r.json()
        check("dry run reports itself", d["dry_run"] is True)
        check("dry run would create 2", d["created_count"] == 2, str(d["created_count"]))
        check("dry run skips 2 (file dup + existing)", d["skipped_count"] == 2, str(d["skipped_count"]))
        check("dry run fails 2 (invalid + empty)", d["failed_count"] == 2, str(d["failed_count"]))
        check("dry run wrote nothing", client.get("/api/contacts").json()["count"] == 2)
        check("errors carry line numbers", all("line" in f for f in d["failed"]))

        r = client.post("/api/contacts/import", content=csv.encode())
        d = r.json()
        check("real import creates 2", d["created_count"] == 2, str(d["created_count"]))
        check("real import reports ids", all("id" in c for c in d["created"]))
        check("contacts now number 4", client.get("/api/contacts").json()["count"] == 4)

        # Re-importing the same file must be idempotent, not a wall of errors.
        d2 = client.post("/api/contacts/import", content=csv.encode()).json()
        check("re-import creates nothing", d2["created_count"] == 0, str(d2["created_count"]))
        check("re-import skips the existing ones", d2["skipped_count"] == 4, str(d2["skipped_count"]))

        # Imported contacts are NOT consented.
        alpha_row = tenancy.get_contact_by_phone(1, "+61400000001")
        alpha = dict(alpha_row)
        check("imported contact is not opted in",
              alpha["consent_state"] == ConsentState.UNKNOWN.value, str(alpha["consent_state"]))
        check("import is recorded in the audit trail",
              any(h["source"] == "import" for h in consent.history(alpha["id"])))

        r = client.post("/api/contacts/import", content=b"name,email\nx,y\n")
        check("missing phone_number column is 422", r.status_code == 422)
        check("error says which column is needed",
              "phone_number" in str(r.json()["errors"]))
        r = client.post("/api/contacts/import", content=b"")
        check("empty file is 422", r.status_code == 422)

        # Excel on Windows exports cp1252 rather than UTF-8.
        r = client.post("/api/contacts/import?dry_run=true",
                        content="phone_number,name\n0400000009,Renée\n".encode("cp1252"))
        check("cp1252 file is decoded", r.status_code == 200, r.text[:140])

        r = client.get("/api/contacts-template.csv")
        check("CSV template downloads", r.status_code == 200)
        check("template has the header", "phone_number" in r.text)

        # ══ PROJ-419: UI pages ════════════════════════════════
        print("-- PROJ-419 UI")
        for path in ("/contacts", "/contacts/new", "/contacts/import",
                     f"/contacts/{jane['id']}", f"/contacts/{jane['id']}/edit",
                     "/reminders", "/reminders/new", f"/reminders/{rem['id']}/edit"):
            check(f"GET {path} returns 200", client.get(path).status_code == 200)

        prof = client.get(f"/contacts/{jane['id']}").text
        check("profile shows consent controls", 'id="optin"' in prof and 'id="optout"' in prof)
        check("profile shows an audit trail", 'id="consenthistory"' in prof)
        check("profile shows the send decision", 'id="senddecision"' in prof)
        check("profile lists that contact's reminders", 'id="reminders"' in prof)
        check("consent is a dot AND a word", 'consentBadge' in prof)

        imp = client.get("/contacts/import").text
        check("import page warns that import is not consent",
              "not opted in" in imp.lower() or "not consent" in imp.lower())
        check("import page offers a dry run", 'id="dry"' in imp)

        form = client.get("/reminders/new").text
        check("reminder form has a contact picker", 'id="contact_id"' in form)
        check("reminder form warns about consent", "consentwarn" in form)
        check("reminder form has no channel field", 'id="channel"' not in form)

        for page in (prof, imp, form, client.get("/contacts").text):
            check("page escapes interpolated values", "const esc" in page)
            check("page has no CDN dependency", "https://" not in page and "cdn." not in page)

        # ══ Dashboard metrics ═════════════════════════════════
        print("-- dashboard metrics")
        s = client.get("/api/stats").json()
        by = {m["key"]: m for m in s["metrics"]}
        check("contacts metric is live", by["contacts_total"]["available"] is True)
        check("contacts metric counts them", by["contacts_total"]["value"] == 4,
              str(by["contacts_total"]["value"]))
        check("contacts note reports opted-in count",
              "opted in" in by["contacts_total"]["note"], by["contacts_total"]["note"])
        check("blocked metric exists", "reminders_blocked" in by)
        check("no metric is pending now", s["pending_count"] == 0, str(s["pending_count"]))

        # ══ Store behaviour ═══════════════════════════════════
        print("-- store")
        check("delete works", client.delete(f"/api/contacts/{bob['id']}").status_code == 204)
        check("deleted contact is 404", client.get(f"/api/contacts/{bob['id']}").status_code == 404)
        check("delete unknown is 404", client.delete("/api/contacts/99999").status_code == 404)

        # A deleted id must not be handed out again.
        new = client.post("/api/contacts", json={"phone_number": "0455555555"}).json()
        check("ids are never reused", new["id"] != bob["id"], f"{new['id']} vs {bob['id']}")

        # Cross-org reads must not leak.
        other_id = tenancy.create_contact(999, "+61999999999", "Other org")
        check("other org's row is invisible",
              contacts.get_contact(other_id) is None)
        check("other org's row is not listed",
              all(c["id"] != other_id for c in contacts.list_contacts()))

        # A broken store must surface, not read as empty — same design
        # property as before, now against the real SQLite file instead
        # of a JSON one: point at a path sqlite cannot open at all.
        auth_db.DB_PATH = str(tmp / "no" / "such" / "dir" / "auth_users.db")
        check("corrupt store is a 500", client.get("/api/contacts").status_code == 500)
        auth_db.DB_PATH = str(tmp / "auth_users.db")
    finally:
        for name in ("reminders", "consent_events"):
            store.set_table(name, None)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
