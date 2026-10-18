# app/web_ui/twilio_routes.py
# ──────────────────────────────────────────────────────────────
# Twilio SMS and Voice webhook endpoints — AI Receptionist
# PROJ-391 (SMS)   — Dilraj Singh
# PROJ-384 (Voice) — Dilraj Singh
# PROJ-470 (Multi-language voice — Part D optional)
#
# Endpoints:
#   POST /twilio/sms           — receive SMS, reply via MessagingResponse
#   POST /twilio/voice         — answer call with Polly TTS greeting + Gather
#   POST /twilio/voice/reply   — process SpeechResult, reply via Polly TTS, loop
#   GET  /twilio/voice/languages — list supported languages (PROJ-470)
#   POST /twilio/voice/language  — set operator default language (PROJ-470)
#   POST /twilio/status-callback — delivery status updates
#
# PROJ-466: every route above verifies the X-Twilio-Signature header once the
# app is on a public URL. It used to be only /twilio/sms, which left the voice
# and status-callback routes open to anyone who knew the hostname — forged
# status callbacks corrupt delivery records, and forged /twilio/voice posts
# spend Claude tokens on demand.
# ──────────────────────────────────────────────────────────────

import logging
import os
import re
import sys
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response

from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

from fastapi.responses import JSONResponse

from agent.call_summary import finalize_call
from auth.sms_routing import resolve_org_by_twilio_number
from agent.receptionist import Receptionist
from app.web_ui.activity_db import log_activity, log_delivery_event, update_delivery_status
from app.web_ui.dashboard_routes import log_escalation
from app.web_ui.voice_languages import (
    DEFAULT_LANG, detect_language, list_supported_languages, resolve_voice,
)
from integrations.sms_consent import handle_inbound

router = APIRouter()


def _say_brand(phrases: dict) -> dict:
    """The name callers hear: BRAND_NAME when set (the clinic demo), else Agent Factory."""
    import os

    name = os.environ.get("BRAND_NAME", "").strip()
    if not name or name == "Agent Factory":
        return phrases
    return {lang: text.replace("Agent Factory", name) for lang, text in phrases.items()}

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
# Booking answers Twilio didn't hear, per call  {CallSid: count}
_unheard: dict[str, int] = {}
MAX_UNHEARD = 2  # ask again this many times, then hand the booking to the team

POLLY_VOICE = "Polly.Joanna"  # kept for SMS/status-callback references
POLLY_LANG = DEFAULT_LANG      # kept for non-voice paths
GOODBYE_WORDS = {"goodbye", "bye", "hang up", "end call", "that's all", "no thanks"}
_BOOKING_GOODBYES = {"goodbye", "hang up", "end call"}

log = logging.getLogger("agent_factory.twilio")


def _activity_intent(result: dict) -> str:
    """The intent recorded in the activity log. A booking that really went through is
    logged as appointment_booked so the Booked tile counts bookings, not questions."""
    if result.get("booked") is True:
        return "appointment_booked"
    return result.get("intent", "")


def _org_for(*numbers: str) -> int | None:
    """Which organisation owns this conversation? Looked up from our Twilio number
    (the To of an inbound call or text, the From of an outbound status callback).
    None when nothing matches, which the dashboards read as the default
    organisation's legacy data rather than guessing (PROJ-501)."""
    for number in numbers:
        if not number:
            continue
        try:
            org = resolve_org_by_twilio_number(number)
        except Exception:  # noqa: BLE001 - a lookup problem must never break a call
            org = None
        if org is not None:
            return org
    if any(numbers):
        log.info("No organisation owns the number(s) ending %s; saving with no organisation",
                 ", ".join(n[-3:] for n in numbers if n))
    return None


