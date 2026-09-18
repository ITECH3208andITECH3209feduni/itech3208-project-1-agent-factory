# tests/test_reminders_store.py — agent/reminders/store.py
# (PROJ-422 store, PROJ-424 timezone, PROJ-425 recurrence, PROJ-426 edit/pause/cancel)
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from agent.reminders.store import ReminderStore, local_to_utc_iso


@pytest.fixture
def store(tmp_path):
    return ReminderStore(db_path=str(tmp_path / "reminders.db"))


def _future_utc(hours=1):
    return (datetime.now(dt_timezone.utc) + timedelta(hours=hours)).isoformat()


def _past_utc(hours=1):
    return (datetime.now(dt_timezone.utc) - timedelta(hours=hours)).isoformat()


# ── Store basics (PROJ-422) ──────────────────────────────────────


def test_create_and_get(store):
    r = store.create(
        contact_channel="sms",
        contact_address="+15551234567",
        message="Your appointment is tomorrow.",
        scheduled_at_utc=_future_utc(),
        contact_timezone="Australia/Melbourne",
    )
    assert r.status == "pending"
    fetched = store.get(r.id)
    assert fetched.message == "Your appointment is tomorrow."


def test_create_rejects_invalid_channel(store):
    with pytest.raises(ValueError):
        store.create(
            contact_channel="carrier_pigeon",
            contact_address="loft-1",
            message="hi",
            scheduled_at_utc=_future_utc(),
            contact_timezone="UTC",
        )


def test_create_rejects_invalid_timezone(store):
    with pytest.raises(Exception):
        store.create(
            contact_channel="sms",
            contact_address="+1",
            message="hi",
            scheduled_at_utc=_future_utc(),
            contact_timezone="Not/A_Real_Zone",
        )


