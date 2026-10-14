# tests/test_web_reminder_actions.py — PROJ-479
#
# Recurrence, pause, resume, cancel and reschedule for reminders created in
# the dashboard (app/web/reminders.py), through both the service functions and
# the HTTP routes the form and list call, and the bridge continuing a series.
from datetime import timedelta

import pytest

from agent.delivery.base import DeliveryResult


class _FakeChannel:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    def send(self, to, message, **kwargs):
        self.sent.append((to, message))
        return DeliveryResult(ok=self.ok, channel="fake", to=to, error=None if self.ok else "boom")


@pytest.fixture
def web(tmp_path):
    from app.web import store
    from auth import db as auth_db, tenancy

    auth_db.DB_PATH = str(tmp_path / "auth_users.db")
    auth_db.init_db()
    tenancy.init_tenancy()
    for name in ("reminders", "consent_events"):
        store.set_table(name, store.JsonTable(tmp_path / f"{name}.json", name))
    yield
    for name in ("reminders", "consent_events"):
        store.set_table(name, None)


@pytest.fixture
def client(web):
    from fastapi.testclient import TestClient

    from app.web.main import app

    return TestClient(app)


def _contact():
    from auth import tenancy

    return tenancy.create_contact(1, "+15551234567", "Test", consent_state="opted_in",
                                  preferred_channel="sms")


def _future(**kw):
    from app.web import reminders

    return (reminders._now() + timedelta(**kw)).isoformat()


def _create(recurrence=None, **kw):
    from app.web import reminders

    payload = {"contact_id": _contact(), "message": "Hello", "send_at": _future(hours=2)}
    if recurrence is not None:
        payload["recurrence"] = recurrence
    payload.update(kw)
    return reminders.create_reminder(payload)


# ── Recurrence validation and maths ──────────────────────────
@pytest.mark.parametrize("rec,expected", [
    (None, None),
    ({"freq": "none"}, None),
    ({"freq": "daily"}, {"freq": "daily"}),
    ({"freq": "weekly"}, {"freq": "weekly"}),
    ({"freq": "custom", "interval_days": "3"}, {"freq": "custom", "interval_days": 3}),
    ({"freq": "daily", "tz": "Australia/Sydney"}, {"freq": "daily", "tz": "Australia/Sydney"}),
])
def test_create_stores_normalised_recurrence(web, rec, expected):
    assert _create(rec)["recurrence"] == expected


@pytest.mark.parametrize("rec", [
    {"freq": "hourly"},
    {"freq": "custom"},
    {"freq": "custom", "interval_days": 0},
    {"freq": "custom", "interval_days": 400},
    {"freq": "daily", "tz": "Mars/Olympus"},
    "daily",
])
def test_bad_recurrence_is_a_field_error(web, rec):
    from app.web import reminders

    with pytest.raises(reminders.ValidationError) as exc:
        _create(rec)
    assert "recurrence" in exc.value.errors


def test_next_occurrence_keeps_local_time_across_dst():
    from app.web.reminders import next_occurrence

    # Sydney leaves daylight saving on 2026-04-05: 9am AEDT (+11) -> 9am AEST (+10).
    nxt = next_occurrence("2026-04-04T09:00:00+11:00", {"freq": "daily", "tz": "Australia/Sydney"})
    assert nxt == "2026-04-05T09:00:00+10:00"


def test_next_occurrence_custom_and_weekly():
    from app.web.reminders import next_occurrence

    base = "2026-07-01T09:00:00+10:00"
    tz = "Australia/Sydney"
    assert next_occurrence(base, {"freq": "weekly", "tz": tz}).startswith("2026-07-08T09:00")
    assert next_occurrence(base, {"freq": "custom", "interval_days": 3, "tz": tz}).startswith("2026-07-04T09:00")


# ── Transitions ──────────────────────────────────────────────
def test_pause_resume_cancel_cycle(web):
    from app.web import reminders

    r = _create()
    assert reminders.pause_reminder(r["id"])["status"] == "paused"
    assert reminders.resume_reminder(r["id"])["status"] == "scheduled"
    assert reminders.cancel_reminder(r["id"])["status"] == "cancelled"
    # Cancelled is history: nothing else applies.
    for action in (reminders.pause_reminder, reminders.resume_reminder, reminders.cancel_reminder):
        with pytest.raises(reminders.TransitionError):
            action(r["id"])
    with pytest.raises(reminders.TransitionError):
        reminders.update_reminder(r["id"], {"message": "changed"})


def test_paused_reminder_is_not_sent_by_bridge(web):
    from agent.reminders.web_bridge import WebReminderBridge
    from app.web import reminders

    r = _create()
    reminders.pause_reminder(r["id"])
    reminders.reminders_table().update(r["id"], {"send_at": _future(minutes=-1)})
    sms = _FakeChannel()
    assert WebReminderBridge(channels={"sms": sms}).tick() == []
    assert sms.sent == []


