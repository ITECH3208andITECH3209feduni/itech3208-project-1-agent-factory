# agent/receptionist.py
# ──────────────────────────────────────────────────────────────
# AI Receptionist — conversational intent routing (PROJ-195 epic,
# PROJ-209-213 intent routing, PROJ-214-218 KB lookups)
#
# Routing order (per PROJ-214's spec: "ChromaDB lookup before skill
# routing"):
#   1. FAQ knowledge base (agent/faq.py)      — fast, no API call
#   2. Escalation keywords                    — "talk to a human" etc.
#   3. Appointment booking                    — Claude extracts date/
#                                                time, then name, phone
#                                                and email are collected,
#                                                read back, and saved as an
#                                                unconfirmed booking
#                                                (agent/bookings.py)
#   4. General conversation                   — Claude, receptionist
#                                                system prompt
#
# Every branch persists to SessionMemory scoped by session_id so a
# logged-in user's receptionist chat has continuity, same as the
# research Orchestrator (PROJ-349's per-user isolation applies here
# too).
# ──────────────────────────────────────────────────────────────

import json
import re
import time
from datetime import datetime, timedelta, timezone

import anthropic

from agent.calendar_client import (
    book_appointment,
    find_upcoming_appointments,
    update_appointment,
    is_configured as calendar_configured,
)
from agent import bookings
from agent.faq import find_answer
from agent.memory import SessionMemory
from contracts.schemas import normalise_phone
from agent.reminders.booking_hooks import (
    create_reminder_for_booking,
    reschedule_reminders_for_booking,
)
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, TIMEZONE, ESCALATION_LOG

RECEPTIONIST_SYSTEM_PROMPT = """You are the front-desk AI receptionist for Agent Factory.
Be warm, brief, and helpful. You can answer general questions, but you are
NOT the literature-search or Amazon-research specialist — if someone
clearly wants deep product or paper research, gently point them at the
"Amazon Seller AI" / "Literature AI" tabs instead of trying to do that
research yourself.
Never say an appointment is booked, confirmed, moved or cancelled: bookings are
only made through the booking steps, which ask for the day and time, the
person's name, phone number and email, and read them back. If someone wants to
book, say you can do that and ask what day and time they would like.
Keep replies to 2-4 sentences unless the question genuinely needs more."""

CLINIC_SYSTEM_PROMPT = """You are the front-desk AI receptionist for {name}, a dental clinic.
Be warm, brief, and helpful. You help with opening hours, services, booking
and moving appointments, and getting a message to the team. You are not a
dentist: never diagnose, never recommend medicines or treatment, and never
quote prices. For pain, swelling or an emergency, tell the person to ask for a
person (or to call 000 if it is severe). If you do not know something about the
clinic, say so and offer to flag the message for the team.
Never say an appointment is booked, confirmed, moved or cancelled: bookings are
only made through the booking steps, which ask for the day and time, the
person's name, phone number and email, and read them back. If someone wants to
book, say you can do that and ask what day and time they would like.
Keep replies to 2-4 sentences unless the question genuinely needs more."""


def _system_prompt() -> str:
    import os

    if os.environ.get("BRAND_MODE", "").strip().lower() == "clinic":
        return CLINIC_SYSTEM_PROMPT.format(name=os.environ.get("BRAND_NAME", "").strip() or "the clinic")
    return RECEPTIONIST_SYSTEM_PROMPT


APPOINTMENT_EXTRACT_PROMPT = """Extract appointment details from the user's message.
Today's date/time is: {now} ({timezone}).

Return ONLY a JSON object, no other text, in exactly this shape:
{{"summary": "<short title>", "start": "<ISO 8601 local, e.g. 2026-08-10T14:00:00>", "end": "<ISO 8601 local>", "clarify": null}}

If the message is missing a specific date, time, or what the appointment
is for, instead return:
{{"summary": null, "start": null, "end": null, "clarify": "<a short question asking for exactly what's missing>"}}

Default appointment length is 30 minutes if no duration is given.
Do not invent a date/time if none was given — ask via "clarify" instead.

User message: "{message}"
"""

_ESCALATE_KEYWORDS = {
    "human", "person", "representative", "manager", "escalate",
    "someone else", "real person", "speak to someone", "talk to someone",
}
# A dental emergency is flagged for the team straight away, whatever else is asked.
_URGENT_KEYWORDS = (
    "emergency", "urgent", "toothache", "tooth ache", "tooth pain", "severe pain",
    "knocked out", "knocked-out", "broken tooth", "swelling", "swollen", "bleeding", "abscess",
)
_CALLBACK_PHRASES = (
    "call me back", "call back", "callback", "ring me", "phone me", "give me a call", "call me",
)
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
# "How do I book?" is a question for the FAQ; "can you book me in?" is a
# request, and goes straight to the booking steps.
_HOW_TO_BOOK = re.compile(r"\bhow (?:do|can|would|should) (?:i|we|you)\b|\bhow to\b|\bcan i book online\b")
_BOOKING_REQUEST = re.compile(
    r"\bbook(?:ing)? (?:me|us|a|an|in|my|for)\b"
    r"|\b(?:make|schedule|arrange|set up|get|need|want|like|have) (?:an? |my |the )?"
    r"(?:appointment|booking|check-?up|clean(?:ing)?|consult(?:ation)?|visit)\b"
    r"|\bemergency booking\b|\bappointment for\b"
)

