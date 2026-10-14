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
#                                                time, then Calendar API
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
from agent.faq import find_answer
from agent.memory import SessionMemory
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
Keep replies to 2-4 sentences unless the question genuinely needs more."""

CLINIC_SYSTEM_PROMPT = """You are the front-desk AI receptionist for {name}, a dental clinic.
Be warm, brief, and helpful. You help with opening hours, services, booking
and moving appointments, and getting a message to the team. You are not a
dentist: never diagnose, never recommend medicines or treatment, and never
quote prices. For pain, swelling or an emergency, tell the person to ask for a
person (or to call 000 if it is severe). If you do not know something about the
clinic, say so and offer to flag the message for the team.
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
    ) -> dict:
        """Returns {"answer": str, "intent": str, ...extra fields}.
        contact_channel/contact_address (e.g. "sms"/"+15551234567") are
        optional — when the caller can supply them (Twilio always
        knows the caller's number), a successful appointment booking
        also schedules a reminder ahead of it (PROJ-445/446). Omit them
        and booking still works, just without the auto-reminder."""
        message = (message or "").strip()
        if not message:
            return {"answer": "Sorry, I didn't catch that — could you say that again?", "intent": "general"}

        pending_reschedule = self._get_pending_reschedule(
            session_id, contact_channel, contact_address
        )
        if self._wants_reschedule(message) or pending_reschedule:
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

        pending = self._get_pending(session_id)

        # 0. Walking away from a half-finished booking (PROJ-478)
        if pending and self._cancels_booking(message):
            self._pending_bookings.pop(self._pending_key(session_id), None)
            answer = "No problem, I've dropped that booking. Is there anything else I can help with?"
            self.memory.save_context(message, "receptionist_general", answer, session_id=session_id)
            return {"answer": answer, "intent": "general"}

        # 0b. Call-backs and emergencies go to the team before anything else, so
        # "book me a call back" or "emergency booking" are not mistaken for an
        # ordinary appointment or a FAQ question.
        callback = self._handle_callback(message, session_id, contact_channel, contact_address)
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
        faq_hit = None if (pending and self._wants_human(message)) else find_answer(message)
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
        if self._wants_human(message):
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
            combined = " ".join(pending["messages"] + [message]) if pending else message
            result = self._handle_appointment(combined, session_id, contact_channel, contact_address)
            if urgent_notice:
                result["answer"] = urgent_notice + "\n\n" + result["answer"]
                result["urgent"] = True
            if result.get("needs_info"):
                self._pending_bookings[self._pending_key(session_id)] = {
                    "messages": (pending["messages"] if pending else []) + [message],
                    "ask": result["answer"],
                    "ts": time.time(),
                }
            else:
                self._pending_bookings.pop(self._pending_key(session_id), None)
            return result

        # 4. General conversation fallback
        answer = self._general_reply(message, session_id)
        self.memory.save_context(message, "receptionist_general", answer, session_id=session_id)
        return {"answer": answer, "intent": "general"}

    # ── Booking in progress (PROJ-478) ───────────────────────────
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

    def _handle_appointment(
        self,
        message: str,
        session_id: str | None,
        contact_channel: str | None = None,
        contact_address: str | None = None,
    ) -> dict:
        if not calendar_configured():
            answer = (
                "I'd love to book that for you, but calendar booking isn't set "
                "up on this server yet — please contact us directly to schedule."
            )
            self.memory.save_context(message, "receptionist_appointment", answer, session_id=session_id)
            return {"answer": answer, "intent": "appointment", "booked": False}

        extracted = self._extract_appointment(message)

        if extracted.get("clarify"):
            answer = extracted["clarify"]
            self.memory.save_context(message, "receptionist_appointment", answer, session_id=session_id)
            return {"answer": answer, "intent": "appointment", "booked": False, "needs_info": True}

        calendar_identity = {}
        if contact_channel and contact_address:
            calendar_identity = {
                "contact_channel": contact_channel,
                "contact_address": contact_address,
            }
        result = book_appointment(
            summary=extracted["summary"],
            start_iso=extracted["start"],
            end_iso=extracted["end"],
            timezone=TIMEZONE,
            **calendar_identity,
        )
        ics_link = self._ics_link(extracted)

        if result["ok"]:
            answer = f"Booked: **{extracted['summary']}** at {extracted['start'].replace('T', ' ')}."
            if result.get("event_url"):
                answer += f" [View event]({result['event_url']})"
            answer += f" · [Add to your own calendar]({ics_link})"

            # PROJ-445/446: auto-schedule a reminder ahead of the
            # appointment when we know how to reach the caller back.
            # A failure here never undoes the booking — it's already
            # confirmed on the calendar either way.
            if contact_channel and contact_address:
                reminder_result = create_reminder_for_booking(
                    summary=extracted["summary"],
                    start_iso=extracted["start"],
                    contact_channel=contact_channel,
                    contact_address=contact_address,
                    booking_id=result.get("event_id"),
                )
                if reminder_result["ok"]:
                    answer += " We'll send you a reminder before it starts."
        else:
            # Calendar booking failed (or isn't configured) — the .ics
            # download still lets the user add it to their own
            # calendar themselves (PROJ-294-298).
            answer = (
                f"I couldn't book that on our calendar — {result['error']} "
                f"You can still [add it to your own calendar]({ics_link}) and "
                "we'll follow up to confirm."
            )

        self.memory.save_context(message, "receptionist_appointment", answer, session_id=session_id)
        return {
            "answer": answer,
            "intent": "appointment",
            "booked": result["ok"],
            "event_url": result.get("event_url"),
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
