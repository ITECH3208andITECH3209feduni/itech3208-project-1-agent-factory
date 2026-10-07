# app/web_ui/twilio_routes.py
# ──────────────────────────────────────────────────────────────
# Twilio SMS and Voice webhook endpoints — AI Receptionist
# PROJ-391 (SMS)  — Dilraj Singh
# PROJ-384 (Voice) — Dilraj Singh
#
# Endpoints:
#   POST /twilio/sms           — receive SMS, reply via MessagingResponse
#   POST /twilio/voice         — answer call with Polly TTS greeting + Gather
#   POST /twilio/voice/reply   — process SpeechResult, reply via Polly TTS, loop
# ──────────────────────────────────────────────────────────────

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

from agent.receptionist import Receptionist
from app.web_ui.activity_db import log_activity, log_delivery_event, update_delivery_status
from app.web_ui.dashboard_routes import log_escalation
from integrations.sms_consent import handle_inbound

router = APIRouter()

# One shared receptionist — the memory module handles per-session context
# via session_id. Was Orchestrator (generic query routing) until now;
# Receptionist adds FAQ lookup, human escalation, and appointment
# booking — including the PROJ-445/446 booking -> reminder tie-in,
# which only fires when a caller/contact address is known, so real
# phone/SMS traffic is exactly the case it was built for.
_receptionist = Receptionist()

POLLY_VOICE = "Polly.Joanna"
POLLY_LANG = "en-AU"
GOODBYE_WORDS = {"goodbye", "bye", "hang up", "end call", "that's all", "no thanks"}


def _strip_markdown(text: str) -> str:
    """Remove Markdown syntax for plain-text channels (SMS, Voice)."""
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)   # bold / italic
    text = re.sub(r"#{1,6}\s+", "", text)                   # headings
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)   # links
    text = re.sub(r"`{1,3}[^`]+`{1,3}", lambda m: re.sub(r"`", "", m.group()), text)  # code
    text = re.sub(r"^[-*•]\s+", "", text, flags=re.MULTILINE)  # bullets
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── SMS ────────────────────────────────────────────────────────

@router.post("/twilio/sms")
async def sms_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    To: str = Form(default=""),
) -> Response:
    """
    Receive an inbound Twilio SMS and reply through the AI Receptionist.
    Session is scoped to the caller's phone number (From field) so each
    caller has independent conversation history.
    PROJ-391

    PROJ-414: STOP/START/HELP consent keywords are handled before the
    orchestrator ever sees the message — a STOP must never be treated
    as a query, cost an API call, or reach a skill.
    """
    validate = os.getenv("TWILIO_VALIDATE_SIGNATURE", "false").lower() == "true"
    if validate:
        from twilio.request_validator import RequestValidator
        token = os.getenv("TWILIO_AUTH_TOKEN", "")
        validator = RequestValidator(token)
        url = str(request.url)
        form = await request.form()
        sig = request.headers.get("X-Twilio-Signature", "")
        if not validator.validate(url, dict(form), sig):
            return Response(content="Forbidden", status_code=403)

    consent_reply = handle_inbound(Body, From, To)
    if consent_reply is not None:
        twiml = MessagingResponse()
        twiml.message(consent_reply)
        return Response(content=str(twiml), media_type="application/xml")

    result = _receptionist.handle(
        Body or "Hello", session_id=From,
        contact_channel="sms", contact_address=From,
    )
    reply = _strip_markdown(result["answer"])[:1600]  # Twilio SMS limit

    log_activity(
        channel="sms",
        caller=From or "unknown",
        intent=result.get("intent", ""),
        summary=reply[:200],
    )

    twiml = MessagingResponse()
    twiml.message(reply)
    return Response(content=str(twiml), media_type="application/xml")


# ── Voice ──────────────────────────────────────────────────────

@router.post("/twilio/voice")
async def voice_greeting(request: Request) -> Response:
    """
    Initial call handler. Greet the caller with Polly.Joanna TTS and open
    a Gather element to capture speech input.
    PROJ-384
    """
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/twilio/voice/reply",
        method="POST",
        speech_timeout="auto",
        language=POLLY_LANG,
    )
    gather.say(
        "Hello! Thank you for calling Agent Factory. How can I help you today?",
        voice=POLLY_VOICE,
        language=POLLY_LANG,
    )
    resp.append(gather)
    # Fallback if no speech detected
    resp.say(
        "Sorry, I didn't hear anything. Please call back when you're ready.",
        voice=POLLY_VOICE,
        language=POLLY_LANG,
    )
    resp.hangup()
    return Response(content=str(resp), media_type="application/xml")


