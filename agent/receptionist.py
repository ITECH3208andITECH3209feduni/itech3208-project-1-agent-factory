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
from datetime import datetime

import anthropic

from agent.calendar_client import book_appointment, is_configured as calendar_configured
from agent.faq import find_answer
from agent.memory import SessionMemory
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, TIMEZONE, ESCALATION_LOG

RECEPTIONIST_SYSTEM_PROMPT = """You are the front-desk AI receptionist for Agent Factory.
Be warm, brief, and helpful. You can answer general questions, but you are
NOT the literature-search or Amazon-research specialist — if someone
clearly wants deep product or paper research, gently point them at the
"Amazon Seller AI" / "Literature AI" tabs instead of trying to do that
research yourself.
Keep replies to 2-4 sentences unless the question genuinely needs more."""

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
_APPOINTMENT_KEYWORDS = {
    "book", "appointment", "schedule", "meeting", "reserve",
    "reservation", "consult", "consultation", "book me", "set up a call",
}


class Receptionist:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.memory = SessionMemory()

    # ── Main entry point ─────────────────────────────────────────
    def handle(self, message: str, session_id: str | None = None) -> dict:
        """Returns {"answer": str, "intent": str, ...extra fields}."""
        message = (message or "").strip()
        if not message:
            return {"answer": "Sorry, I didn't catch that — could you say that again?", "intent": "general"}

        # 1. FAQ lookup first (PROJ-214: KB before skill routing)
        faq_hit = find_answer(message)
        if faq_hit:
            self.memory.save_context(message, "receptionist_faq", faq_hit["answer"], session_id=session_id)
            return {"answer": faq_hit["answer"], "intent": "faq", "faq_score": faq_hit["score"]}

        # 2. Escalation
        if self._wants_human(message):
            answer = (
                "I've flagged this conversation for our team — someone will "
                "follow up with you shortly. Is there anything else I can help "
                "with in the meantime?"
            )
            self._log_escalation(message, session_id)
            self.memory.save_context(message, "receptionist_escalate", answer, session_id=session_id)
            return {"answer": answer, "intent": "escalate"}

        # 3. Appointment booking
        if self._wants_appointment(message):
            result = self._handle_appointment(message, session_id)
            return result

        # 4. General conversation fallback
        answer = self._general_reply(message, session_id)
        self.memory.save_context(message, "receptionist_general", answer, session_id=session_id)
        return {"answer": answer, "intent": "general"}

    # ── Intent keyword pre-checks ────────────────────────────────
    def _wants_human(self, message: str) -> bool:
        m = message.lower()
        return any(k in m for k in _ESCALATE_KEYWORDS)

    def _wants_appointment(self, message: str) -> bool:
        m = message.lower()
        return any(k in m for k in _APPOINTMENT_KEYWORDS)

    # ── Escalation logging ───────────────────────────────────────
    def _log_escalation(self, message: str, session_id: str | None) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id or "unknown",
            "message": message,
        }
        try:
            import os

            os.makedirs(os.path.dirname(ESCALATION_LOG), exist_ok=True)
            with open(ESCALATION_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # don't fail the user-facing reply just because logging failed

    # ── Appointment booking ──────────────────────────────────────
    def _handle_appointment(self, message: str, session_id: str | None) -> dict:
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
            return {"answer": answer, "intent": "appointment", "booked": False}

        result = book_appointment(
            summary=extracted["summary"],
            start_iso=extracted["start"],
            end_iso=extracted["end"],
            timezone=TIMEZONE,
        )
        ics_link = self._ics_link(extracted)

        if result["ok"]:
            answer = f"Booked: **{extracted['summary']}** at {extracted['start'].replace('T', ' ')}."
            if result.get("event_url"):
                answer += f" [View event]({result['event_url']})"
            answer += f" · [Add to your own calendar]({ics_link})"
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
                system=RECEPTIONIST_SYSTEM_PROMPT,
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
