# app/web_ui/analytics_routes.py
# ──────────────────────────────────────────────────────────────
# Analytics Aggregation & Reporting API
# PROJ-398 (Epic: Analytics)
# PROJ-435 (Analytics aggregation: delivery rate, response rate)
# PROJ-436 (Analytics charts backend endpoints)
# ──────────────────────────────────────────────────────────────

import os
import sys
import uuid
import random
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Query
from app.web_ui.activity_db import (
    get_delivery_analytics,
    log_delivery_event,
    update_delivery_status,
    log_activity,
)

router = APIRouter(prefix="/analytics", tags=["Analytics & Reporting"])


@router.get("/summary")
async def get_analytics_summary():
    """
    Get aggregated analytics metrics:
    - Delivery rate %
    - Response rate %
    - Failure & bounce counts
    - Channel breakdown
    PROJ-435
    """
    return get_delivery_analytics()


@router.get("/trends")
async def get_analytics_trends():
    """Get time-series delivery and response trends for dashboard charts (PROJ-436)."""
    analytics = get_delivery_analytics()
    return {"daily_trends": analytics.get("daily_trends", [])}


@router.get("/channels")
async def get_channel_metrics():
    """Get performance metrics broken down by delivery channel (PROJ-435)."""
    analytics = get_delivery_analytics()
    return {"channels": analytics.get("channels", {})}


@router.get("/failures")
async def get_failure_breakdown():
    """Get top failure and bounce error breakdown (PROJ-435)."""
    analytics = get_delivery_analytics()
    return {"failure_reasons": analytics.get("failure_reasons", {})}


@router.post("/seed-demo-data")
async def seed_demo_analytics_data(count: int = Query(default=35, ge=5, le=100)):
    """
    Seed realistic sample delivery records and responses for testing and demonstration.
    PROJ-435 / PROJ-436
    """
    now = datetime.now(timezone.utc)
    channels = ["sms", "sms", "email", "email", "voice"]
    reminder_types = ["appointment", "appointment", "followup", "alert", "general"]
    statuses = ["delivered", "delivered", "delivered", "delivered", "sent", "failed", "bounced"]
    
    phone_prefixes = ["+61412", "+61435", "+61488", "+61421", "+61450"]
    domains = ["federation.edu.au", "student.federation.edu.au", "gmail.com", "outlook.com"]

    seeded = 0
    for i in range(count):
        ch = random.choice(channels)
        rtype = random.choice(reminder_types)
        status = random.choice(statuses)
        day_offset = random.randint(0, 6)
        item_time = (now - timedelta(days=day_offset, hours=random.randint(1, 23))).isoformat()

        if ch == "email":
            recipient = f"student{random.randint(100, 999)}@{random.choice(domains)}"
            msg_id = f"EM-{uuid.uuid4().hex[:10].upper()}"
        elif ch == "voice":
            recipient = f"{random.choice(phone_prefixes)}{random.randint(100000, 999999)}"
            msg_id = f"CA{uuid.uuid4().hex[:12].lower()}"
        else:
            recipient = f"{random.choice(phone_prefixes)}{random.randint(100000, 999999)}"
            msg_id = f"SM{uuid.uuid4().hex[:12].lower()}"

        err_code = ""
        err_msg = ""
        if status == "failed":
            err_code = "30008" if ch == "sms" else "554"
            err_msg = "Unknown error delivering to carrier" if ch == "sms" else "SMTP relay error"
        elif status == "bounced":
            err_code = "550"
            err_msg = "5.1.1 Recipient mailbox unknown"
            status = "bounced"

        log_delivery_event(
            message_id=msg_id,
            recipient=recipient,
            channel=ch,
            reminder_type=rtype,
            status=status,
            metadata={"source": "demo_seed", "seeded_at": item_time},
        )

        delivered_time = (now - timedelta(days=day_offset, hours=random.randint(0, 10))).isoformat() if status == "delivered" else None
        update_delivery_status(
            message_id=msg_id,
            status=status,
            error_code=err_code,
            error_message=err_msg,
            delivered_at=delivered_time,
        )

        seeded += 1

    return {"status": "ok", "seeded_records": seeded, "analytics": get_delivery_analytics()}
