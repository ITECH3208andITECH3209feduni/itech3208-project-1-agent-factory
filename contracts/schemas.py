# contracts/schemas.py
# ──────────────────────────────────────────────────────────────
# Published data contracts (PROJ-404)
#
# These are the request/response shapes for org, contact and
# reminder data. Routes import from here rather than defining
# their own models, so the wire format stays consistent and
# there's one place to change it.
#
# Note: the ticket names "reminder" but no other ticket in this
# batch defines reminder behaviour and there is no reminders
# table. The contract below is the minimal shape implied by the
# consent epic (a scheduled SMS to a contact); it is published
# but not yet consumed by any route.
# ──────────────────────────────────────────────────────────────

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Shared ─────────────────────────────────────────────────────
class ConsentState(str, Enum):
    """Consent lifecycle for a contact (PROJ-412)."""
    UNKNOWN = "unknown"      # never asked
    PENDING = "pending"      # invited, no reply yet
    OPTED_IN = "opted_in"    # explicit yes
    OPTED_OUT = "opted_out"  # replied STOP or equivalent


def normalise_phone(value: str) -> str:
    """
    Store phone numbers in a single canonical form so the same
    person can't exist twice under different formatting.
    Digits and a leading + only.
    """
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    if not cleaned:
        raise ValueError("phone number contains no digits")
    if not cleaned.startswith("+"):
        # Australian local format -> E.164
        if cleaned.startswith("0"):
            cleaned = "+61" + cleaned[1:]
        else:
            cleaned = "+" + cleaned
    return cleaned


# ── Organisation ───────────────────────────────────────────────
class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact_email: EmailStr | None = None
    timezone: str = Field(default="Australia/Melbourne", max_length=64)


class OrgUpdate(BaseModel):
    """All fields optional — only what's supplied gets changed (PROJ-409)."""
    name: str | None = Field(default=None, min_length=2, max_length=120)
    contact_email: EmailStr | None = None
    timezone: str | None = Field(default=None, max_length=64)


class OrgOut(BaseModel):
    id: int
    name: str
    contact_email: str | None = None
    timezone: str
    is_active: bool
    created_at: str


# ── Registration (PROJ-406) ────────────────────────────────────
class OrgRegistration(BaseModel):
    """Creates an organisation and its first (owner) user together."""
    org_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    timezone: str = Field(default="Australia/Melbourne", max_length=64)


class RegistrationOut(BaseModel):
    org: OrgOut
    user_id: int
    role: str


# ── Contact ────────────────────────────────────────────────────
class ContactCreate(BaseModel):
    phone_number: str = Field(min_length=6, max_length=20)
    name: str | None = Field(default=None, max_length=120)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalise_phone(v)


class ContactOut(BaseModel):
    id: int
    org_id: int
    phone_number: str
    name: str | None = None
    consent_state: ConsentState = ConsentState.UNKNOWN
    created_at: str


# ── Consent (PROJ-412, PROJ-413) ───────────────────────────────
class ConsentEvent(BaseModel):
    """One entry in the consent audit trail. Append-only."""
    contact_id: int
    org_id: int
    old_state: ConsentState | None = None
    new_state: ConsentState
    source: str = Field(max_length=40)   # "sms_stop", "web_form", "import", "manual"
    detail: str | None = Field(default=None, max_length=500)
    occurred_at: datetime


# ── Reminder ───────────────────────────────────────────────────
class ReminderCreate(BaseModel):
    """
    A scheduled outbound message to a contact. Published as a
    contract per PROJ-404; no route consumes it yet.
    """
    contact_id: int
    message: str = Field(min_length=1, max_length=1600)
    send_at: datetime


class ReminderOut(BaseModel):
    id: int
    org_id: int
    contact_id: int
    message: str
    send_at: datetime
    sent_at: datetime | None = None
    status: str  # "scheduled", "sent", "blocked", "failed"