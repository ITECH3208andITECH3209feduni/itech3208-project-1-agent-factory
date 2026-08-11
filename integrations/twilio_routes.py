# integrations/twilio_routes.py
# ──────────────────────────────────────────────────────────────
# Twilio SMS + Voice webhooks (PROJ-385)
# Twilio POSTs form-encoded data and expects TwiML (XML) back.
# ──────────────────────────────────────────────────────────────

import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, Request, Response
from twilio.request_validator import RequestValidator

from agent.orchestrator import Orchestrator
load_dotenv()

log = logging.getLogger("twilio")

AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
VALIDATE = os.getenv("TWILIO_VALIDATE_SIGNATURE", "false").lower() == "true"

# SMS segments are 160 chars; keep replies to one message where possible.
SMS_MAX_CHARS = 1500

router = APIRouter(prefix="/twilio", tags=["twilio"])
_orchestrator = Orchestrator(output_format="text")


def twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


async def signature_ok(request: Request, form: dict) -> bool:
    """Verify the request really came from Twilio."""
    if not VALIDATE:
        return True
    if not AUTH_TOKEN:
        log.warning("TWILIO_VALIDATE_SIGNATURE is on but TWILIO_AUTH_TOKEN is empty")
        return False
    validator = RequestValidator(AUTH_TOKEN)
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    return validator.validate(url, form, signature)


@router.post("/sms")
async def sms_webhook(request: Request):
    """Handle an inbound SMS and reply with the agent's answer."""
    form = dict(await request.form())

    if not await signature_ok(request, form):
        log.warning("rejected SMS with invalid Twilio signature")
        return Response(status_code=403)

    body = (form.get("Body") or "").strip()
    sender = form.get("From", "unknown")
    log.info("SMS from %s: %r", sender, body)

    if not body:
        return twiml(
            "<Response><Message>Send me a question and I'll look it up.</Message></Response>"
        )

    try:
        rendered, result = _orchestrator.run(body)
        reply = (result.summary if result and result.summary else rendered) or "No results found."
    except Exception as exc:
        log.exception("orchestrator failed for SMS")
        reply = "Sorry, something went wrong handling that request."

    if len(reply) > SMS_MAX_CHARS:
        reply = reply[: SMS_MAX_CHARS - 3] + "..."

    # Escape XML-significant characters so the TwiML stays valid.
    reply = (
        reply.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return twiml(f"<Response><Message>{reply}</Message></Response>")


@router.post("/voice")
async def voice_webhook(request: Request):
    """Answer an inbound call and collect a spoken question."""
    form = dict(await request.form())

    if not await signature_ok(request, form):
        log.warning("rejected call with invalid Twilio signature")
        return Response(status_code=403)

    log.info("voice call from %s", form.get("From", "unknown"))

    return twiml(
        "<Response>"
        "<Gather input='speech' action='/twilio/voice/handle' method='POST' speechTimeout='auto'>"
        "<Say voice='Polly.Nicole'>Welcome to Agent Factory. "
        "Ask your question after the tone.</Say>"
        "</Gather>"
        "<Say voice='Polly.Nicole'>Sorry, I didn't catch that. Goodbye.</Say>"
        "</Response>"
    )


@router.post("/voice/handle")
async def voice_handle(request: Request):
    """Run the transcribed speech through the orchestrator and speak the answer."""
    form = dict(await request.form())

    if not await signature_ok(request, form):
        return Response(status_code=403)

    speech = (form.get("SpeechResult") or "").strip()
    log.info("voice query: %r", speech)

    if not speech:
        return twiml(
            "<Response><Say voice='Polly.Nicole'>I didn't hear a question. Goodbye.</Say></Response>"
        )

    try:
        _, result = _orchestrator.run(speech)
        reply = (result.summary if result and result.summary else "No results found.")
    except Exception:
        log.exception("orchestrator failed for voice")
        reply = "Sorry, something went wrong."

    # Keep spoken replies short — long text-to-speech is unpleasant on a call.
    reply = reply[:500].replace("&", "and").replace("<", "").replace(">", "")
    return twiml(f"<Response><Say voice='Polly.Nicole'>{reply}</Say></Response>")