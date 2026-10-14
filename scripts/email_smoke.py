#!/usr/bin/env python3
# scripts/email_smoke.py — prove email delivery end to end (PROJ-481)
#
#   python scripts/email_smoke.py --to you@example.com            # direct test email
#   python scripts/email_smoke.py --to you@example.com --reminder # + a real reminder
#
# Needs SMTP_* in .env (scripts/set_gmail_smtp.sh writes them). The --reminder
# run uses a throwaway CRM store and auth DB in a temp folder, so it never
# touches real contacts: it creates one opted-in contact whose preferred
# channel is email, schedules a reminder for one minute from now, then runs
# the same WebReminderBridge the server runs until the reminder is sent.
# Screenshot the output and the received email for the handover pack.

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--to", required=True, help="address to send the test to")
    ap.add_argument("--reminder", action="store_true", help="also schedule and send a reminder")
    args = ap.parse_args()

    if args.reminder:
        # Before anything imports config: keep this run's data out of the real stores.
        tmp = Path(tempfile.mkdtemp(prefix="af-email-smoke-"))
        os.environ["CRM_STORE_DIR"] = str(tmp / "store")
        os.environ["AUTH_DB_PATH"] = str(tmp / "auth.db")

    from config import settings
    from agent.delivery import EmailChannel

    if not (settings.SMTP_HOST and settings.SMTP_FROM_EMAIL):
        print("FAIL  SMTP is not configured: set SMTP_HOST, SMTP_FROM_EMAIL, SMTP_USERNAME, "
              "SMTP_PASSWORD (run scripts/set_gmail_smtp.sh).")
        return 1
    print(f"SMTP  {settings.SMTP_HOST}:{settings.SMTP_PORT} as {settings.SMTP_FROM_EMAIL}")

    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    result = EmailChannel().send(args.to, f"Agent Factory SMTP test sent at {stamp}.",
                                 subject="Agent Factory: SMTP test")
    print(("PASS" if result.ok else "FAIL") + f"  direct email to {args.to}"
          + ("" if result.ok else f": {result.error}"))
    if not result.ok:
        return 1
    if not args.reminder:
        return 0

    from auth import db as auth_db, tenancy
    from agent.reminders.web_bridge import WebReminderBridge
    from app.web import reminders

    auth_db.DB_PATH = os.environ["AUTH_DB_PATH"]
    auth_db.init_db()
    tenancy.init_tenancy()
    cid = tenancy.create_contact(1, "+15550100199", "Email Smoke Test", email=args.to,
                                 consent_state="opted_in", preferred_channel="email")
    send_at = (reminders._now() + timedelta(minutes=1)).replace(second=0, microsecond=0)
    if send_at <= reminders._now() + timedelta(seconds=5):
        send_at += timedelta(minutes=1)
    r = reminders.create_reminder({
        "contact_id": cid, "send_at": send_at.isoformat(),
        "message": "Hi {first_name}, this reminder was scheduled for {time} on {date} "
                   "and sent by the Agent Factory reminders engine.",
    })
    print(f"WAIT  reminder #{r['id']} scheduled for {send_at.strftime('%H:%M:%S')}; polling every 5s")

    bridge = WebReminderBridge()
    deadline = time.time() + 180
    while time.time() < deadline:
        for res in bridge.tick():
            row = reminders.get_reminder(res["reminder_id"])
            if res.get("ok"):
                late = (reminders.parse_dt(row["sent_at"]) - send_at).total_seconds()
                print(f"PASS  reminder sent at {row['sent_at']} ({late:.0f}s after its send time)")
                return 0
            print(f"FAIL  reminder {row['status']}: {res.get('error') or res.get('reason')}")
            return 1
        time.sleep(5)
    print("FAIL  reminder was not sent within 3 minutes")
    return 1


if __name__ == "__main__":
    sys.exit(main())
