from datetime import datetime, timedelta, timezone

import pytest

from agent.delivery.base import DeliveryResult
from agent.reminders.scheduler import ReminderScheduler
from agent.reminders.store import ReminderStore
from app.web import message_templates


class CaptureChannel:
    def __init__(self):
        self.sent = []

    def send(self, to, message, **kwargs):
        self.sent.append((to, message, kwargs))
        return DeliveryResult(
            ok=True, channel="test", to=to, provider_id="TEST123"
        )


@pytest.fixture
def store(tmp_path):
    return ReminderStore(db_path=str(tmp_path / "proj485.db"))


def past_time():
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


@pytest.mark.parametrize(
    ("channel", "address"),
    [
        ("sms", "+15551234567"),
        ("email", "jane@example.com"),
        ("voice", "+15551234567"),
    ],
)
def test_scheduler_personalises_all_delivery_channels(
    store, monkeypatch, channel, address
):
    from auth import tenancy

    contact = {"name": "Jane Doe", "email": "jane@example.com"}
    monkeypatch.setattr(
        tenancy, "get_contact_by_phone", lambda org_id, phone: contact
    )
    monkeypatch.setattr(
        tenancy, "get_contact_by_email", lambda org_id, email: contact
    )
    monkeypatch.setattr(
        message_templates, "org_name", lambda org_id: "Bright Dental"
    )

    fake = CaptureChannel()
    scheduler = ReminderScheduler(store=store, channels={channel: fake})

    reminder = store.create(
        contact_channel=channel,
        contact_address=address,
        message=(
            "Hi {name} ({first_name}), your appointment is "
            "{appointment_date}. Regards, {org_name}."
        ),
        scheduled_at_utc=past_time(),
        contact_timezone="UTC",
        org_id=17,
        appointment_date="2026-11-02T10:00:00",
    )

    result = scheduler.tick()

    assert result[0]["ok"] is True
    assert store.get(reminder.id).status == "sent"
    assert fake.sent[0][1] == (
        "Hi Jane Doe (Jane), your appointment is Monday 2 November. "
        "Regards, Bright Dental."
    )


def test_missing_fields_use_fallbacks_not_raw_placeholders(
    store, monkeypatch
):
    from auth import tenancy

    monkeypatch.setattr(
        tenancy, "get_contact_by_phone", lambda org_id, phone: None
    )
    monkeypatch.setattr(
        tenancy, "get_contact_by_email", lambda org_id, email: None
    )
    monkeypatch.setattr(message_templates, "org_name", lambda org_id: None)

    fake = CaptureChannel()
    scheduler = ReminderScheduler(store=store, channels={"sms": fake})

    store.create(
        contact_channel="sms",
        contact_address="+15551234567",
        message="Hi {name}, {first_name}, {appointment_date}, {org_name}, {org}.",
        scheduled_at_utc=past_time(),
        contact_timezone="UTC",
    )

    result = scheduler.tick()

    assert result[0]["ok"] is True
    delivered = fake.sent[0][1]
    assert "{name}" not in delivered
    assert "{first_name}" not in delivered
    assert "{appointment_date}" not in delivered
    assert "{org_name}" not in delivered
    assert "{org}" not in delivered
    assert "there" in delivered
    assert "us" in delivered


def test_double_braces_escape_merge_fields():
    rendered = message_templates.render(
        "Literal {{name}}; personalised {name}.",
        {"name": "Jane"},
    )
    assert rendered == "Literal {name}; personalised Jane."


def test_new_aliases_are_supported():
    values = message_templates.merge_values(
        {"name": "Jane Doe"},
        datetime(2026, 11, 2, 10, 0),
        "Bright Dental",
        appointment_date=datetime(2026, 11, 3, 11, 0),
    )
    rendered = message_templates.render(
        "{name}|{first_name}|{appointment_date}|{org_name}",
        values,
    )
    assert rendered == "Jane Doe|Jane|Tuesday 3 November|Bright Dental"

def test_missing_appointment_date_does_not_use_send_date():
    values = message_templates.merge_values(
        {"name": "Jane Doe"},
        datetime(2026, 11, 2, 10, 0),
        "Bright Dental",
        tz_name="UTC",
    )
    assert values["date"] == "Monday 2 November"
    assert values["appointment_date"] == ""
