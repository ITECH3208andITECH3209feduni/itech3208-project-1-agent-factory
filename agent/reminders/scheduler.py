# agent/reminders/scheduler.py
# ──────────────────────────────────────────────────────────────
# Scheduler process (PROJ-423) — Dilraj Singh
#
# Polls the reminders store for due reminders and sends each one
# through the matching delivery channel (agent/delivery). Designed to
# "just work" across restarts because ALL state lives in SQLite
# (ReminderStore), not in this process's memory:
#   - a crash mid-send leaves the reminder 'sending', and
#     reclaim_stale_sending() bounces it back to 'pending' so the next
#     process picks it up again
#   - claim() is an atomic DB transition, so even if two ticks (or two
#     scheduler processes) race on the same reminder, only one of them
#     actually sends it
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import time

from agent.delivery import EmailChannel, SMSChannel, VoiceChannel
from agent.reminders.store import Reminder, ReminderStore
from config.settings import REMINDER_POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, store: ReminderStore | None = None, channels: dict | None = None):
        self.store = store or ReminderStore()
        # Injectable so tests (and any future channel additions) don't
        # need real Twilio/SMTP credentials.
        self.channels = channels or {
            "sms": SMSChannel(),
            "voice": VoiceChannel(),
            "email": EmailChannel(),
        }

    def tick(self) -> list[dict]:
        """Runs one poll cycle: reclaim stale claims, then send every
        due reminder. Returns a list of {reminder_id, ok, error} so
        callers (tests, a future status/analytics epic) can inspect
        what happened without re-querying the store."""
        self.store.reclaim_stale_sending()
        results = []
        for reminder in self.store.list_due():
            results.append(self._send_one(reminder))
        return results

    def _send_one(self, reminder: Reminder) -> dict:
        if not self.store.claim(reminder.id):
            # Another tick/process claimed it first — not an error,
            # just means we lost the race and should skip it.
            return {"reminder_id": reminder.id, "ok": False, "skipped": True}

        channel = self.channels.get(reminder.contact_channel)
        if channel is None:
            self.store.mark_failed(reminder.id, f"no channel registered for {reminder.contact_channel!r}")
            return {"reminder_id": reminder.id, "ok": False, "error": "unknown channel"}

        kwargs = {"subject": reminder.subject} if reminder.contact_channel == "email" else {}
        result = channel.send(reminder.contact_address, reminder.message, **kwargs)

        if result.ok:
            self.store.mark_sent(reminder.id, result.provider_id)
            try:
                self.store.schedule_next_occurrence(reminder)
            except ValueError as exc:
                logger.error("Failed to schedule next occurrence for %s: %s", reminder.id, exc)
            return {"reminder_id": reminder.id, "ok": True}

        self.store.mark_failed(reminder.id, result.error or "unknown delivery error")
        return {"reminder_id": reminder.id, "ok": False, "error": result.error}

    def run_forever(self, poll_interval: int | None = None) -> None:
        """The actual long-running process (PROJ-423's "runs
        continuously"). Intended to be run as its own OS process
        (systemd/launchd unit, or a container entrypoint) alongside the
        FastAPI web app — not inside a request handler."""
        interval = poll_interval or REMINDER_POLL_INTERVAL_SECONDS
        logger.info("Reminder scheduler starting, polling every %ss", interval)
        while True:
            try:
                results = self.tick()
                sent = sum(1 for r in results if r.get("ok"))
                if results:
                    logger.info("Tick: %d due, %d sent", len(results), sent)
            except Exception:
                # A bug in one tick must never kill the process — the
                # next tick tries again in `interval` seconds.
                logger.exception("Scheduler tick failed")
            time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ReminderScheduler().run_forever()
