# app/web_ui/delivery_routes.py
# ──────────────────────────────────────────────────────────────
# Delivery Status & History, Twilio callback and Email Bounce API
# PROJ-397 (Epic: Delivery Status & History)
# PROJ-432 (Twilio status callback webhook)
# PROJ-433 (Email bounce / failure handling)
# PROJ-434 (Delivery history view per reminder)
# ──────────────────────────────────────────────────────────────

import os
import sys
import uuid
from typing import Optional
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.web_ui.activity_db import (
    add_email_suppression,
    get_delivery_analytics,
    get_delivery_by_id,
    get_delivery_history,
    get_email_suppressions,
    is_email_suppressed,
    log_activity,
    log_delivery_event,
    retry_delivery_message,
    update_delivery_status,
)

router = APIRouter(prefix="/delivery", tags=["Delivery Status & History"])


# ── Pydantic Request / Response Models ─────────────────────────

class SendReminderRequest(BaseModel):
    recipient: str = Field(..., description="Phone number or email address")
    channel: str = Field(default="sms", description="'sms', 'email', or 'voice'")
    reminder_type: str = Field(default="appointment", description="'appointment', 'followup', 'alert', 'general'")
    message: str = Field(default="", description="Reminder message body")
    metadata: Optional[dict] = Field(default_factory=dict)


class EmailBounceWebhookPayload(BaseModel):
    email: Optional[str] = None
    recipient: Optional[str] = None
    message_id: Optional[str] = None
    bounce_type: str = Field(default="hard_bounce", description="'hard_bounce', 'soft_bounce', 'complaint', 'undeliverable'")
    reason: Optional[str] = "Recipient address rejected or mailbox unavailable"
    diagnostic_code: Optional[str] = "550 5.1.1 User unknown"
    timestamp: Optional[str] = None


# ── PROJ-434: Delivery History Endpoints ───────────────────────

@router.get("/history")
async def list_delivery_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None, description="Filter by status: queued, sent, delivered, failed, bounced, undelivered"),
    channel: Optional[str] = Query(default=None, description="Filter by channel: sms, email, voice"),
    search: Optional[str] = Query(default=None, description="Search recipient, message_id, or error"),
):
    """
    Return paginated delivery history records per reminder.
    PROJ-434
    """
    return get_delivery_history(
        limit=limit,
        offset=offset,
        status=status,
        channel=channel,
        search=search,
    )