def _summarise_call_later(call_sid: str, caller: str, org_id: int | None = None) -> None:
    """Tag a finished call with a summary, sentiment and priority (PROJ-477).
    Runs in a thread so the Claude call never delays the TwiML reply Twilio is
    waiting on; any failure is logged and never reaches the caller."""
    if not call_sid:
        return

    def _run() -> None:
        try:
            finalize_call(call_sid, caller, _receptionist.memory, org_id=org_id)
        except Exception:  # noqa: BLE001
            log.exception("post-call summary failed for %s", call_sid)

    threading.Thread(target=_run, daemon=True).start()

FORBIDDEN = Response(content="Forbidden", status_code=403)


async def reject_unsigned(request: Request) -> Response | None:
    """
    Verify Twilio's X-Twilio-Signature. Returns a 403 Response to return to the
    caller, or None when the request may proceed (PROJ-466).

    Off by default so local development and the test suite keep working; set
    TWILIO_VALIDATE_SIGNATURE=true in any environment reachable from the
    internet. fly.toml sets it.

    Validation hashes the exact URL Twilio signed, so the app must see the
    public https:// URL rather than the proxy's internal http:// one — hence
    --proxy-headers in deploy/start.sh. A mismatch here looks like every
    request being rejected.
    """
    if os.getenv("TWILIO_VALIDATE_SIGNATURE", "false").lower() != "true":
        return None

    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token:
        # Fail closed. Validation was explicitly asked for and cannot be done,
        # which is a misconfiguration, not a reason to accept the request.
        log.error("TWILIO_VALIDATE_SIGNATURE is on but TWILIO_AUTH_TOKEN is unset; rejecting.")
        return FORBIDDEN

    from twilio.request_validator import RequestValidator

    # Starlette caches the parsed form, so reading it here does not consume the
    # body the route's own Form(...) parameters depend on.
    form = await request.form()
    signature = request.headers.get("X-Twilio-Signature", "")
    if not RequestValidator(token).validate(str(request.url), dict(form), signature):
        log.warning("Rejected unsigned/invalid Twilio request to %s", request.url.path)
        return FORBIDDEN

    return None


def _strip_markdown(text: str) -> str:
    """Remove Markdown syntax for plain-text channels (SMS, Voice)."""
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)   # bold / italic
    text = re.sub(r"#{1,6}\s+", "", text)                   # headings
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)   # links
    text = re.sub(r"`{1,3}[^`]+`{1,3}", lambda m: re.sub(r"`", "", m.group()), text)  # code
    text = re.sub(r"^[-*•]\s+", "", text, flags=re.MULTILINE)  # bullets
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Pictographs, dingbats, arrows, flags and the joiners that glue emoji together.
# Polly reads these aloud by name ("smiling face with smiling eyes"), so voice
# replies drop them. SMS keeps them.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002190-\U000021FF\U00002300-\U000023FF"
    "\U00002600-\U000027BF\U00002B00-\U00002BFF\U0000FE0F\U0000200D\U000020E3]"
)


# Australia's emergency number. Polly reads "000" as "oh oh oh"; callers expect
# "triple zero". Digits that are part of a longer number (1800 000 123) are left alone.
_TRIPLE_ZERO_RE = re.compile(r"(?<![\d])(?<!\d[ -])000(?![ -]?\d)")


# Phone numbers are read one digit at a time, in the groups people write them
# in, with a short pause between groups: "zero four one two, three four five,
# six seven eight". Otherwise Polly says "four hundred and twelve".
_DIGIT_NAMES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_NUMBER_IN_TEXT = re.compile(r"\+?\(?\d[\d \-()]{6,}\d")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
# Email addresses are read as "jane dot citizen at gmail dot com".
_EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_EMAIL_SYMBOLS = {".": " dot ", "@": " at ", "_": " underscore ", "-": " dash ", "+": " plus "}


def _say_digits(group: str) -> str:
    return " ".join(_DIGIT_NAMES[int(c)] for c in group if c.isdigit())


