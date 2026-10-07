# agent/delivery/__init__.py
# ──────────────────────────────────────────────────────────────
# Delivery Channels (PROJ-396) — Dilraj Singh
#
# Adapters that actually send a reminder to a contact over SMS, a
# voice call, or email. Each adapter implements the DeliveryChannel
# interface from base.py so the future scheduler (PROJ-395) can call
# channel.send(...) without caring which transport it's talking to.
# ──────────────────────────────────────────────────────────────

from agent.delivery.base import (
    DeliveryChannel,
    DeliveryResult,
    RetryPolicy,
    send_with_retry,
)
from agent.delivery.sms_channel import SMSChannel
from agent.delivery.voice_channel import VoiceChannel
from agent.delivery.email_channel import EmailChannel

__all__ = [
    "DeliveryChannel",
    "DeliveryResult",
    "RetryPolicy",
    "send_with_retry",
    "SMSChannel",
    "VoiceChannel",
    "EmailChannel",
]
