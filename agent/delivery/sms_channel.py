# agent/delivery/sms_channel.py
# ──────────────────────────────────────────────────────────────
# SMS delivery adapter (PROJ-427) — Dilraj Singh
#
# Outbound reminder SMS via Twilio's REST API. Reuses the same Twilio
# account already configured for the AI Receptionist's inbound webhooks
# (app/web_ui/twilio_routes.py) — nothing new to provision.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

import os

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from agent.delivery.base import DeliveryChannel, DeliveryResult
from config.settings import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER

# Twilio error codes that mean "this will never work, don't retry" —
# https://www.twilio.com/docs/api/errors. Anything else (rate limits,
# transient carrier issues, Twilio-side 5xx) is treated as retriable.
_NON_RETRIABLE_CODES = {
    21211,  # invalid 'To' phone number
    21214,  # 'To' number not reachable
    21610,  # recipient unsubscribed (opted out)
    21408,  # permission to send to this region not enabled
    21606,  # 'From' number not owned by this account
    21608,  # trial account: 'To' is not a verified caller ID
    21612,  # 'From' cannot send to this 'To' (e.g. unsupported carrier or region)
}


def _status_callback_url() -> str | None:
    """Where Twilio should post delivery updates (PROJ-482). Without this the
    /twilio/status-callback route never hears whether a reminder SMS was
    delivered, or why it was not (e.g. 30034, unregistered A2P traffic).
    Only an https APP_BASE_URL is used: Twilio cannot reach localhost, and a
    plain-http URL would fail the signature check behind a TLS proxy."""
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    return f"{base}/twilio/status-callback" if base.startswith("https://") else None


class SMSChannel(DeliveryChannel):
    name = "sms"

    def __init__(self, client: Client | None = None):
        self._client = client

    def _get_client(self) -> Client:
        if self._client is not None:
            return self._client
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    def is_configured(self) -> bool:
        return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)

    def _send_once(self, to: str, message: str, **kwargs) -> DeliveryResult:
        if not self.is_configured():
            return DeliveryResult(
                ok=False,
                channel=self.name,
                to=to,
                error="SMS not configured — set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER in .env",
                retriable=False,
            )

        try:
            params = {"to": to, "from_": TWILIO_FROM_NUMBER, "body": message[:1600]}
            callback = _status_callback_url()
            if callback:
                params["status_callback"] = callback
            msg = self._get_client().messages.create(**params)
        except TwilioRestException as exc:
            return DeliveryResult(
                ok=False,
                channel=self.name,
                to=to,
                error=f"Twilio error {exc.code}: {exc.msg}",
                retriable=exc.code not in _NON_RETRIABLE_CODES,
            )
        except Exception as exc:
            return DeliveryResult(
                ok=False, channel=self.name, to=to, error=str(exc), retriable=True
            )

        return DeliveryResult(ok=True, channel=self.name, to=to, provider_id=msg.sid)