_APPOINTMENT_KEYWORDS = {
    "book", "appointment", "schedule", "meeting", "reserve",
    "reservation", "consult", "consultation", "book me", "set up a call",
}


# PROJ-478: a half-finished booking survives side questions (parking, pricing,
# what to bring) for this long. In process memory, so it resets on a restart,
# which is fine for a conversation that lasts minutes.
_PENDING_BOOKING_TTL = 30 * 60
_CANCEL_BOOKING_PHRASES = (
    "never mind", "nevermind", "forget it", "forget the booking", "cancel the booking",
    "don't book", "do not book", "no booking", "stop booking",
)


# ── Collecting the patient's details for a booking ───────────────
# After the day and time are known, the receptionist asks for a name, a
# phone number and an email, reads them back, and only books on a "yes".
_COLLECT_STAGES = ("name", "phone", "email", "confirm", "change")

_QUESTION_START = re.compile(
    r"^(what|where|when|how|why|who|which|can|could|do|does|is|are|will|should|would)\b", re.I
)
_YES_START = re.compile(r"^(yes|yeah|yep|yup|correct|sure|ok|okay|perfect|right|confirm|confirmed)\b")
_NO_RE = re.compile(r"\b(no|nope|nah|wrong|incorrect|not right|not correct|change|mistake)\b")
_YES_RE = re.compile(
    r"\b(yes|yeah|yep|yup|correct|that's right|that is right|sounds good|perfect|"
    r"sure|ok|okay|all good|book it|go ahead|confirm)\b"
)
_NAME_LEAD = re.compile(
    r"^(?:(?:hi|hello|yes|yeah|ok|okay|sure)[,.\s]+)?"
    r"(?:my name is|my name's|the name is|name is|it's|it is|this is|i am|i'm|im|call me|"
    r"put it under|under the name|under)\s+",
    re.I,
)
_DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "nought": "0", "one": "1", "two": "2",
    "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9",
}
_SAME_NUMBER = (
    "this number", "same number", "this one", "same one", "calling from",
    "texting from", "number i'm on", "number im on", "use my number",
)
_EMAIL_FOUND = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+")
_EMAIL_OK = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}$")
_EMAIL_LEAD = re.compile(
    r"^(?:(?:yes|yeah|ok|okay|sure)[,.\s]+)?(?:(?:my|the)\s+)?"
    r"(?:email|e-mail)(?:\s+address)?\s+(?:is\s+)?|^(?:it's|it is)\s+",
    re.I,
)
_NO_EMAIL = re.compile(
    r"\b(no email|no e-mail|don't have (?:an )?email|do not have (?:an )?email|"
    r"no thanks|skip|none|no)\b"
)


def _looks_like_question(message: str) -> bool:
    m = message.strip()
    return m.endswith("?") or bool(_QUESTION_START.match(m))


def _yes_or_no(message: str) -> str | None:
    m = re.sub(r"[^\w\s']", " ", message.lower()).strip()
    if _YES_START.match(m) and not re.match(r"^(right|confirm)\b.*\b(no|not|wrong)\b", m):
        return "yes"
    if _NO_RE.search(m):
        return "no"
    if _YES_RE.search(m):
        return "yes"
    return None


def _parse_name(message: str) -> str | None:
    text = message.strip().strip(".!?,")
    text = _NAME_LEAD.sub("", text).strip(" ,.!?")
    text = re.sub(r"[,\s]+(?:please|thanks|thank you)$", "", text, flags=re.I).strip()
    if not text or len(text) > 60 or re.search(r"[\d@]", text):
        return None
    words = text.split()
    if len(words) > 5:
        return None
    return " ".join(w[0].upper() + w[1:] if w.islower() else w for w in words)


def _spoken_digits(message: str) -> str:
    """'zero four one two, double three...' -> '041233...'. Digits already
    written as digits are kept as they are."""
    out, repeat = [], 1
    for tok in re.findall(r"\+|\d+|[a-z]+", message.lower()):
        if tok in ("double", "triple"):
            repeat = 2 if tok == "double" else 3
            continue
        if tok == "+":
            out.append("+")
        elif tok.isdigit():
            out.append(tok[0] * repeat + tok[1:])
        elif tok in _DIGIT_WORDS:
            out.append(_DIGIT_WORDS[tok] * repeat)
        else:
            continue
        repeat = 1
    return "".join(out)


def _parse_phone(message: str, own_number: str | None = None) -> str | None:
    """A phone number in E.164 (+61412345678), or None if it doesn't look like
    one. "This number" means the number the person is calling or texting from."""
    m = message.lower()
    written = re.sub(r"[^\d+]", "", message)
    candidate = written if len(written.lstrip("+")) >= 8 else _spoken_digits(message)
    if len(candidate.lstrip("+")) < 8:
        if own_number and (any(p in m for p in _SAME_NUMBER) or _yes_or_no(message) == "yes"):
            candidate = own_number
        else:
            return None
    try:
        phone = normalise_phone(candidate)
    except ValueError:
        return None
    return phone if 9 <= len(phone.lstrip("+")) <= 15 else None


