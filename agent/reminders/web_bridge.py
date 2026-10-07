# agent/reminders/web_bridge.py
# ──────────────────────────────────────────────────────────────
# Drives sends for reminders created through the Contacts/Dashboard
# UI (app/web/reminders.py, PROJ-438/439) — a second reminder source
# alongside this package's own ReminderStore (used by PROJ-402's
# booking tie-in). app/web/reminders.py's own docstring already names
# this integration: "Nothing sends: the Reminders Engine is PROJ-395.
# mark_sent/mark_blocked are the transitions that engine will drive."
#
# This is a bridge, not a migration: app/web/reminders.py keeps its
# own JSON-backed store exactly as built. This module reads its due,
# 'scheduled' reminders, sends through the same PROJ-396 delivery
# channels the rest of the engine uses, and writes the outcome back
# via mark_sent/mark_blocked/mark_failed — so a reminder created in
# the dashboard UI actually gets delivered, without app/web/reminders.py
# needing to know anything about SQLite, Twilio, or SMTP.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import time

from agent.delivery import EmailChannel, SMSChannel
from app.web.store import DEFAULT_ORG_ID
from config.settings import REMINDER_POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)

# app/web/contacts.py's CHANNELS = ("sms", "email", "telegram") — telegram
# has no delivery adapter in agent/delivery/ (no bot integration exists
# anywhere in this app), so it's an honest, named gap rather than a
# silent drop.
_CHANNEL_MAP = {"sms": "phone_number", "email": "email"}


class WebReminderBridge:
    def __init__(self, channels: dict | None = None):
        self.channels = channels or {"sms": SMSChannel(), "email": EmailChannel()}

    def tick(self, org_id: int = DEFAULT_ORG_ID) -> list[dict]:
        from app.web import reminders

        now = reminders._now()
        results = []
        for item in reminders.list_reminders(org_id):
            if item.get("status") != "scheduled":
                continue
            if reminders.parse_dt(item["send_at"]) > now:
                continue
            results.append(self._send_one(item, org_id))
        return results

    def _send_one(self, reminder: dict, org_id: int) -> dict:
        from app.web import contacts, reminders

        reminder_id = reminder["id"]
        decision = reminders.dispatch_check(reminder_id, org_id)
        if not decision["allowed"]:
            reminders.mark_blocked(reminder_id, decision["reason"], org_id)
            return {"reminder_id": reminder_id, "ok": False, "blocked": True, "reason": decision["reason"]}

        contact = contacts.get_contact(reminder["contact_id"], org_id)
        preferred = contact.get("preferred_channel", "sms") if contact else "sms"
        address_field = _CHANNEL_MAP.get(preferred)
        channel = self.channels.get(preferred)

        if address_field is None or channel is None:
            reason = f"channel '{preferred}' has no delivery adapter"
            reminders.mark_failed(reminder_id, reason, org_id)
            return {"reminder_id": reminder_id, "ok": False, "error": reason}

        address = contact.get(address_field) if contact else None
        if not address:
            reason = f"contact has no {address_field} for its preferred channel ({preferred})"
            reminders.mark_failed(reminder_id, reason, org_id)
            return {"reminder_id": reminder_id, "ok": False, "error": reason}

        kwargs = {"subject": "Reminder"} if preferred == "email" else {}
        result = channel.send(address, reminder["message"], **kwargs)

        if result.ok:
            reminders.mark_sent(reminder_id, org_id)
            return {"reminder_id": reminder_id, "ok": True}

        reminders.mark_failed(reminder_id, result.error or "unknown delivery error", org_id)
        return {"reminder_id": reminder_id, "ok": False, "error": result.error}

    def run_forever(self, poll_interval: int | None = None, org_id: int = DEFAULT_ORG_ID) -> None:
        """Run as its own process alongside agent/reminders/scheduler.py's
        run_forever — same polling pattern, different reminder source."""
        interval = poll_interval or REMINDER_POLL_INTERVAL_SECONDS
        logger.info("Web reminder bridge starting, polling every %ss", interval)
        while True:
            try:
                results = self.tick(org_id)
                sent = sum(1 for r in results if r.get("ok"))
                if results:
                    logger.info("Tick: %d due, %d sent", len(results), sent)
            except Exception:
                logger.exception("Web reminder bridge tick failed")
            time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    WebReminderBridge().run_forever()
