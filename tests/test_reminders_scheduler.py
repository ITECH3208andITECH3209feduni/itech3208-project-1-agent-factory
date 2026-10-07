# tests/test_reminders_scheduler.py — agent/reminders/scheduler.py (PROJ-423)
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from agent.delivery.base import DeliveryResult
from agent.reminders.scheduler import ReminderScheduler
from agent.reminders.store import ReminderStore


class _FakeChannel:
    def __init__(self, ok=True, error=None, provider_id="PID123"):
        self.ok = ok
        self.error = error
        self.provider_id = provider_id
        self.sent_to = []

    def send(self, to, message, **kwargs):
        self.sent_to.append((to, message))
        return DeliveryResult(
            ok=self.ok, channel="sms", to=to, provider_id=self.provider_id, error=self.error
        )


@pytest.fixture
def store(tmp_path):
    return ReminderStore(db_path=str(tmp_path / "reminders.db"))


def _past_utc(hours=1):
    return (datetime.now(dt_timezone.utc) - timedelta(hours=hours)).isoformat()


def test_tick_sends_due_reminder_and_marks_sent(store):
    fake_sms = _FakeChannel(ok=True)
    scheduler = ReminderScheduler(store=store, channels={"sms": fake_sms, "voice": _FakeChannel(), "email": _FakeChannel()})

    r = store.create(
        contact_channel="sms", contact_address="+15551234567", message="Your appointment is tomorrow.",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )

    results = scheduler.tick()
    assert results == [{"reminder_id": r.id, "ok": True}]
    assert store.get(r.id).status == "sent"
    assert fake_sms.sent_to == [("+15551234567", "Your appointment is tomorrow.")]


def test_tick_marks_failed_on_delivery_error(store):
    fake_sms = _FakeChannel(ok=False, error="invalid number")
    scheduler = ReminderScheduler(store=store, channels={"sms": fake_sms})

    r = store.create(
        contact_channel="sms", contact_address="+1bad", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )

    results = scheduler.tick()
    assert results[0]["ok"] is False
    assert store.get(r.id).status == "failed"
    assert store.get(r.id).last_error == "invalid number"


def test_tick_ignores_reminders_not_yet_due(store):
    scheduler = ReminderScheduler(store=store, channels={"sms": _FakeChannel()})
    future = (datetime.now(dt_timezone.utc) + timedelta(hours=1)).isoformat()
    store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=future, contact_timezone="UTC",
    )
    assert scheduler.tick() == []


def test_tick_schedules_next_occurrence_for_recurring(store):
    scheduler = ReminderScheduler(store=store, channels={"sms": _FakeChannel(ok=True)})
    store.create(
        contact_channel="sms", contact_address="+1", message="daily",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
        recurrence={"freq": "daily"},
    )

    scheduler.tick()

    # One sent + one freshly-created pending for tomorrow.
    all_ids = [r.id for r in store.list_due(now_utc=(datetime.now(dt_timezone.utc) + timedelta(days=2)).isoformat())]
    assert len(all_ids) == 1  # the newly-created next occurrence is pending


def test_unknown_channel_marks_failed_without_crashing(store):
    scheduler = ReminderScheduler(store=store, channels={})
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    results = scheduler.tick()
    assert results[0]["ok"] is False
    assert store.get(r.id).status == "failed"


def test_claimed_reminder_is_not_sent_twice_in_same_tick(store):
    """Simulates the race claim() protects against: if a reminder is
    already 'sending' when list_due() would have picked it up, the
    scheduler must not attempt to send it again."""
    fake_sms = _FakeChannel(ok=True)
    scheduler = ReminderScheduler(store=store, channels={"sms": fake_sms})
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    store.claim(r.id)  # pretend another process already claimed it

    results = scheduler._send_one(r)
    assert results["skipped"] is True
    assert fake_sms.sent_to == []