def _spoken_number(match: re.Match) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 8 or _ISO_DATE.match(raw):
        return raw  # times, years, prices and dates are read normally
    prefix = ""
    if raw.startswith("+61") and len(digits) == 11:
        local = "0" + digits[2:]  # +61 4xx xxx xxx is read the Australian way
        groups = [local[:4], local[4:7], local[7:]]
    else:
        if raw.startswith("+"):
            prefix = "plus "
        groups = [g for g in re.split(r"[ ()-]+", raw.lstrip("+")) if g]
        if len(groups) == 1:
            run = groups[0]
            if len(run) == 10:
                sizes = (4, 3, 3)
            elif prefix and run.startswith("1") and len(run) == 11:
                sizes = (1, 3, 3, 4)  # +1 555 010 0199
            else:
                sizes = (3,) * ((len(run) + 2) // 3)
            groups, i = [], 0
            for size in sizes:
                if i < len(run):
                    groups.append(run[i:i + size])
                    i += size
    return prefix + ", ".join(_say_digits(g) for g in groups)


def _spoken_email(match: re.Match) -> str:
    out = "".join(_EMAIL_SYMBOLS.get(c, c) for c in match.group(0).lower())
    return re.sub(r"\s+", " ", out).strip()


def _speakable(text: str) -> str:
    """Plain text for text-to-speech: no Markdown, no emoji, 000 said as triple
    zero, phone numbers digit by digit and email addresses spelled out."""
    text = _EMOJI_RE.sub("", _strip_markdown(text))
    text = _EMAIL_IN_TEXT.sub(_spoken_email, text)
    text = _NUMBER_IN_TEXT.sub(_spoken_number, text)
    text = _TRIPLE_ZERO_RE.sub("triple zero", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


# Hints help Twilio's speech recognition while a booking asks for a phone
# number or an email address.
_SPEECH_HINTS = {
    "phone": "zero, oh, double, triple, this number",
    "email": "at, dot, underscore, dash, gmail dot com, outlook dot com, hotmail dot com, "
             "yahoo dot com, icloud dot com, bigpond dot com, no email",
    "confirm": "yes, no, correct, that's right",
}


def _gather_opts(lang: str, stage: str | None = None) -> dict:
    """Twilio <Gather> settings for the next answer.

    actionOnEmptyResult makes Twilio call us back even when it heard nothing,
    so a missed answer gets the question again instead of a hang-up. While a
    booking asks for details the caller gets longer to start talking, and
    longer pauses for reading out a phone number or an email address."""
    opts = {
        "input": "speech",
        "action": "/twilio/voice/reply",
        "method": "POST",
        "speech_timeout": "auto",
        "language": lang,
        "action_on_empty_result": True,
    }
    if stage:
        opts["timeout"] = 8
    if stage in ("phone", "email"):
        opts["speech_timeout"] = "3"
    if stage in _SPEECH_HINTS:
        opts["hints"] = _SPEECH_HINTS[stage]
    return opts


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
    denied = await reject_unsigned(request)
    if denied:
        return denied

    consent_reply = handle_inbound(Body, From, To)
    if consent_reply is not None:
        twiml = MessagingResponse()
        twiml.message(consent_reply)
        return Response(content=str(twiml), media_type="application/xml")

    result = _receptionist.handle(
        Body or "Hello", session_id=From,
        contact_channel="sms", contact_address=From, org_id=_org_for(To),
    )
    reply = _strip_markdown(result["answer"])[:1600]  # Twilio SMS limit

    log_activity(
        channel="sms",
        caller=From or "unknown",
        intent=_activity_intent(result),
        summary=reply[:200],
        org_id=_org_for(To),
    )

    twiml = MessagingResponse()
    twiml.message(reply)
    return Response(content=str(twiml), media_type="application/xml")


# ── Voice language helpers (PROJ-470) ──────────────────────────

def _require_operator(request: Request) -> None:
    """These two routes sit under /twilio/ (a public prefix because the real
    Twilio webhooks verify their own signature), but they are operator
    controls, not webhooks, so they need a logged-in session."""
    from app.web_ui.auth_routes import get_current_username

    get_current_username(request)  # raises 401 when not signed in


@router.get("/twilio/voice/languages")
async def list_voice_languages(request: Request):
    """Return supported voice languages for the language selector (PROJ-470)."""
    _require_operator(request)
    return {
        "languages": list_supported_languages(),
        "default": _operator_default_lang,
    }


@router.post("/twilio/voice/language")
async def set_voice_language(request: Request):
    """Operator sets the default voice language for new calls (PROJ-470)."""
    global _operator_default_lang
    _require_operator(request)
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
    denied = await reject_unsigned(request)
    if denied:
        return denied

    lang_param = request.query_params.get("lang", "").strip() or _operator_default_lang
    voice, lang = resolve_voice(lang_param)
    # Note CallSid isn't available at greeting-time on inbound, so we use
    # a synthetic key derived from the form body if needed.
    form = await request.form()
    call_sid = form.get("CallSid", "")
    if call_sid:
        _call_lang[call_sid] = lang_param

    greetings = _say_brand({
        "en-AU": "Hello! Thank you for calling Agent Factory. How can I help you today?",
        "en-US": "Hello! Thank you for calling Agent Factory. How can I help you today?",
        "es-US": "¡Hola! Gracias por llamar a Agent Factory. ¿En qué puedo ayudarle?",
        "hi-IN": "नमस्ते! Agent Factory में कॉल करने के लिए धन्यवाद। मैं आपकी कैसे मदद कर सकता हूँ?",
        "cmn-CN": "您好！感谢致电 Agent Factory。我今天可以怎么帮助您？",
        "fr-FR": "Bonjour ! Merci d'appeler Agent Factory. Comment puis-je vous aider aujourd'hui ?",
        "de-DE": "Hallo! Vielen Dank für Ihren Anruf bei Agent Factory. Wie kann ich Ihnen helfen?",
    })
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
    To: str = Form(default=""),
) -> Response:
    """
    Receive Twilio's SpeechResult, query the AI Receptionist, and speak
    the answer back with Polly TTS. Loops for multi-turn dialogue.
    Detects goodbye keywords to hang up cleanly.
    PROJ-384 / PROJ-470 (dynamic Polly voice per language)

    Twilio resends the call's From on every webhook for that call, so
    it's available here even though the call started at /twilio/voice.
    """
    denied = await reject_unsigned(request)
    if denied:
        return denied

    query = SpeechResult.strip()

    # PROJ-470: Detect language from speech or fall back to stored/operator default
    detected = detect_language(query)
    lang_code = detected or _call_lang.get(CallSid, _operator_default_lang)
    if CallSid:
        _call_lang[CallSid] = lang_code   # remember for subsequent turns
    voice, lang = resolve_voice(lang_code)

    goodbye_phrases = _say_brand({
        "en-AU": "Thank you for calling Agent Factory. Have a wonderful day. Goodbye!",
        "en-US": "Thank you for calling Agent Factory. Have a wonderful day. Goodbye!",
        "es-US": "Gracias por llamar a Agent Factory. ¡Que tenga un buen día!",
        "hi-IN": "Agent Factory में कॉल करने के लिए धन्यवाद। आपका दिन शुभ हो!",
        "cmn-CN": "感谢致电 Agent Factory。祝您有美好的一天，再见！",
        "fr-FR": "Merci d'avoir appelé Agent Factory. Bonne journée. Au revoir !",
        "de-DE": "Danke für Ihren Anruf bei Agent Factory. Einen schönen Tag noch. Auf Wiederhören!",
    })
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

    # Goodbye detection. Mid-booking, "no thanks" is an answer (no email), so
    # only an explicit goodbye ends the call.
    goodbye_words = _BOOKING_GOODBYES if _receptionist.booking_question(CallSid) else GOODBYE_WORDS
    if any(kw in query.lower() for kw in goodbye_words):
        if CallSid in _call_lang:
            del _call_lang[CallSid]
        resp.say(goodbye_phrases.get(lang_code, goodbye_phrases["en-AU"]), voice=voice, language=lang)
        resp.hangup()
        _summarise_call_later(CallSid, From, _org_for(To))
        return Response(content=str(resp), media_type="application/xml")

    # Nothing heard. Mid-booking, ask the same question again instead of hanging
    # up; after a few tries, ask the team to ring back and finish the booking.
    # Otherwise (silence after "anything else?") the caller is done.
    if not query:
        question = _receptionist.booking_question(CallSid)
        if question:
            misses = _unheard.get(CallSid, 0) + 1
            _unheard[CallSid] = misses
            if misses <= MAX_UNHEARD:
                gather = Gather(**_gather_opts(lang, _receptionist.booking_stage(CallSid)))
                gather.say(_speakable("Sorry, I didn't hear that. " + question), voice=voice, language=lang)
                resp.append(gather)
                resp.say(goodbye_phrases.get(lang_code, goodbye_phrases["en-AU"]), voice=voice, language=lang)
                resp.hangup()
                return Response(content=str(resp), media_type="application/xml")
            _receptionist.hand_booking_to_team(CallSid, From)
            _unheard.pop(CallSid, None)
            resp.say(_speakable(
                "I'm having trouble hearing you, so I've asked the team to call you back on "
                f"{From} to finish your booking." if From else
                "I'm having trouble hearing you, so I've asked the team to follow up on your booking."
            ), voice=voice, language=lang)
            resp.say(goodbye_phrases.get(lang_code, goodbye_phrases["en-AU"]), voice=voice, language=lang)
            resp.hangup()
            _summarise_call_later(CallSid, From, _org_for(To))
            return Response(content=str(resp), media_type="application/xml")

        _call_lang.pop(CallSid, None)
        resp.say(goodbye_phrases.get(lang_code, goodbye_phrases["en-AU"]), voice=voice, language=lang)
        resp.hangup()
        _summarise_call_later(CallSid, From, _org_for(To))
        return Response(content=str(resp), media_type="application/xml")

    _unheard.pop(CallSid, None)
    result = _receptionist.handle(
        query, session_id=CallSid,
        contact_channel="voice", contact_address=From, org_id=_org_for(To),
    )
    reply = _speakable(result["answer"])

    log_activity(
        channel="voice",
        caller=CallSid or "unknown",
        intent=_activity_intent(result),
        summary=reply[:200],
        org_id=_org_for(To),
    )

    # Trim to ~250 words for voice suitability
    words = reply.split()
    if len(words) > 250:
        reply = " ".join(words[:250]) + "."

    # Mid-booking the reply already ends in a question ("What's your full
    # name?"), so the caller is not also asked "anything else?".
    asking = bool(result.get("needs_info"))
    gather = Gather(**_gather_opts(lang, result.get("expect") if asking else None))
    if asking:
        gather.say(reply, voice=voice, language=lang)
    else:
        resp.say(reply, voice=voice, language=lang)
        # Loop back for a follow-up question (PROJ-470: translated prompt)
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

    PROJ-466: this route writes to the delivery log from an unauthenticated
    public URL, so it is signature-checked like the others. Note that Twilio
    signs form-encoded parameters; the JSON branch below is for our own tooling
    and cannot satisfy validation, so it only works with validation off.
    """
    denied = await reject_unsigned(request)
    if denied:
        return denied

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
            org_id=_org_for(To, From),
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
            org_id=_org_for(To, From),
        )

    # A completed inbound call that never said goodbye (caller just hung up)
    # still gets its post-call summary (PROJ-477).
    if channel == "voice" and status.lower() == "completed":
        _summarise_call_later(CallSid or msg_id, From or To, _org_for(To, From))

    return Response(content="<Response/>", media_type="application/xml")

