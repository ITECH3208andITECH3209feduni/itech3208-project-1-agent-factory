# agent/call_summary.py
# ──────────────────────────────────────────────────────────────
# Post-call processing (PROJ-477, brief Part D3): turn a finished voice call's
# transcript into a one-line summary, a sentiment and a priority, so the
# operator dashboard can show who needs attention first.
#
# Claude does the work when it is reachable. If the key is missing or the call
# fails, a keyword heuristic still produces a tag, so a call is never left
# untagged and the phone path never depends on the model being up.
# ──────────────────────────────────────────────────────────────

import json
import logging
import re

log = logging.getLogger("agent_factory.call_summary")

SENTIMENTS = ("positive", "neutral", "negative")
PRIORITIES = ("low", "normal", "high")

_NEGATIVE = {
    "angry", "upset", "terrible", "awful", "unacceptable", "complaint", "complain",
    "refund", "furious", "worst", "disappointed", "frustrated", "ridiculous", "useless",
}
_POSITIVE = {"thanks", "thank", "great", "perfect", "wonderful", "excellent", "appreciate", "happy", "love"}
_URGENT = {"urgent", "emergency", "asap", "immediately", "right now", "pain", "bleeding", "cancel", "today"}

SUMMARY_PROMPT = """You are summarising a finished phone call to an AI receptionist for the business owner.

Transcript (caller, then receptionist reply):
{transcript}

Return ONLY a JSON object, no other text:
{{"summary": "<one sentence, under 30 words, what the caller wanted and what happened>",
  "sentiment": "positive" | "neutral" | "negative",
  "priority": "low" | "normal" | "high"}}

priority is "high" when the caller is upset, the matter is urgent or time-critical, or they asked for a human.
Otherwise "normal" for a real request (booking, question needing follow-up) and "low" for a simple FAQ."""


def _transcript(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        lines.append(f"Caller: {t.get('query', '')}")
        reply = (t.get("summary") or "").strip()
        if reply:
            lines.append(f"Receptionist: {reply}")
    return "\n".join(lines)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def heuristic_summary(turns: list[dict]) -> dict:
    """Keyword fallback. Deliberately conservative: unknown means neutral/normal."""
    caller_text = " ".join(t.get("query", "") for t in turns)
    words = _words(caller_text)
    lowered = caller_text.lower()

    negative = len(words & _NEGATIVE)
    positive = len(words & _POSITIVE)
    urgent = bool(words & _URGENT) or any(p in lowered for p in _URGENT if " " in p)
    escalated = any((t.get("skill") or "") == "receptionist_escalate" for t in turns)

    if negative > positive:
        sentiment = "negative"
    elif positive > negative:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    if escalated or urgent or sentiment == "negative":
        priority = "high"
    elif all((t.get("skill") or "") == "receptionist_faq" for t in turns):
        priority = "low"
    else:
        priority = "normal"

    first = (turns[0].get("query") or "").strip() if turns else ""
    summary = f"Caller asked: {first[:120]}" if first else "Call with no recorded speech."
    if escalated:
        summary += " Asked for a human."
    return {"summary": summary, "sentiment": sentiment, "priority": priority}


def _clean(data: dict, fallback: dict) -> dict:
    summary = str(data.get("summary") or "").strip()[:300] or fallback["summary"]
    sentiment = str(data.get("sentiment") or "").lower()
    priority = str(data.get("priority") or "").lower()
    return {
        "summary": summary,
        "sentiment": sentiment if sentiment in SENTIMENTS else fallback["sentiment"],
        "priority": priority if priority in PRIORITIES else fallback["priority"],
    }


def summarise_call(turns: list[dict], client=None, model: str | None = None) -> dict:
    """Return {"summary", "sentiment", "priority"} for a list of memory turns.

    `client` is an anthropic.Anthropic-like object (injected in tests). Any
    failure falls back to the heuristic.
    """
    fallback = heuristic_summary(turns)
    if not turns:
        return fallback

    # A human handoff is always high priority, whatever the model says.
    escalated = any((t.get("skill") or "") == "receptionist_escalate" for t in turns)

    if client is None:
        try:
            import anthropic
            from config.settings import ANTHROPIC_API_KEY

            if not ANTHROPIC_API_KEY:
                return fallback
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except Exception:  # noqa: BLE001 - never let tagging break a call
            return fallback

    try:
        from config.settings import CLAUDE_HAIKU_MODEL

        resp = client.messages.create(
            model=model or CLAUDE_HAIKU_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": SUMMARY_PROMPT.format(transcript=_transcript(turns))}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = _clean(json.loads(raw), fallback)
    except Exception as exc:  # noqa: BLE001
        log.warning("call summary model failed, using heuristic: %s", exc)
        result = fallback

    if escalated:
        result["priority"] = "high"
    return result


def finalize_call(call_sid: str, caller: str, memory, client=None) -> dict | None:
    """Summarise and store one call exactly once. Safe to call repeatedly
    (goodbye and the status callback both fire it). Returns the stored record,
    or None if there was nothing to summarise or it was already done."""
    from app.web_ui.activity_db import get_call_summary, save_call_summary

    if not call_sid or get_call_summary(call_sid):
        return None
    turns = memory.get_history(last_n=40, session_id=call_sid)
    if not turns:
        return None
    result = summarise_call(turns, client=client)
    save_call_summary(call_sid, caller, result["summary"], result["sentiment"], result["priority"], len(turns))
    return result
