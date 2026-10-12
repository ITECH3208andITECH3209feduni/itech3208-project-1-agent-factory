#!/usr/bin/env python3
"""
scripts/seed_demo.py — load a demo account and sample data for the poster
session, through the app's own HTTP API (so it exercises the real code paths).

    python3 scripts/seed_demo.py [base_url]        # default http://localhost:8000

Safe by design:
  * every phone number is a fictional US 555-01xx number (reserved for fiction)
  * every reminder is scheduled 8+ days out, so the scheduler cannot send any
    of them during a demo
  * no real person, and no Australian number, appears here
Running it twice does not duplicate contacts.

Demo login (local demo data only, not a real account):
"""

import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

DEMO_EMAIL = "poster.demo@example.com"
DEMO_ORG = "Demo Dental Clinic"
DEMO_PASSWORD = "AgentFactory-Demo-2026"

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")

CONTACTS = [
    ("+15555550101", "Alex Rivera",   "alex.rivera@example.com",   "sms",   "opted_in"),
    ("+15555550102", "Priya Nair",    "priya.nair@example.com",    "email", "opted_in"),
    ("+15555550103", "Sam Okafor",    "sam.okafor@example.com",    "sms",   "opted_in"),
    ("+15555550104", "Mei Tanaka",    "mei.tanaka@example.com",    "email", "opted_out"),
    ("+15555550105", "Jordan Ellis",  "jordan.ellis@example.com",  "sms",   "unknown"),
    ("+15555550106", "Fatima Hassan", "fatima.hassan@example.com", "email", "opted_in"),
]

REMINDERS = [
    (0, "Hi Alex, a reminder that your dental check-up is booked for next week.", 8),
    (1, "Hi Priya, your quarterly review meeting is coming up. Reply STOP to opt out.", 9),
    (2, "Hi Sam, your service appointment is confirmed. See you soon!", 10),
    (5, "Hi Fatima, your consultation is scheduled. Please bring your documents.", 12),
    (0, "Hi Alex, don't forget to complete your intake form before your visit.", 14),
]

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def main():
    # An organisation owner who signs in with an email, like a real visitor would.
    call("POST", "/orgs/register", {"org_name": DEMO_ORG, "email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    s, body = call("POST", "/auth/login", {"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    if s != 200:
        sys.exit(f"Could not log in the demo user ({s}): {body}")
    print(f"logged in as {DEMO_EMAIL}")

    s, existing = call("GET", "/crm/api/contacts")
    if s != 200:
        sys.exit(f"Could not read contacts ({s}): {existing}")
    by_phone = {c["phone_number"]: c for c in existing.get("contacts", [])}

    ids = []
    for phone, name, email, channel, consent in CONTACTS:
        if phone in by_phone:
            ids.append(by_phone[phone]["id"])
            continue
        s, c = call("POST", "/crm/api/contacts", {
            "phone_number": phone, "name": name, "email": email,
            "preferred_channel": channel, "consent_state": consent,
        })
        if s != 201:
            sys.exit(f"Could not create {name} ({s}): {c}")
        ids.append(c["id"])
    print(f"contacts ready: {len(ids)}")

    s, existing_r = call("GET", "/crm/api/reminders")
    have = {(r["contact_id"], r["message"]) for r in (existing_r or {}).get("reminders", [])}
    made = 0
    for idx, message, days in REMINDERS:
        if (ids[idx], message) in have:
            continue
        when = (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()
        s, r = call("POST", "/crm/api/reminders", {"contact_id": ids[idx], "message": message, "send_at": when})
        if s != 201:
            sys.exit(f"Could not create reminder ({s}): {r}")
        made += 1
    print(f"reminders created: {made} (all 8+ days out, none can send during the demo)")

    s, r = call("POST", "/analytics/seed-demo-data?count=40")
    print(f"analytics demo data: {'loaded' if s == 200 else f'skipped ({s})'}")
    print(f"\nOpen {BASE}/login and sign in as {DEMO_EMAIL}")


if __name__ == "__main__":
    main()
