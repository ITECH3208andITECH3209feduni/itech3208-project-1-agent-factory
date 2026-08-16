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

from agent.orchestrator import Orchestrator
from app.web_ui.activity_db import log_activity
from app.web_ui.receptionist_routes import log_escalation

router = APIRouter()

# One shared orchestrator — the memory module handles per-session context via session_id
_orchestrator = Orchestrator()

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
) -> Response:
    """
    Receive an inbound Twilio SMS and reply through the AI Receptionist.
    Session is scoped to the caller's phone number (From field) so each
    caller has independent conversation history.
    PROJ-391
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

    rendered, result = _orchestrator.run(Body or "Hello")
    reply = _strip_markdown(rendered)[:1600]  # Twilio SMS limit

    log_activity(
        channel="sms",
        caller=From or "unknown",
        intent=result.skill_name if result else "",
        summary=(result.summary if result else reply)[:200],
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
) -> Response:
    """
    Receive Twilio's SpeechResult, query the AI Receptionist, and speak
    the answer back with Polly TTS. Loops for multi-turn dialogue.
    Detects goodbye keywords to hang up cleanly.
    PROJ-384
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

    rendered, result = _orchestrator.run(query)
    reply = _strip_markdown(rendered)

    log_activity(
        channel="voice",
        caller=CallSid or "unknown",
        intent=result.skill_name if result else "",
        summary=(result.summary if result else reply[:200]),
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