@router.get("/history/{delivery_id}")
async def get_delivery_record(delivery_id: str):
    """Fetch single delivery record by numerical ID or message_id (PROJ-434)."""
    record = get_delivery_by_id(delivery_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Delivery record '{delivery_id}' not found.")
    return record


@router.post("/retry/{delivery_id}")
async def retry_delivery(delivery_id: str):
    """
    Retry a failed or bounced delivery message.
    Increments retry count and sets status back to queued (PROJ-434).
    """
    record = get_delivery_by_id(delivery_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Delivery record '{delivery_id}' not found.")

    if record.get("channel") == "email" and is_email_suppressed(record.get("recipient", "")):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry: recipient '{record.get('recipient')}' is currently on the suppression list due to a previous bounce."
        )

    updated = retry_delivery_message(delivery_id)
    log_activity(
        channel=record.get("channel", "sms"),
        caller=record.get("recipient", "unknown"),
        intent="delivery_retry",
        summary=f"Manually retried reminder {record.get('message_id')} (attempt #{updated.get('retry_count', 1)})",
    )
    return {"status": "retrying", "record": updated}


@router.post("/send")
async def send_reminder(payload: SendReminderRequest):
    """
    Trigger or schedule an outbound reminder delivery across SMS, Email, or Voice.
    Validates suppressions for email, logs delivery record, and returns tracking message_id.
    """
    channel = payload.channel.lower().strip()
    recipient = payload.recipient.strip()

    if channel == "email" and is_email_suppressed(recipient):
        raise HTTPException(
            status_code=400,
            detail=f"Recipient email '{recipient}' is suppressed due to previous bounce or spam report."
        )

    msg_id = f"{channel[:2].upper()}-{uuid.uuid4().hex[:12].upper()}"
    meta = payload.metadata or {}
    meta["message"] = payload.message[:500]

    record = log_delivery_event(
        message_id=msg_id,
        recipient=recipient,
        channel=channel,
        reminder_type=payload.reminder_type,
        status="sent",
        metadata=meta,
    )

    log_activity(
        channel=channel,
        caller=recipient,
        intent=f"reminder_{payload.reminder_type}",
        summary=f"Sent {payload.reminder_type} reminder to {recipient} [{msg_id}]",
    )

    return {"status": "sent", "message_id": msg_id, "record": record}


# ── PROJ-433: Email Bounce & Failure Handling ──────────────────

@router.post("/email/bounce")
@router.post("/email/status")
async def handle_email_bounce(request: Request):
    """
    Handle email bounce / failure webhooks from email providers (SendGrid, SES, Mailgun, SMTP).
    Parses bounce payload, updates delivery history to 'bounced' or 'failed', and adds
    hard bounces to suppression list (PROJ-433).
    """
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        # Handle form or raw data
        form = await request.form()
        payload = dict(form)

    # Handle batched event arrays (SendGrid format)
    events = payload if isinstance(payload, list) else [payload]
    processed = []

    for event in events:
        recipient = (
            event.get("email")
            or event.get("recipient")
            or event.get("To")
            or event.get("address")
            or ""
        ).strip().lower()

        msg_id = (
            event.get("message_id")
            or event.get("sg_message_id")
            or event.get("mail_id")
            or event.get("id")
            or ""
        )

        event_type = (event.get("event") or event.get("bounce_type") or event.get("type") or "hard_bounce").lower()
        reason = (
            event.get("reason")
            or event.get("diagnostic_code")
            or event.get("description")
            or "Recipient mailbox unavailable or rejected"
        )
        diag_code = str(event.get("diagnostic_code") or event.get("status_code") or event.get("error_code") or "550")

        is_hard = "hard" in event_type or "reject" in event_type or "complaint" in event_type or "550" in diag_code
        status = "bounced" if ("bounce" in event_type or is_hard) else "failed"

        # Update delivery tracking record if message_id provided
        if msg_id:
            update_delivery_status(
                message_id=msg_id,
                status=status,
                error_code=diag_code,
                error_message=reason,
                extra_metadata={"bounce_type": event_type, "processed_at": datetime.now(timezone.utc).isoformat()},
            )
        elif recipient:
            # Fallback: create delivery log for the bounce
            auto_id = f"EM-BOUNCE-{uuid.uuid4().hex[:8].upper()}"
            log_delivery_event(
                message_id=auto_id,
                recipient=recipient,
                channel="email",
                reminder_type="general",
                status=status,
                metadata={"bounce_type": event_type, "reason": reason, "code": diag_code},
            )
            update_delivery_status(auto_id, status, diag_code, reason)

        # Add to suppressions list on hard bounce / complaint
        if is_hard and recipient:
            add_email_suppression(recipient, f"{event_type}: {reason}")

        log_activity(
            channel="email",
            caller=recipient or "unknown",
            intent="email_bounce",
            summary=f"Email bounce ({event_type}) for {recipient}: {reason[:100]}",
        )

        processed.append({"recipient": recipient, "status": status, "suppressed": is_hard})

    return {"status": "ok", "processed_events": len(processed), "details": processed}


@router.get("/email/suppressions")
async def list_suppressions():
    """List all suppressed email addresses (PROJ-433)."""
    return {"suppressions": get_email_suppressions()}


@router.delete("/email/suppressions/{email}")
async def remove_suppression(email: str):
    """Remove an email address from suppression list (PROJ-433)."""
    from app.web_ui.activity_db import _get_db
    db = _get_db()
    db.execute("DELETE FROM email_suppressions WHERE email = ?", (email.strip().lower(),))
    db.commit()
    return {"status": "removed", "email": email.strip().lower()}
