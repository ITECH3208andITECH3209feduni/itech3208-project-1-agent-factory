# app/web_ui/twilio_routes.py
# ──────────────────────────────────────────────────────────────
# Twilio SMS and Voice webhook endpoints — AI Receptionist
# PROJ-391 (SMS)   — Dilraj Singh
# PROJ-384 (Voice) — Dilraj Singh
# PROJ-470 (Multi-language voice — Part D optional)
#
# Endpoints:
#   POST /twilio/sms              — receive SMS, reply via MessagingResponse
#   POST /twilio/voice            — answer call with Polly TTS greeting + Gather
#   POST /twilio/voice/reply      — process SpeechResult, reply via Polly TTS, loop
#   GET  /twilio/voice/languages  — list supported languages (PROJ-470)
#   POST /twilio/voice/language   — set operator default language (PROJ-470)
# ──────────────────────────────────────────────────────────────

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

from fastapi.responses import JSONResponse

from agent.receptionist import Receptionist
from app.web_ui.activity_db import log_activity, log_delivery_event, update_delivery_status
from app.web_ui.dashboard_routes import log_escalation
from app.web_ui.voice_languages import (
    DEFAULT_LANG, detect_language, list_supported_languages, resolve_voice,
)
from integrations.sms_consent import handle_inbound

router = APIRouter()

# One shared receptionist — the memory module handles per-session context
# via session_id. Was Orchestrator (generic query routing) until now;
# Receptionist adds FAQ lookup, human escalation, and appointment
# booking — including the PROJ-445/446 booking -> reminder tie-in,
# which only fires when a caller/contact address is known, so real
# phone/SMS traffic is exactly the case it was built for.
_receptionist = Receptionist()

# PROJ-470: per-call language preference  {CallSid: lang_code}
_call_lang: dict[str, str] = {}
# Operator default (set via POST /twilio/voice/language)
_operator_default_lang: str = DEFAULT_LANG

POLLY_VOICE = "Polly.Joanna"  # kept for SMS/status-callback references
POLLY_LANG = DEFAULT_LANG      # kept for non-voice paths
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


# ── Voice language helpers (PROJ-470) ──────────────────────────

@router.get("/twilio/voice/languages")
async def list_voice_languages():
    """Return supported voice languages for the language selector (PROJ-470)."""
    return {
        "languages": list_supported_languages(),
        "default": _operator_default_lang,
    }


@router.post("/twilio/voice/language")
async def set_voice_language(request: Request):
    """Operator sets the default voice language for new calls (PROJ-470)."""
    global _operator_default_lang
    try:
        body = await request.json()
        from app.web_ui.voice_languages import VOICE_MAP
        lang = body.get("language", "").strip()
        if lang not in VOICE_MAP:
            return JSONResponse({"error": f"Unsupported language: {lang}"}, status_code=422)
        _operator_default_lang = lang
        return {"ok": True, "language": _operator_default_lang}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


# ── Voice ──────────────────────────────────────────────────────

@router.post("/twilio/voice")
async def voice_greeting(request: Request) -> Response:
    """
    Initial call handler. Greet the caller with Polly TTS and open
    a Gather element to capture speech input. Language auto-detected from
    query param ?lang= or falls back to operator default (PROJ-470).
    PROJ-384
    """
    lang_param = request.query_params.get("lang", "").strip() or _operator_default_lang
    voice, lang = resolve_voice(lang_param)
    # Note CallSid isn't available at greeting-time on inbound, so we use
    # a synthetic key derived from the form body if needed.
    form = await request.form()
    call_sid = form.get("CallSid", "")
    if call_sid:
        _call_lang[call_sid] = lang_param

    greetings = {
        "en-AU": "Hello! Thank you for calling Agent Factory. How can I help you today?",
        "en-US": "Hello! Thank you for calling Agent Factory. How can I help you today?",
        "es-US": "¡Hola! Gracias por llamar a Agent Factory. ¿En qué puedo ayudarle?",
        "hi-IN": "नमस्ते! Agent Factory में कॉल करने के लिए धन्यवाद। मैं आपकी कैसे मदद कर सकता हूँ?",
        "cmn-CN": "您好！感谢致电 Agent Factory。我今天可以怎么帮助您？",
        "fr-FR": "Bonjour ! Merci d'appeler Agent Factory. Comment puis-je vous aider aujourd'hui ?",
        "de-DE": "Hallo! Vielen Dank für Ihren Anruf bei Agent Factory. Wie kann ich Ihnen helfen?",
    }
    fallbacks = {
        "en-AU": "Sorry, I didn't hear anything. Please call back when you're ready.",
        "en-US": "Sorry, I didn't hear anything. Please call back when you're ready.",
        "es-US": "Lo siento, no le escuché. Por favor, llame de nuevo cuando esté listo.",
        "hi-IN": "क्षमा करें, मैंने कुछ नहीं सुना। कृपया वापस कॉल करें।",
        "cmn-CN": "对不起，我没有听到任何声音。请稍后再打来。",
        "fr-FR": "Désolé, je n'ai rien entendu. Veuillez rappeler quand vous serez prêt.",
        "de-DE": "Entschuldigung, ich habe nichts gehört. Bitte rufen Sie zurück.",
    }
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/twilio/voice/reply",
        method="POST",
        speech_timeout="auto",
        language=lang,
    )
    gather.say(greetings.get(lang_param, greetings["en-AU"]), voice=voice, language=lang)
    resp.append(gather)
    resp.say(fallbacks.get(lang_param, fallbacks["en-AU"]), voice=voice, language=lang)
    resp.hangup()
    return Response(content=str(resp), media_type="application/xml")


