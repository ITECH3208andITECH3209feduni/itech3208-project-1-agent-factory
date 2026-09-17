# agent/delivery/voice_channel.py
# ──────────────────────────────────────────────────────────────
# Voice call delivery adapter (PROJ-428) — Dilraj Singh
#
# Outbound reminder call via Twilio's REST API. The message is spoken
# with the same Polly voice used by the AI Receptionist's inbound calls
# (app/web_ui/twilio_routes.py — POLLY_VOICE/POLLY_LANG) so a reminder
# call and a receptionist call sound like the same system. TwiML is
# passed inline (twiml=...) rather than pointing Twilio at a hosted
# URL — a one-way announcement doesn't need a callback endpoint.
# ──────────────────────────────────────────────────────────────

from __future__ import annotations

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from agent.delivery.base import DeliveryChannel, DeliveryResult
from config.settings import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER

POLLY_VOICE = "Polly.Joanna"
POLLY_LANG = "en-AU"

# Same reasoning as sms_channel.py's _NON_RETRIABLE_CODES.
_NON_RETRIABLE_CODES = {
    21211,  # invalid 'To' phone number
    21214,  # 'To' number not reachable
    21216,  # geo-permissions not enabled
    21606,  # 'From' number not owned by this account
    13224,  # invalid 'To' phone number format
}


class VoiceChannel(DeliveryChannel):
    name = "voice"

    def __init__(self, client: Client | None = None):
        self._client = client

    def _get_client(self) -> Client:
        if self._client is not None:
            return self._client
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    def is_configured(self) -> bool:
        return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)

    def _build_twiml(self, message: str) -> str:
        resp = VoiceResponse()
        resp.say(message, voice=POLLY_VOICE, language=POLLY_LANG)
        resp.hangup()
        return str(resp)

    def _send_once(self, to: str, message: str, **kwargs) -> DeliveryResult:
        if not self.is_configured():
            return DeliveryResult(
                ok=False,
                channel=self.name,
                to=to,
                error="Voice not configured — set TWILIO_ACCOUNT_SID, "
                "TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER in .env",
                retriable=False,
            )

        try:
            call = self._get_client().calls.create(
                to=to, from_=TWILIO_FROM_NUMBER, twiml=self._build_twiml(message)
            )
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

        return DeliveryResult(ok=True, channel=self.name, to=to, provider_id=call.sid)
