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
from app.web_ui.activity_db import log_activity
from app.web_ui.dashboard_routes import log_escalation
from app.web_ui.client_manager import get_active_client, build_system_prompt

router = APIRouter()

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


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # symbols/pictographs, emoticons, transport, supplemental
    "\U00002600-\U000027BF"  # misc symbols, dingbats
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F"              # variation selector (emoji presentation)
    "]+"
)


def _strip_emoji(text: str) -> str:
    """Polly reads emoji aloud on voice calls instead of silently skipping
    them — strip before speaking. Left out of SMS, where emoji are normal."""
    text = _EMOJI_PATTERN.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


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

    client = get_active_client()
    system_prompt = build_system_prompt(client, query=Body)
    result = _receptionist.handle(Body or "Hello", session_id=From, system_prompt=system_prompt,
                                    skip_global_faq=client.get("rag_enabled", False))
    reply = _strip_markdown(result["answer"])[:1600]  # Twilio SMS limit

    log_activity(
        channel="sms",
        caller=From or "unknown",
        intent=result.get("intent", ""),
        summary=reply[:200],
        caller_message=Body,
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
    client = get_active_client()
    greeting = _strip_emoji(client.get("greeting", "Hello! How can I help you today?"))
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/twilio/voice/reply",
        method="POST",
        speech_timeout="auto",
        language=POLLY_LANG,
    )
    gather.say(greeting, voice=POLLY_VOICE, language=POLLY_LANG)
    resp.append(gather)
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
        goodbye = _strip_emoji(get_active_client().get("goodbye", "Thank you for calling. Have a wonderful day. Goodbye!"))
        resp.say(goodbye, voice=POLLY_VOICE, language=POLLY_LANG)
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

    client = get_active_client()
    system_prompt = build_system_prompt(client, query=query)
    result = _receptionist.handle(query, session_id=CallSid, system_prompt=system_prompt,
                                    skip_global_faq=client.get("rag_enabled", False))
    reply = _strip_emoji(_strip_markdown(result["answer"]))

    log_activity(
        channel="voice",
        caller=CallSid or "unknown",
        intent=result.get("intent", ""),
        summary=reply[:200],
        caller_message=query,
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
    # If the AI's own reply already ends in a question (e.g. a clarifying
    # follow-up like "Which campus are you based at?"), don't also stack
    # the generic "anything else" prompt on top of it — the caller would
    # hear two different questions back to back and not know which one to
    # answer. Just listen for their answer to the AI's own question.
    if not reply.rstrip().endswith("?"):
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