def test_reschedule_paused_keeps_it_paused(web):
    from app.web import reminders

    r = _create()
    reminders.pause_reminder(r["id"])
    when = _future(days=3)
    out = reminders.reschedule_reminder(r["id"], when)
    assert out["status"] == "paused"
    assert reminders.parse_dt(out["send_at"]) == reminders.parse_dt(when)


def test_reschedule_into_the_past_is_rejected(web):
    from app.web import reminders

    r = _create()
    with pytest.raises(reminders.ValidationError) as exc:
        reminders.reschedule_reminder(r["id"], _future(hours=-1))
    assert "send_at" in exc.value.errors


def test_resume_overdue_one_off_asks_for_reschedule(web):
    from app.web import reminders

    r = _create()
    reminders.pause_reminder(r["id"])
    reminders.reminders_table().update(r["id"], {"send_at": _future(hours=-3)})
    with pytest.raises(reminders.ValidationError) as exc:
        reminders.resume_reminder(r["id"])
    assert "send_at" in exc.value.errors
    assert reminders.get_reminder(r["id"])["status"] == "paused"


def test_resume_overdue_recurring_skips_to_next_future_time(web):
    from app.web import reminders

    r = _create({"freq": "daily"})
    reminders.pause_reminder(r["id"])
    reminders.reminders_table().update(r["id"], {"send_at": _future(days=-3, hours=1)})
    out = reminders.resume_reminder(r["id"])
    assert out["status"] == "scheduled"
    assert reminders._now() < reminders.parse_dt(out["send_at"]) <= reminders._now() + timedelta(days=1)


# ── Bridge continues a series ────────────────────────────────
@pytest.mark.parametrize("ok", [True, False])
def test_bridge_schedules_next_occurrence_whatever_the_outcome(web, ok):
    from agent.reminders.web_bridge import WebReminderBridge
    from app.web import reminders

    r = _create({"freq": "weekly"})
    reminders.reminders_table().update(r["id"], {"send_at": _future(minutes=-1)})
    WebReminderBridge(channels={"sms": _FakeChannel(ok=ok)}).tick()

    rows = reminders.list_reminders()
    assert len(rows) == 2
    first, nxt = (next(x for x in rows if x["id"] == r["id"]),
                  next(x for x in rows if x["id"] != r["id"]))
    assert first["status"] == ("sent" if ok else "failed")
    assert nxt["status"] == "scheduled"
    assert nxt["recurrence"] == {"freq": "weekly"}
    assert nxt["series_of"] == r["id"]
    gap = reminders.parse_dt(nxt["send_at"]) - reminders.parse_dt(first["send_at"])
    assert timedelta(days=6, hours=22) < gap < timedelta(days=7, hours=2)


def test_bridge_does_not_repeat_one_off(web):
    from agent.reminders.web_bridge import WebReminderBridge
    from app.web import reminders

    r = _create()
    reminders.reminders_table().update(r["id"], {"send_at": _future(minutes=-1)})
    WebReminderBridge(channels={"sms": _FakeChannel()}).tick()
    assert len(reminders.list_reminders()) == 1


# ── HTTP routes the form and list call ───────────────────────
def test_routes_create_recurring_then_pause_resume_reschedule_cancel(client):
    cid = _contact()
    r = client.post("/api/reminders", json={
        "contact_id": cid, "message": "Weekly check-in", "send_at": _future(hours=5),
        "recurrence": {"freq": "custom", "interval_days": 2, "tz": "Australia/Sydney"},
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["recurrence"]["interval_days"] == 2

    assert client.post(f"/api/reminders/{rid}/pause").json()["status"] == "paused"
    assert client.post(f"/api/reminders/{rid}/pause").status_code == 409
    assert client.post(f"/api/reminders/{rid}/reschedule",
                       json={"send_at": _future(days=2)}).json()["status"] == "paused"
    assert client.post(f"/api/reminders/{rid}/reschedule",
                       json={"send_at": "nonsense"}).status_code == 422
    assert client.post(f"/api/reminders/{rid}/resume").json()["status"] == "scheduled"
    assert client.patch(f"/api/reminders/{rid}", json={"recurrence": None}).json()["recurrence"] is None
    assert client.post(f"/api/reminders/{rid}/cancel").json()["status"] == "cancelled"
    assert client.patch(f"/api/reminders/{rid}", json={"message": "x"}).status_code == 409
    assert client.get("/api/reminders?status=cancelled").json()["total"] == 1


def test_routes_404_for_missing_reminder(client):
    for action in ("pause", "resume", "cancel"):
        assert client.post(f"/api/reminders/9999/{action}").status_code == 404
    assert client.post("/api/reminders/9999/reschedule", json={"send_at": _future(days=1)}).status_code == 404


def test_form_and_list_render_the_new_controls(client):
    form = client.get("/reminders/new").text
    for needle in ('id="freq"', 'value="weekly"', 'id="interval_days"', 'id="pause"',
                   'id="resume"', 'id="cancelrem"', "toISOString"):
        assert needle in form, needle
    page = client.get("/reminders").text
    for needle in ('value="paused"', 'value="cancelled"', 'data-act="reschedule"', "repeatLabel"):
        assert needle in page, needle
