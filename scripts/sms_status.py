#!/usr/bin/env python3
# scripts/sms_status.py — SMS delivery evidence for the handover pack (PROJ-482)
#
#   python scripts/sms_status.py                     # read-only report
#   python scripts/sms_status.py --send +1XXXXXXXXXX # also send ONE test SMS
#
# Read-only by default. Reports, from the Twilio account in .env:
#   - account type (Trial vs Full) and status
#   - the sending number: country, capabilities
#   - US A2P 10DLC: brand registrations and each messaging service's campaign
#   - verified caller IDs (the only numbers a trial account can text)
#   - the last 20 outbound messages with status and error code, which is the
#     evidence itself: 'delivered', or 'undelivered' with 30034 (unregistered
#     A2P traffic) or 21608 (unverified number on a trial account)
#
# --send sends one SMS and then polls its status for two minutes. It refuses
# the Australian number from the earlier test incident (see HANDOFF.md).
# Paste the output into the handover pack; it contains no secrets.

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FORBIDDEN = {"+61400123456"}   # HANDOFF.md section 6: never send to this number

ERROR_HINTS = {
    "30034": "US A2P 10DLC: message from an unregistered number (needs brand + campaign registration)",
    "30032": "toll-free number not verified",
    "30007": "carrier filtered the message as spam",
    "30003": "handset unreachable / switched off",
    "30005": "unknown or inactive destination number",
    "21608": "trial account: the destination is not a verified caller ID",
    "21610": "recipient replied STOP (opted out)",
    "21408": "account is not permitted to send to this region",
}


def section(title):
    print(f"\n== {title} " + "=" * max(0, 60 - len(title)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--send", metavar="TO", help="send one test SMS to this E.164 number")
    args = ap.parse_args()

    from config import settings

    sid, token, from_number = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN,
                               settings.TWILIO_FROM_NUMBER)
    if not (sid and token and from_number):
        print("Twilio is not configured: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and "
              "TWILIO_FROM_NUMBER in .env (or run this in the Render shell).")
        return 1

    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client

    client = Client(sid, token)

    section("Account")
    acct = client.api.v2010.accounts(sid).fetch()
    print(f"type: {acct.type}   status: {acct.status}   name: {acct.friendly_name}")
    if acct.type == "Trial":
        print("NOTE  trial accounts can only text verified caller IDs and prefix every message.")

    section("Sending number")
    nums = client.incoming_phone_numbers.list(phone_number=from_number, limit=1)
    if nums:
        n = nums[0]
        caps = ", ".join(k for k, v in (n.capabilities or {}).items() if v)
        print(f"{n.phone_number}   capabilities: {caps}")
        is_us = n.phone_number.startswith("+1")
        print("US number: A2P 10DLC registration applies to SMS to US recipients." if is_us
              else "Not a US number: A2P 10DLC does not apply.")
    else:
        print(f"{from_number} is not an incoming number on this account (check TWILIO_FROM_NUMBER).")

    section("A2P 10DLC registration")
    try:
        brands = client.messaging.v1.brand_registrations.list(limit=20)
        if not brands:
            print("No brand registration. Unregistered US long-code SMS is blocked (error 30034).")
        for b in brands:
            print(f"brand {b.sid}: status={b.status} type={getattr(b, 'brand_type', '?')}")
        services = client.messaging.v1.services.list(limit=20)
        if not services:
            print("No messaging service, so no campaign can exist yet.")
        for svc in services:
            campaigns = client.messaging.v1.services(svc.sid).us_app_to_person.list(limit=5)
            state = ", ".join(f"{c.campaign_status}" for c in campaigns) or "no campaign"
            print(f"service {svc.friendly_name} ({svc.sid}): {state}")
    except TwilioRestException as exc:
        print(f"Could not read registration ({exc.code}): {exc.msg}")

    section("Verified caller IDs (trial accounts can text only these)")
    try:
        ids = client.outgoing_caller_ids.list(limit=20)
        print("\n".join(f"{c.phone_number}  {c.friendly_name}" for c in ids) or "none")
    except TwilioRestException as exc:
        print(f"Could not list ({exc.code}): {exc.msg}")

    section("Last 20 outbound messages")
    msgs = client.messages.list(from_=from_number, limit=20)
    if not msgs:
        print("none")
    for m in msgs:
        code = str(m.error_code) if m.error_code else ""
        hint = f"  <- {ERROR_HINTS.get(code, '')}" if code else ""
        print(f"{m.date_created:%Y-%m-%d %H:%M}  to {m.to}  {m.status:<11} {code}{hint}")

    if not args.send:
        return 0

    to = args.send.replace(" ", "")
    if to in FORBIDDEN:
        print(f"\nRefusing to send to {to}: see HANDOFF.md section 6.")
        return 2
    section(f"Test send to {to}")
    try:
        m = client.messages.create(to=to, from_=from_number,
                                   body="Agent Factory SMS delivery test (PROJ-482).")
    except TwilioRestException as exc:
        print(f"Rejected by Twilio ({exc.code}): {exc.msg}  {ERROR_HINTS.get(str(exc.code), '')}")
        return 1
    print(f"queued as {m.sid}; polling status for up to 2 minutes")
    for _ in range(24):
        time.sleep(5)
        m = client.messages(m.sid).fetch()
        if m.status in ("delivered", "undelivered", "failed"):
            break
    code = str(m.error_code) if m.error_code else ""
    print(f"final status: {m.status} {code} {ERROR_HINTS.get(code, '')}".rstrip())
    return 0 if m.status == "delivered" else 1


if __name__ == "__main__":
    sys.exit(main())