def test_list_due_only_returns_past_pending(store):
    due = store.create(
        contact_channel="sms", contact_address="+1", message="due",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    not_due = store.create(
        contact_channel="sms", contact_address="+1", message="not due",
        scheduled_at_utc=_future_utc(), contact_timezone="UTC",
    )
    due_ids = {r.id for r in store.list_due()}
    assert due.id in due_ids
    assert not_due.id not in due_ids


# ── Timezone-correct scheduling (PROJ-424) ───────────────────────


def test_local_to_utc_conversion():
    # 9am AEST (UTC+10, no DST in Melbourne in June) -> 23:00 UTC previous day
    utc_iso = local_to_utc_iso("2026-06-15T09:00:00", "Australia/Melbourne")
    dt = datetime.fromisoformat(utc_iso)
    assert dt.hour == 23
    assert dt.date().isoformat() == "2026-06-14"


def test_local_to_utc_handles_different_zones_differently():
    melbourne = local_to_utc_iso("2026-06-15T09:00:00", "Australia/Melbourne")
    la = local_to_utc_iso("2026-06-15T09:00:00", "America/Los_Angeles")
    assert melbourne != la


# ── Claim (PROJ-423 support: never double-send) ──────────────────


def test_claim_succeeds_once(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    assert store.claim(r.id) is True
    assert store.claim(r.id) is False  # already 'sending', second claim loses the race
    assert store.get(r.id).status == "sending"


def test_mark_sent_and_mark_failed(store):
    r1 = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    store.claim(r1.id)
    store.mark_sent(r1.id, provider_id="SM123")
    assert store.get(r1.id).status == "sent"
    assert store.get(r1.id).provider_id == "SM123"

    r2 = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    store.claim(r2.id)
    store.mark_failed(r2.id, "invalid number")
    assert store.get(r2.id).status == "failed"
    assert store.get(r2.id).last_error == "invalid number"


def test_reclaim_stale_sending_bounces_back_to_pending(store, monkeypatch):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    store.claim(r.id)
    assert store.get(r.id).status == "sending"

    # Simulate the claim being old by directly backdating updated_at.
    old_ts = (datetime.now(dt_timezone.utc) - timedelta(minutes=30)).isoformat()
    store._conn.execute("UPDATE reminders SET updated_at = ? WHERE id = ?", (old_ts, r.id))
    store._conn.commit()

    reclaimed = store.reclaim_stale_sending(older_than_minutes=10)
    assert reclaimed == 1
    assert store.get(r.id).status == "pending"


def test_reclaim_stale_sending_leaves_fresh_claims_alone(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    store.claim(r.id)
    assert store.reclaim_stale_sending(older_than_minutes=10) == 0
    assert store.get(r.id).status == "sending"


# ── Recurrence (PROJ-425) ────────────────────────────────────────


def test_recurring_daily_schedules_next_occurrence_24h_later(store):
    scheduled = _past_utc(hours=0)  # roughly "now"
    r = store.create(
        contact_channel="sms", contact_address="+1", message="daily check-in",
        scheduled_at_utc=scheduled, contact_timezone="UTC",
        recurrence={"freq": "daily"},
    )
    next_r = store.schedule_next_occurrence(r)
    assert next_r is not None
    delta = datetime.fromisoformat(next_r.scheduled_at_utc) - datetime.fromisoformat(r.scheduled_at_utc)
    assert delta == timedelta(days=1)
    assert next_r.recurrence == {"freq": "daily"}
    assert next_r.status == "pending"


def test_recurring_weekly_schedules_next_occurrence_7d_later(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="weekly check-in",
        scheduled_at_utc=_past_utc(hours=0), contact_timezone="UTC",
        recurrence={"freq": "weekly"},
    )
    next_r = store.schedule_next_occurrence(r)
    delta = datetime.fromisoformat(next_r.scheduled_at_utc) - datetime.fromisoformat(r.scheduled_at_utc)
    assert delta == timedelta(weeks=1)


def test_recurring_custom_interval(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="every 3 days",
        scheduled_at_utc=_past_utc(hours=0), contact_timezone="UTC",
        recurrence={"freq": "custom", "interval_days": 3},
    )
    next_r = store.schedule_next_occurrence(r)
    delta = datetime.fromisoformat(next_r.scheduled_at_utc) - datetime.fromisoformat(r.scheduled_at_utc)
    assert delta == timedelta(days=3)


def test_non_recurring_has_no_next_occurrence(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="one-off",
        scheduled_at_utc=_past_utc(hours=0), contact_timezone="UTC",
    )
    assert store.schedule_next_occurrence(r) is None


def test_recurring_daily_stays_at_same_local_wall_clock_time_across_dst():
    """The core DST correctness claim (PROJ-424): a daily 9am reminder
    in a DST-observing zone should still read 9am local the next day,
    even though the UTC offset for that zone changes across the
    transition. Sydney springs forward on 2026-10-04 (2am -> 3am)."""
    from agent.reminders.store import _next_occurrence_utc

    before_dst = local_to_utc_iso("2026-10-03T09:00:00", "Australia/Sydney")
    next_utc = _next_occurrence_utc(before_dst, "Australia/Sydney", {"freq": "daily"})

    from zoneinfo import ZoneInfo

    next_local = datetime.fromisoformat(next_utc).astimezone(ZoneInfo("Australia/Sydney"))
    assert next_local.hour == 9
    assert next_local.date().isoformat() == "2026-10-04"


# ── Edit / pause / cancel / reschedule (PROJ-426) ────────────────


def test_update_message_on_pending(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="old",
        scheduled_at_utc=_future_utc(), contact_timezone="UTC",
    )
    assert store.update_message(r.id, "new message") is True
    assert store.get(r.id).message == "new message"


def test_update_message_fails_once_sent(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="old",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    store.claim(r.id)
    store.mark_sent(r.id, None)
    assert store.update_message(r.id, "too late") is False
    assert store.get(r.id).message == "old"


def test_pause_and_resume(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_future_utc(), contact_timezone="UTC",
    )
    assert store.pause(r.id) is True
    assert store.get(r.id).status == "paused"
    # A paused reminder should never show up as due.
    assert r.id not in {x.id for x in store.list_due(now_utc=_future_utc(hours=100))}

    assert store.resume(r.id) is True
    assert store.get(r.id).status == "pending"


def test_reschedule(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_future_utc(hours=1), contact_timezone="UTC",
    )
    new_time = _future_utc(hours=5)
    assert store.reschedule(r.id, new_time) is True
    assert store.get(r.id).scheduled_at_utc == new_time


def test_cancel(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_future_utc(), contact_timezone="UTC",
    )
    assert store.cancel(r.id) is True
    assert store.get(r.id).status == "cancelled"
    assert store.cancel(r.id) is False  # already cancelled


def test_cancel_fails_once_sent(store):
    r = store.create(
        contact_channel="sms", contact_address="+1", message="hi",
        scheduled_at_utc=_past_utc(), contact_timezone="UTC",
    )
    store.claim(r.id)
    store.mark_sent(r.id, None)
    assert store.cancel(r.id) is False