def _parse_email(message: str) -> str | None:
    text = message.strip().lower()
    found = _EMAIL_FOUND.search(text)
    if found and _EMAIL_OK.match(found.group(0)):
        return found.group(0)
    spoken = _EMAIL_LEAD.sub("", text).strip(" .")
    spoken = re.sub(r"\s+at the rate(?: of)?\s+|\s+at\s+", "@", spoken)
    spoken = re.sub(r"\s*\b(?:dot|full stop|period)\b\s*", ".", spoken)
    spoken = re.sub(r"\s*\bunderscore\b\s*", "_", spoken)
    spoken = re.sub(r"\s*\b(?:dash|hyphen)\b\s*", "-", spoken)
    spoken = re.sub(r"\s*\bplus\b\s*", "+", spoken)
    spoken = re.sub(r"\s+", "", spoken).strip(".")
    return spoken if _EMAIL_OK.match(spoken) else None


def _which_field(message: str) -> str | None:
    m = message.lower()
    if "email" in m or "e-mail" in m:
        return "email"
    if any(k in m for k in ("phone", "number", "mobile")):
        return "phone"
    if "name" in m:
        return "name"
    if any(k in m for k in ("time", "date", "day", "when", "appointment", "tomorrow", "week")) or re.search(
        r"\d|monday|tuesday|wednesday|thursday|friday|saturday|sunday", m
    ):
        return "time"
    return None