@router.post("/twilio/voice/reply")
async def voice_reply(
    request: Request,  # noqa: ARG001
    SpeechResult: str = Form(default=""),
    CallSid: str = Form(default=""),
    From: str = Form(default=""),
) -> Response:
    """
    Receive Twilio's SpeechResult, query the AI Receptionist, and speak
    the answer back with Polly TTS. Loops for multi-turn dialogue.
    Detects goodbye keywords to hang up cleanly.
    PROJ-384 / PROJ-470 (dynamic Polly voice per language)

    Twilio resends the call's From on every webhook for that call, so
    it's available here even though the call started at /twilio/voice.
    """
    query = SpeechResult.strip()

    # PROJ-470: Detect language from speech or fall back to stored/operator default
    detected = detect_language(query)
    lang_code = detected or _call_lang.get(CallSid, _operator_default_lang)
    if CallSid:
        _call_lang[CallSid] = lang_code   # remember for subsequent turns
    voice, lang = resolve_voice(lang_code)

    goodbye_phrases = {
        "en-AU": "Thank you for calling Agent Factory. Have a wonderful day. Goodbye!",
        "en-US": "Thank you for calling Agent Factory. Have a wonderful day. Goodbye!",
        "es-US": "Gracias por llamar a Agent Factory. ¡Que tenga un buen día!",
        "hi-IN": "Agent Factory में कॉल करने के लिए धन्यवाद। आपका दिन शुभ हो!",
        "cmn-CN": "感谢致电 Agent Factory。祝您有美好的一天，再见！",
        "fr-FR": "Merci d'avoir appelé Agent Factory. Bonne journée. Au revoir !",
        "de-DE": "Danke für Ihren Anruf bei Agent Factory. Einen schönen Tag noch. Auf Wiederhören!",
    }
    retry_phrases = {
        "en-AU": "I'm sorry, I didn't catch that. Could you please repeat your question?",
        "en-US": "I'm sorry, I didn't catch that. Could you please repeat your question?",
        "es-US": "Lo siento, no le entendí. ¿Podría repetir su pregunta?",
        "hi-IN": "मुझे माफ़ करें, मैं समझ नहीं पाया। क्या आप अपना प्रश्न दोहरा सकते हैं?",
        "cmn-CN": "对不起，我没听清楚。您能重复一下您的问题吗？",
        "fr-FR": "Désolé, je n'ai pas compris. Pourriez-vous répéter votre question ?",
        "de-DE": "Entschuldigung, ich habe das nicht verstanden. Könnten Sie Ihre Frage wiederholen?",
    }
    followup_phrases = {
        "en-AU": "Is there anything else I can help you with?",
        "en-US": "Is there anything else I can help you with?",
        "es-US": "¿Hay algo más en lo que pueda ayudarle?",
        "hi-IN": "क्या मैं आपकी और कोई सहायता कर सकता हूँ?",
        "cmn-CN": "还有什么我可以帮助您的吗？",
        "fr-FR": "Y a-t-il autre chose avec laquelle je peux vous aider ?",
        "de-DE": "Gibt es noch etwas, womit ich Ihnen helfen kann?",
    }

    resp = VoiceResponse()

    # Goodbye detection
    if any(kw in query.lower() for kw in GOODBYE_WORDS):
        if CallSid in _call_lang:
            del _call_lang[CallSid]
        resp.say(goodbye_phrases.get(lang_code, goodbye_phrases["en-AU"]), voice=voice, language=lang)
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    # Empty transcript fallback
    if not query:
        resp.say(retry_phrases.get(lang_code, retry_phrases["en-AU"]), voice=voice, language=lang)
        gather = Gather(
            input="speech",
            action="/twilio/voice/reply",
            method="POST",
            speech_timeout="auto",
            language=lang,
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

    resp.say(reply, voice=voice, language=lang)

    # Loop back for a follow-up question (PROJ-470: translated prompt)
    gather = Gather(
        input="speech",
        action="/twilio/voice/reply",
        method="POST",
        speech_timeout="auto",
        language=lang,
    )
    gather.say(followup_phrases.get(lang_code, followup_phrases["en-AU"]), voice=voice, language=lang)
    resp.append(gather)
    resp.say(goodbye_phrases.get(lang_code, goodbye_phrases["en-AU"]), voice=voice, language=lang)
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

