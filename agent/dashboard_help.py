"""MyAI: answers staff questions about how to use the dashboard.

Separate from the receptionist, which talks to patients. It answers from the
help topics in config/dashboard_help.json (matched by keywords, no API needed),
and when nothing matches and an Anthropic key is configured it asks Claude to
answer from those same topics only. It cannot read or change any data.
"""

from __future__ import annotations

import json
import os

from agent.faq import best_match
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL

HELP_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "dashboard_help.json")
MIN_SCORE = 0.4

_SYSTEM = """You are MyAI, the help assistant inside a clinic's reminder and receptionist dashboard.
Answer only questions about using the dashboard, from the help topics below. If the topics do not
cover the question, say you are not sure and name the closest tab or topic. Never invent buttons,
settings or features. You cannot see the clinic's data and cannot change anything. Be brief:
2 to 4 sentences, plain words, and name the tab or button to use.

HELP TOPICS:
{topics}"""

_cache: list[dict] | None = None


def _entries() -> list[dict]:
    global _cache
    if _cache is None:
        try:
            with open(HELP_PATH, encoding="utf-8") as fh:
                _cache = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _cache = []
    return _cache


def _topic_list() -> str:
    return "\n".join(f"- {e['question']}" for e in _entries()[:8])


def answer(message: str, client=None) -> dict:
    message = (message or "").strip()
    if not message:
        return {"answer": "Ask me how to use the dashboard, for example: How do I add a contact?", "intent": "help"}

    hit = best_match(_entries(), message, MIN_SCORE, weighted=True)
    if hit:
        return {"answer": hit["answer"], "intent": "help", "topic": hit["question"], "score": hit["score"]}

    api = client
    if api is None and ANTHROPIC_API_KEY:
        import anthropic

        api = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if api is not None:
        topics = "\n\n".join(f"Q: {e['question']}\nA: {e['answer']}" for e in _entries())
        try:
            resp = api.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=300,
                system=_SYSTEM.format(topics=topics),
                messages=[{"role": "user", "content": message}],
            )
            return {"answer": resp.content[0].text.strip(), "intent": "help"}
        except Exception:
            pass  # fall through to the plain answer below

    return {
        "answer": "I'm not sure about that one. I can help with things like:\n"
        + _topic_list()
        + "\nTry asking in other words, or name the tab you are on.",
        "intent": "help",
    }