class Receptionist:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.memory = SessionMemory()
        self._pending_bookings: dict[str, dict] = {}
        self._pending_reschedules: dict[str, dict] = {}
        self._pending_callbacks: dict[str, float] = {}

    # ── Main entry point ─────────────────────────────────────────
    def handle(
        self,
        message: str,
        session_id: str | None = None,
        contact_channel: str | None = None,
        contact_address: str | None = None,
        org_id: int | None = None,
    ) -> dict:
        """Returns {"answer": str, "intent": str, ...extra fields}.
        org_id is the clinic the conversation belongs to; bookings are saved
        under it so they show in that clinic's Calendar tab.
        contact_channel/contact_address (e.g. "sms"/"+15551234567") are
        optional — when the caller can supply them (Twilio always
        knows the caller's number), a successful appointment booking
        also schedules a reminder ahead of it (PROJ-445/446). Omit them
        and booking still works, just without the auto-reminder."""
        message = (message or "").strip()
        if not message:
            return {"answer": "Sorry, I didn't catch that — could you say that again?", "intent": "general"}

        pending = self._get_pending(session_id)
        # Mid-booking, the reply is a name, number, email or yes/no, so it
        # skips reschedule, call-back, FAQ and (for an email address) hand-off checks.
        stage = pending.get("stage", "details") if pending else None
        collecting = stage in _COLLECT_STAGES

        pending_reschedule = None if collecting else self._get_pending_reschedule(
            session_id, contact_channel, contact_address
        )
        if (self._wants_reschedule(message) and not collecting) or pending_reschedule:
            result = self._handle_reschedule(
                message, session_id, contact_channel, contact_address
            )
            self.memory.save_context(
                message,
                "receptionist_reschedule",
                result.get("answer", ""),
                session_id=session_id,
            )
            return result

        # 0. Walking away from a half-finished booking (PROJ-478)
        if pending and self._cancels_booking(message):
            self._pending_bookings.pop(self._pending_key(session_id), None)
            answer = "No problem, I've dropped that booking. Is there anything else I can help with?"
            self.memory.save_context(message, "receptionist_general", answer, session_id=session_id)
            return {"answer": answer, "intent": "general"}

        # 0b. Call-backs and emergencies go to the team before anything else, so
        # "book me a call back" or "emergency booking" are not mistaken for an
        # ordinary appointment or a FAQ question.
        callback = None if collecting else self._handle_callback(
            message, session_id, contact_channel, contact_address
        )
        if callback:
            self.memory.save_context(message, "receptionist_escalate", callback["answer"], session_id=session_id)
            return callback

        urgent_notice = ""
        if self._is_urgent(message):
            self._log_escalation(
                message, session_id, label="URGENT", priority="high",
                contact=self._callback_number(message, contact_channel, contact_address),
            )
            urgent_notice = (
                "I'm sorry you're dealing with this. I've flagged it as urgent for our team "
                "and they will follow up as soon as possible. If you have severe swelling "
                "affecting your breathing or swallowing, heavy bleeding, or a head injury, "
                "call 000 now."
            )
            if not (pending or self._wants_appointment(message)):
                answer = urgent_notice + " If you would like the earliest time we have, tell me a day and time and I will book it."
                self.memory.save_context(message, "receptionist_escalate", answer, session_id=session_id)
                return {"answer": answer, "intent": "escalate", "urgent": True}

        # 1. FAQ lookup first (PROJ-214: KB before skill routing)
        # With a booking open, "let me talk to a person" hands off straight
        # away instead of getting the FAQ blurb about how to ask for one.
        lowered = message.lower()
        booking_request = (not pending and bool(_BOOKING_REQUEST.search(lowered))
                           and not _HOW_TO_BOOK.search(lowered))
        # With a booking open, only a real question ("where do I park?") is a
        # side question for the FAQ; "a check-up at 10am" is the next detail.
        faq_hit = None if (
            collecting or booking_request
            or (pending and (self._wants_human(message) or not _looks_like_question(message)))
        ) else find_answer(message)
        if faq_hit:
            answer = faq_hit["answer"]
            result = {"intent": "faq", "faq_score": faq_hit["score"]}
            if pending:
                # PROJ-478: answer the question, then steer back to the booking
                answer += f"\n\nWhenever you're ready, we can finish your booking. {pending['ask']}"
                result["booking_pending"] = True
            self.memory.save_context(message, "receptionist_faq", answer, session_id=session_id)
            result["answer"] = answer
            return result

        # 2. Escalation
        if self._wants_human(message) and stage != "email":
            self._pending_bookings.pop(self._pending_key(session_id), None)
            answer = (
                "I've flagged this conversation for our team — someone will "
                "follow up with you shortly. Is there anything else I can help "
                "with in the meantime?"
            )
            self._log_escalation(message, session_id)
            self.memory.save_context(message, "receptionist_escalate", answer, session_id=session_id)
            return {"answer": answer, "intent": "escalate"}

        # 3. Appointment booking. With a booking in progress, any other reply
        # is the next piece of it ("Friday at 10 for a check-up"), so earlier
        # booking messages are combined with this one (PROJ-478).
        if pending or self._wants_appointment(message):
            result = self._booking_step(
                message, pending, session_id, contact_channel, contact_address, org_id
            )
            if urgent_notice:
                result["answer"] = urgent_notice + "\n\n" + result["answer"]
                result["urgent"] = True
            return result

        # 4. General conversation fallback
        answer = self._general_reply(message, session_id)
        self.memory.save_context(message, "receptionist_general", answer, session_id=session_id)
        return {"answer": answer, "intent": "general"}

    # ── Booking in progress (PROJ-478) ───────────────────────────
    def booking_question(self, session_id: str | None) -> str | None:
        """The question a half-finished booking is waiting on, or None."""
        pending = self._get_pending(session_id)
        return pending.get("ask") if pending else None

    def booking_stage(self, session_id: str | None) -> str | None:
        pending = self._get_pending(session_id)
        return pending.get("stage", "details") if pending else None

    def hand_booking_to_team(self, session_id: str | None, contact: str | None) -> None:
        """The call couldn't finish the booking (Twilio kept hearing nothing):
        drop it and flag a call-back with whatever was collected."""
        pending = self._pending_bookings.pop(self._pending_key(session_id), None) or {}
        details = pending.get("details") or {}
        parts = ["Caller wanted to book but the call couldn't hear their answers"]
        if details:
            parts.append(f"{details.get('summary')} on {bookings.when_text(details.get('start', ''))}")
        if pending.get("name"):
            parts.append(f"name {pending['name']}")
        self._log_escalation("; ".join(parts), session_id, label="BOOKING CALL-BACK", contact=contact)

    @staticmethod
    def _pending_key(session_id: str | None) -> str:
        return session_id or "_default"

    def _get_pending(self, session_id: str | None) -> dict | None:
        key = self._pending_key(session_id)
        pending = self._pending_bookings.get(key)
        if pending and time.time() - pending["ts"] > _PENDING_BOOKING_TTL:
            del self._pending_bookings[key]
            return None
        return pending

    @staticmethod
    def _cancels_booking(message: str) -> bool:
        m = message.lower()
        return any(p in m for p in _CANCEL_BOOKING_PHRASES)

    # ── Intent keyword pre-checks ────────────────────────────────
    def _wants_human(self, message: str) -> bool:
        m = message.lower()
        return any(k in m for k in _ESCALATE_KEYWORDS)

    def _wants_appointment(self, message: str) -> bool:
        m = message.lower()
        return any(k in m for k in _APPOINTMENT_KEYWORDS)

    # ── Urgent and call-back requests ────────────────────────────
    @staticmethod
    def _is_urgent(message: str) -> bool:
        m = message.lower()
        if "not urgent" in m or "non-urgent" in m or "non urgent" in m:
            return False
        return any(k in m for k in _URGENT_KEYWORDS)

    @staticmethod
    def _wants_callback(message: str) -> bool:
        m = message.lower()
        return any(k in m for k in _CALLBACK_PHRASES)

    @staticmethod
    def _callback_number(message: str, contact_channel: str | None, contact_address: str | None) -> str | None:
        """The number to call back: the one in the message, else the caller's own
        (Twilio always knows it for texts and calls)."""
        found = _PHONE_RE.search(message or "")
        if found:
            return " ".join(found.group(0).split())
        if contact_channel in ("sms", "voice") and contact_address:
            return contact_address
        return None

    def _handle_callback(
        self, message: str, session_id: str | None, contact_channel: str | None, contact_address: str | None
    ) -> dict | None:
        key = self._pending_key(session_id)
        waiting = self._pending_callbacks.get(key)
        if waiting and time.time() - waiting > _PENDING_BOOKING_TTL:
            self._pending_callbacks.pop(key, None)
            waiting = None

        if not (waiting or self._wants_callback(message)):
            return None

        number = self._callback_number(message, contact_channel, contact_address)
        if number is None:
            self._pending_callbacks[key] = time.time()
            return {
                "answer": "Happy to arrange a call back. What number should our team call you on?",
                "intent": "escalate",
            }

        self._pending_callbacks.pop(key, None)
        self._log_escalation(
            message, session_id, label="CALL BACK", priority="high" if self._is_urgent(message) else "normal",
            contact=number,
        )
        return {
            "answer": f"I've asked our team to call you back on {number}. They will ring you on the next working day, "
            "or sooner if it is urgent. Is there anything else I can help with?",
            "intent": "escalate",
        }

    # ── Escalation logging ───────────────────────────────────────
    def _log_escalation(
        self,
        message: str,
        session_id: str | None,
        label: str | None = None,
        priority: str = "normal",
        contact: str | None = None,
    ) -> None:
        reason = message
        if label:
            reason = f"{label}: {message}"
            if contact and contact not in message:
                reason += f" (call {contact})"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),  # the dashboard reads this as UTC
            "session_id": session_id or "unknown",
            "message": message,
            "reason": reason,
            "priority": priority,
        }
        if contact:
            entry["contact"] = contact
        try:
            import os

            os.makedirs(os.path.dirname(ESCALATION_LOG), exist_ok=True)
            with open(ESCALATION_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # don't fail the user-facing reply just because logging failed

    # ── Appointment booking ──────────────────────────────────────
    @staticmethod
    def _reschedule_key(
        session_id: str | None,
        contact_channel: str | None,
        contact_address: str | None,
    ) -> str:
        if contact_channel and contact_address:
            return (
                f"contact:{contact_channel.strip().lower()}:"
                f"{contact_address.strip().lower()}"
            )
        return session_id or "_default"

    def _get_pending_reschedule(
        self,
        session_id: str | None,
        contact_channel: str | None,
        contact_address: str | None,
    ) -> dict | None:
        key = self._reschedule_key(session_id, contact_channel, contact_address)
        pending = self._pending_reschedules.get(key)
        if pending and time.time() - pending["ts"] > _PENDING_BOOKING_TTL:
            del self._pending_reschedules[key]
            return None
        return pending

    @staticmethod
    def _wants_reschedule(message: str) -> bool:
        text = (message or "").lower()
        phrases = (
            "reschedule", "rescheduling", "move my appointment",
            "move the appointment", "move my booking",
            "change my appointment", "change the appointment",
            "change my booking", "can't do", "cannot do",
            "can't make", "cannot make", "won't make it",
            "will not make it", "different time", "change the time",
        )
        if any(phrase in text for phrase in phrases):
            return True
        if "what about" in text:
            date_terms = (
                "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday", "morning",
                "afternoon", "evening", "tomorrow", "next week",
            )
            return any(term in text for term in date_terms)
        return False

    @staticmethod
    def _event_datetime(event: dict, field: str) -> str | None:
        value = event.get(field) or {}
        return value.get("dateTime") or value.get("date")

    @staticmethod
    def _select_reschedule_event(events: list[dict], message: str) -> dict | None:
        if len(events) == 1:
            return events[0]

        text = re.sub(r"[^a-z0-9]+", " ", (message or "").lower()).strip()
        ignored = {
            "appointment", "booking", "book", "move", "change",
            "reschedule", "please", "the", "my", "that", "one",
        }
        matches = []

        for event in events:
            summary = str(event.get("summary") or "").lower()
            normal = re.sub(r"[^a-z0-9]+", " ", summary).strip()
            tokens = [
                token for token in normal.split()
                if len(token) >= 4 and token not in ignored
            ]
            if normal and normal in text:
                matches.append(event)
            elif any(
                re.search(rf"\b{re.escape(token)}\b", text)
                for token in tokens
            ):
                matches.append(event)

        return matches[0] if len(matches) == 1 else None

    def _extract_reschedule_start(self, message: str, event: dict) -> dict:
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        old_start = self._event_datetime(event, "start") or "unknown"
        prompt = (
            "Extract the NEW proposed start date and time for an existing appointment.\n"
            f"Today's date/time is {now} in {TIMEZONE}.\n"
            f"Existing appointment: {event.get('summary') or 'appointment'}, "
            f"currently at {old_start}.\n"
            'Return only JSON: {"start": "YYYY-MM-DDTHH:MM:SS", "clarify": null}.\n'
            "If the user gives only a vague part of day, such as Friday morning "
            "without an hour, or omits a definite date or time, return start:null "
            "and ask a short clarification. Never invent the hour or date. "
            "Resolve clearly stated relative dates using today's date.\n"
            f"User message: {message}"
        )

        try:
            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=160,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(
                r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE
            ).strip()
            data = json.loads(raw)
        except Exception:
            return {"clarify": "What exact date and time would suit you instead?"}

        if not isinstance(data, dict) or not data.get("start"):
            clarify = data.get("clarify") if isinstance(data, dict) else None
            return {
                "clarify": clarify or "What exact date and time would suit you instead?"
            }

        try:
            datetime.fromisoformat(str(data["start"]).replace("Z", "+00:00"))
        except ValueError:
            return {"clarify": "What exact date and time would suit you instead?"}

        return data

    def _handle_reschedule(
        self,
        message: str,
        session_id: str | None,
        contact_channel: str | None = None,
        contact_address: str | None = None,
    ) -> dict:
        key = self._reschedule_key(
            session_id, contact_channel, contact_address
        )
        pending = self._get_pending_reschedule(
            session_id, contact_channel, contact_address
        )
        request_message = message

        if not contact_channel or not contact_address:
            return {
                "answer": (
                    "To find your existing appointment safely, please contact "
                    "us through the same phone number or email address used "
                    "when booking."
                ),
                "intent": "reschedule",
                "rescheduled": False,
                "needs_info": True,
            }

        if not calendar_configured():
            self._pending_reschedules.pop(key, None)
            return {
                "answer": (
                    "I can't access the booking calendar right now, so I "
                    "haven't changed anything. Please contact our team."
                ),
                "intent": "reschedule",
                "rescheduled": False,
            }

        if pending and pending.get("event"):
            event = pending["event"]
            request_message = " ".join(
                part for part in (pending.get("request_message"), message) if part
            )
        else:
            if pending and pending.get("events"):
                events = pending["events"]
                request_message = " ".join(
                    part for part in (pending.get("request_message"), message) if part
                )
            else:
                lookup = find_upcoming_appointments(
                    contact_channel, contact_address
                )
                if not lookup.get("ok"):
                    self._pending_reschedules.pop(key, None)
                    return {
                        "answer": (
                            "I couldn't check the booking calendar just now, "
                            "so I haven't changed anything. Please try again shortly."
                        ),
                        "intent": "reschedule",
                        "rescheduled": False,
                    }
                events = lookup.get("events", [])

            if not events:
                self._pending_reschedules.pop(key, None)
                return {
                    "answer": (
                        "I couldn't find an upcoming appointment linked to "
                        "this contact. I haven't made any changes. Would you "
                        "like help making a new booking?"
                    ),
                    "intent": "reschedule",
                    "rescheduled": False,
                }

            event = self._select_reschedule_event(events, message)
            if event is None:
                self._pending_reschedules[key] = {
                    "events": events,
                    "kind": "select_event",
                    "request_message": request_message,
                    "ts": time.time(),
                }
                options = []
                for item in events[:5]:
                    start = self._event_datetime(item, "start") or "date unavailable"
                    options.append(
                        f"{item.get('summary') or 'Appointment'} "
                        f"({start.replace('T', ' ')[:16]})"
                    )
                return {
                    "answer": (
                        "I found more than one upcoming appointment. "
                        "Which one would you like to move? "
                        + "; ".join(options)
                        + "."
                    ),
                    "intent": "reschedule",
                    "rescheduled": False,
                    "needs_info": True,
                }

        old_start = self._event_datetime(event, "start")
        old_end = self._event_datetime(event, "end")
        event_id = event.get("id")

        if (
            not event_id
            or not old_start
            or not old_end
            or "T" not in old_start
            or "T" not in old_end
        ):
            self._pending_reschedules[key] = {
                "event": event,
                "kind": "target_time",
                "request_message": request_message,
                "ts": time.time()
            }
            return {
                "answer": (
                    "I found the appointment, but it doesn't contain enough "
                    "timed-event details for me to move it safely. Please "
                    "contact our team for help."
                ),
                "intent": "reschedule",
                "rescheduled": False,
            }

        extracted = self._extract_reschedule_start(request_message, event)
        if extracted.get("clarify") or not extracted.get("start"):
            self._pending_reschedules[key] = {
                "event": event,
                "kind": "target_time",
                "request_message": request_message,
                "ts": time.time()
            }
            return {
                "answer": (
                    extracted.get("clarify")
                    or "What exact date and time would suit you instead?"
                ),
                "intent": "reschedule",
                "rescheduled": False,
                "needs_info": True,
            }

        try:
            old_start_dt = datetime.fromisoformat(
                old_start.replace("Z", "+00:00")
            )
            old_end_dt = datetime.fromisoformat(
                old_end.replace("Z", "+00:00")
            )
            proposed_start = datetime.fromisoformat(
                str(extracted["start"]).replace("Z", "+00:00")
            )
            duration = old_end_dt - old_start_dt
            if duration.total_seconds() <= 0:
                duration = timedelta(minutes=30)
            proposed_end = proposed_start + duration
        except (ValueError, TypeError):
            self._pending_reschedules[key] = {
                "event": event,
                "kind": "target_time",
                "request_message": request_message,
                "ts": time.time()
            }
            return {
                "answer": (
                    "I couldn't safely interpret the appointment times. "
                    "What exact date and time would suit you instead?"
                ),
                "intent": "reschedule",
                "rescheduled": False,
                "needs_info": True,
            }

        moved = update_appointment(
            event_id=event_id,
            start_iso=proposed_start.isoformat(),
            end_iso=proposed_end.isoformat(),
            timezone=TIMEZONE,
        )
        if not moved.get("ok"):
            self._pending_reschedules.pop(key, None)
            return {
                "answer": (
                    "I couldn't move the appointment on the calendar, so "
                    "its time is unchanged. Please try again or contact our team."
                ),
                "intent": "reschedule",
                "rescheduled": False,
            }

        reminder_update = reschedule_reminders_for_booking(
            booking_id=event_id,
            summary=str(event.get("summary") or "Appointment"),
            start_iso=proposed_start.isoformat(),
        )
        self._pending_reschedules.pop(key, None)

        answer = (
            f"Your appointment, **{event.get('summary') or 'Appointment'}**, "
            f"has been moved to "
            f"{proposed_start.strftime('%A %d %B at %I:%M %p').replace(' 0', ' ')}."
        )
        if moved.get("event_url"):
            answer += f" [View updated event]({moved['event_url']})"
        if reminder_update.get("ok") and reminder_update.get("updated", 0) > 0:
            answer += " Your existing reminder has also been updated."
        elif not reminder_update.get("ok"):
            answer += (
                " However, I couldn't update the linked reminder; "
                "please contact our team to check it."
            )

        return {
            "answer": answer,
            "intent": "reschedule",
            "rescheduled": True,
            "event_id": event_id,
            "reminders_updated": reminder_update.get("updated", 0),
        }

    def _booking_step(
        self,
        message: str,
        pending: dict | None,
        session_id: str | None,
        contact_channel: str | None,
        contact_address: str | None,
        org_id: int | None,
    ) -> dict:
        """One turn of the booking conversation. The order is: what and when,
        then name, phone number and email, then a read-back. Nothing is saved
        until the person says yes."""
        state = dict(pending) if pending else {"messages": [], "stage": "details"}
        state.setdefault("messages", [])
        stage = state.get("stage", "details")
        own_number = contact_address if contact_channel in ("voice", "sms") else None

        # A question in the middle of the details ("where do I park?") gets an
        # answer, then the same question is asked again.
        if stage in ("name", "phone", "email") and _looks_like_question(message):
            hit = find_answer(message)
            lead = hit["answer"] + "\n\n" if hit else "Sorry, I just need this to finish the booking. "
            return self._ask(state, state.get("ask") or "", session_id, message, prefix=lead)

        if stage == "details":
            combined = " ".join(state["messages"] + [message])
            extracted = self._extract_appointment(combined)
            state["messages"] = state["messages"] + [message]
            if extracted.get("clarify"):
                return self._ask(state, extracted["clarify"], session_id, message)
            state["details"] = {k: extracted[k] for k in ("summary", "start", "end")}
            return self._next_question(state, session_id, message, contact_channel, own_number)

        if stage == "name":
            name = _parse_name(message)
            if not name:
                return self._ask(state, "Sorry, I didn't catch that. What name should I put the booking under?",
                                 session_id, message)
            state["name"] = name
            return self._next_question(state, session_id, message, contact_channel, own_number)

        if stage == "phone":
            phone = _parse_phone(message, own_number)
            if not phone:
                return self._ask(state, "Sorry, I didn't get that number. Could you say the phone number again, "
                                 "digit by digit?", session_id, message)
            state["phone"] = phone
            return self._next_question(state, session_id, message, contact_channel, own_number)

        if stage == "email":
            email = _parse_email(message)
            if email is None and _NO_EMAIL.search(message.lower()):
                email = ""
            if email is None:
                example = " For example: john dot smith at gmail dot com." if contact_channel == "voice" else ""
                return self._ask(state, "Sorry, I didn't get that email address. Could you say it again?" + example
                                 + " Or say no email to skip it.", session_id, message)
            state["email"] = email
            return self._next_question(state, session_id, message, contact_channel, own_number)

        if stage == "confirm":
            answer = _yes_or_no(message)
            if answer == "yes":
                return self._finish_booking(state, session_id, message, contact_channel, contact_address, org_id)
            if answer == "no":
                state["stage"] = "change"
                return self._ask(state, "No problem. What would you like to change: the day and time, your name, "
                                 "your phone number or your email?", session_id, message)
            return self._ask(state, self._readback(state), session_id, message)

        if stage == "change":
            field = _which_field(message)
            if field == "time":
                summary = state["details"]["summary"]
                state.pop("details", None)
                state["messages"] = [f"Booking a {summary}."]
                state["stage"] = "details"
                if re.search(r"\d|monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next",
                             message.lower()):
                    return self._booking_step(message, state, session_id, contact_channel, contact_address, org_id)
                return self._ask(state, "Sure. What day and time would you like instead?", session_id, message)
            if field in ("name", "phone", "email"):
                state.pop(field, None)
                # "change my email to anna@example.com" carries the new value already
                parsed = {"name": None, "phone": _parse_phone(message), "email": _parse_email(message)}[field]
                if parsed:
                    state[field] = parsed
                    return self._next_question(state, session_id, message, contact_channel, own_number)
                return self._next_question(state, session_id, message, contact_channel, own_number)
            return self._ask(state, "What would you like to change: the day and time, your name, your phone "
                             "number or your email?", session_id, message)

        # Unknown stage (should not happen): start again cleanly.
        self._pending_bookings.pop(self._pending_key(session_id), None)
        return self._booking_step(message, None, session_id, contact_channel, contact_address, org_id)

    def _next_question(self, state: dict, session_id, message, contact_channel, own_number) -> dict:
        details = state["details"]
        when = bookings.when_text(details["start"])
        if "name" not in state:
            state["stage"] = "name"
            return self._ask(state, f"Great, that's a {bookings.in_sentence(details['summary'])} on {when}. "
                             "What's your full name?",
                             session_id, message)
        if "phone" not in state:
            state["stage"] = "phone"
            first = state["name"].split()[0]
            question = f"Thanks, {first}. What's the best phone number to reach you?"
            if own_number:
                verb = "calling" if contact_channel == "voice" else "texting"
                question += f" You can say this number to use the one you're {verb} from."
            return self._ask(state, question, session_id, message)
        if "email" not in state:
            state["stage"] = "email"
            question = "And your email address, so I can send the confirmation there too?"
            if contact_channel == "voice":
                question += " For example: john dot smith at gmail dot com."
            question += " If you'd rather not, just say no email."
            return self._ask(state, question, session_id, message)
        state["stage"] = "confirm"
        return self._ask(state, self._readback(state), session_id, message)

    @staticmethod
    def _readback(state: dict) -> str:
        details = state["details"]
        email = state.get("email") or ""
        return (
            "Let me check I have that right: "
            f"{bookings.in_sentence(details['summary'])} on {bookings.when_text(details['start'])}, "
            f"for {state['name']}, phone {bookings.phone_text(state['phone'])}, "
            + (f"email {email}" if email else "no email")
            + ". Is that correct?"
        )

    def _ask(self, state: dict, question: str, session_id, message, prefix: str = "") -> dict:
        state["ask"] = question
        state["ts"] = time.time()
        self._pending_bookings[self._pending_key(session_id)] = state
        answer = prefix + question
        self.memory.save_context(message, "receptionist_appointment", answer, session_id=session_id)
        return {
            "answer": answer, "intent": "appointment", "booked": False,
            "needs_info": True, "expect": state.get("stage", "details"),
        }

    def _finish_booking(self, state, session_id, message, contact_channel, contact_address, org_id) -> dict:
        details = state["details"]
        booking, token = bookings.create_booking(
            summary=details["summary"], start_local=details["start"], end_local=details["end"],
            name=state["name"], phone=state["phone"], email=state.get("email") or "",
            org_id=org_id, channel=contact_channel or "web", session_id=session_id,
        )
        self._pending_bookings.pop(self._pending_key(session_id), None)
        bookings.notify_in_background(booking, token)

        # Optional: mirror to Google Calendar when the clinic has connected one.
        event_url = None
        if calendar_configured():
            identity = {}
            if contact_channel and contact_address:
                identity = {"contact_channel": contact_channel, "contact_address": contact_address}
            try:
                mirrored = book_appointment(
                    summary=f"{details['summary']} - {state['name']} (unconfirmed)",
                    start_iso=details["start"], end_iso=details["end"], timezone=TIMEZONE, **identity,
                )
                event_url = mirrored.get("event_url") if mirrored.get("ok") else None
            except Exception:  # noqa: BLE001 - the booking is already saved
                event_url = None

        first = state["name"].split()[0]
        sent = "a text and an email" if state.get("email") else "a text"
        answer = (
            f"All done, {first}. Your {bookings.in_sentence(details['summary'])} on "
            f"{bookings.when_text(details['start'])} "
            f"is booked, but not confirmed yet. I'm sending you {sent} with a link to confirm it. "
            "Once you confirm, it's locked in."
        )
        if not contact_channel:
            # Web chat: show the link straight away, plus the .ics download.
            answer += (
                f" [Confirm the appointment]({bookings.confirm_url(token)})"
                f" · [Add to your own calendar]({self._ics_link(details)})"
            )
        self.memory.save_context(message, "receptionist_appointment", answer, session_id=session_id)
        return {
            "answer": answer, "intent": "appointment", "booked": True,
            "booking_id": booking["id"], "status": booking["status"], "event_url": event_url,
        }

    def _ics_link(self, extracted: dict) -> str:
        from urllib.parse import urlencode

        params = {"summary": extracted["summary"], "start": extracted["start"], "end": extracted["end"]}
        return f"/calendar/ics?{urlencode(params)}"

    def _extract_appointment(self, message: str) -> dict:
        """Ask Claude to pull structured date/time/summary out of the
        message. Single-turn — if info is missing we ask a clarifying
        question and expect the user's next message to restate
        everything, rather than tracking multi-turn slot-filling state.
        That's a real scope limitation, noted honestly rather than
        faked with silent guesses at a date/time nobody gave us."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        prompt = APPOINTMENT_EXTRACT_PROMPT.format(now=now, timezone=TIMEZONE, message=message)

        try:
            resp = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            # Claude sometimes wraps JSON in ```json fences despite instructions
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            data = json.loads(raw)
        except Exception:
            # Covers Claude API errors, malformed JSON, and any
            # unexpected response shape — all treated the same way:
            # ask the user rather than guess at a date/time.
            return {
                "clarify": "What date and time would you like, and what's the appointment for?"
            }

        if not data.get("start") or not data.get("summary"):
            return {"clarify": data.get("clarify") or "What date and time would you like, and what's the appointment for?"}

        return data

    # ── General conversation ─────────────────────────────────────
    def _general_reply(self, message: str, session_id: str | None) -> str:
        context = self.memory.get_context_string(last_n=4, session_id=session_id)
        try:
            resp = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=250,
                system=_system_prompt(),
                messages=[
                    {
                        "role": "user",
                        "content": f"Recent conversation:\n{context}\n\nUser: {message}",
                    }
                ],
            )
            return resp.content[0].text.strip()
        except Exception as exc:
            return f"Sorry, I'm having trouble responding right now ({exc}). Please try again in a moment."