@router.post("/twilio/voice/reply")
async def voice_reply(
    request: Request,
    SpeechResult: str = Form(default=""),
    CallSid: str = Form(default=""),
    From: str = Form(default=""),
) -> Response:
    """
    Receive Twilio's SpeechResult, query the AI Receptionist, and speak
    the answer back with Polly TTS. Loops for multi-turn dialogue.
    Detects goodbye keywords to hang up cleanly.
    PROJ-384

    Twilio resends the call's From on every webhook for that call, so
    it's available here even though the call started at /twilio/voice.
    """
    query = SpeechResult.strip()
    resp = VoiceResponse()

    # Goodbye detection
    if any(kw in query.lower() for kw in GOODBYE_WORDS):
        resp.say(
            "Thank you for calling Agent Factory. Have a wonderful day. Goodbye!",
            voice=POLLY_VOICE,
            language=POLLY_LANG,
        )
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    # Empty transcript fallback
    if not query:
        resp.say(
            "I'm sorry, I didn't catch that. Could you please repeat your question?",
            voice=POLLY_VOICE,
            language=POLLY_LANG,
        )
        gather = Gather(
            input="speech",
            action="/twilio/voice/reply",
            method="POST",
            speech_timeout="auto",
            language=POLLY_LANG,
        )
        resp.append(gather)
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    result = _receptionist.handle(
        query, session_id=CallSid,
        contact_channel="voice", contact_address=From,
    )
    reply = _strip_markdown(result["answer"])

    log_activity(
        channel="voice",
        caller=CallSid or "unknown",
        intent=result.get("intent", ""),
        summary=reply[:200],
    )

    # Trim to ~250 words for voice suitability
    words = reply.split()
    if len(words) > 250:
        reply = " ".join(words[:250]) + "."

    resp.say(reply, voice=POLLY_VOICE, language=POLLY_LANG)

    # Loop back for a follow-up question
    gather = Gather(
        input="speech",
        action="/twilio/voice/reply",
        method="POST",
        speech_timeout="auto",
        language=POLLY_LANG,
    )
    gather.say(
        "Is there anything else I can help you with?",
        voice=POLLY_VOICE,
        language=POLLY_LANG,
    )
    resp.append(gather)
    resp.say(
        "Thank you for calling. Goodbye!",
        voice=POLLY_VOICE,
        language=POLLY_LANG,
    )
    resp.hangup()
    return Response(content=str(resp), media_type="application/xml")


# ── Delivery Status Webhook (PROJ-432) ─────────────────────────

@router.post("/twilio/status-callback")
@router.post("/twilio/status")
async def twilio_status_callback(
    request: Request,
    MessageSid: str = Form(default=""),
    CallSid: str = Form(default=""),
    SmsSid: str = Form(default=""),
    MessageStatus: str = Form(default=""),
    CallStatus: str = Form(default=""),
    SmsStatus: str = Form(default=""),
    To: str = Form(default=""),
    From: str = Form(default=""),
    ErrorCode: str = Form(default=""),
    ErrorMessage: str = Form(default=""),
) -> Response:
    """
    Handle Twilio status callbacks for SMS and Voice messages.
    Updates delivery tracking record, records errors, and logs status transitions.
    PROJ-432
    """
    # Fallback to JSON payload if Content-Type is application/json
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            MessageSid = MessageSid or body.get("MessageSid") or body.get("SmsSid") or body.get("CallSid") or ""
            MessageStatus = MessageStatus or body.get("MessageStatus") or body.get("SmsStatus") or body.get("CallStatus") or ""
            To = To or body.get("To") or ""
            From = From or body.get("From") or ""
            ErrorCode = ErrorCode or str(body.get("ErrorCode") or "")
            ErrorMessage = ErrorMessage or body.get("ErrorMessage") or ""
        except Exception:
            pass

    msg_id = MessageSid or SmsSid or CallSid
    status = MessageStatus or SmsStatus or CallStatus or "unknown"
    channel = "voice" if CallSid and not (MessageSid or SmsSid) else "sms"

    if not msg_id:
        # Check query params
        msg_id = request.query_params.get("MessageSid") or request.query_params.get("CallSid") or ""
        status = status if status != "unknown" else request.query_params.get("MessageStatus", "unknown")

    if not msg_id:
        return Response(content="<Response/>", media_type="application/xml")

    # Update delivery tracking in database
    updated = update_delivery_status(
        message_id=msg_id,
        status=status,
        error_code=ErrorCode,
        error_message=ErrorMessage,
    )

    if not updated:
        # If record didn't exist prior to callback, register it now
        log_delivery_event(
            message_id=msg_id,
            recipient=To or "unknown",
            channel=channel,
            reminder_type="voice_call" if channel == "voice" else "sms_reminder",
            status=status,
            metadata={"from": From, "error_code": ErrorCode, "error_message": ErrorMessage},
        )
        if ErrorCode or ErrorMessage or status in ("failed", "undelivered"):
            update_delivery_status(msg_id, status, ErrorCode, ErrorMessage)

    # If delivery failed, log in activity stream for visibility
    if status.lower() in ("failed", "undelivered"):
        log_activity(
            channel=channel,
            caller=To or "unknown",
            intent="delivery_failure",
            summary=f"Delivery failed for {msg_id}: {ErrorMessage or ErrorCode or status}",
        )

    return Response(content="<Response/>", media_type="application/xml")

