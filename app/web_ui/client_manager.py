# app/web_ui/client_manager.py
# ──────────────────────────────────────────────────────────────
# Multi-client profile manager.
# Client JSON files live in config/clients/<id>.json.
# Active client is persisted to config/active_client.txt.
# ──────────────────────────────────────────────────────────────

import json
import os

_CLIENTS_DIR = os.path.join(os.path.dirname(__file__), "../../config/clients")
_ACTIVE_FILE = os.path.join(os.path.dirname(__file__), "../../config/active_client.txt")
_DEFAULT_CLIENT = "chase_exotic"


def list_clients() -> list[dict]:
    clients = []
    for fname in sorted(os.listdir(_CLIENTS_DIR)):
        if fname.endswith(".json"):
            path = os.path.join(_CLIENTS_DIR, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                    clients.append({"id": d["id"], "name": d["name"], "tagline": d.get("tagline", "")})
            except Exception:
                pass
    return clients


def get_active_id() -> str:
    try:
        with open(_ACTIVE_FILE, encoding="utf-8") as f:
            return f.read().strip() or _DEFAULT_CLIENT
    except FileNotFoundError:
        return _DEFAULT_CLIENT


def set_active_client(client_id: str) -> bool:
    path = os.path.join(_CLIENTS_DIR, f"{client_id}.json")
    if not os.path.exists(path):
        return False
    with open(_ACTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(client_id)
    return True


def get_active_client() -> dict:
    client_id = get_active_id()
    path = os.path.join(_CLIENTS_DIR, f"{client_id}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        path = os.path.join(_CLIENTS_DIR, f"{_DEFAULT_CLIENT}.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)


def build_system_prompt(client: dict, query: str | None = None) -> str:
    c = client
    hours = c.get("hours", {})
    hours_str = ", ".join(f"{d.capitalize()}: {h}" for d, h in hours.items())

    services = c.get("services", [])
    services_str = "\n".join(
        f"  - {s['name']}: {s['price']} — {s['description']}" for s in services
    )

    faqs = c.get("faqs", [])
    faq_str = "\n".join(f"  Q: {f['q']}\n  A: {f['a']}" for f in faqs)

    personality = c.get("personality", {})
    contact = c.get("contact", {})
    booking = c.get("booking", {})

    rag_section = ""
    if c.get("rag_enabled") and query:
        from agent.fedai_rag import build_rag_context
        try:
            context = build_rag_context(query, k=5)
        except Exception:
            context = ""  # index not built yet, or model unavailable — degrade to static FAQs only
        if context:
            rag_section = f"""

RELEVANT INFORMATION RETRIEVED FROM FEDERATION UNIVERSITY'S WEBSITE FOR THIS QUESTION
(use this as your primary source — it's more current and specific than the FAQ list above;
cite the page it came from when it's helpful, e.g. "According to the Library page..."):
{context}
"""

    return f"""You are the AI receptionist for {c['name']} ({c.get('tagline', '')}).

PERSONALITY: {personality.get('style', 'professional and helpful')}. Be warm, brief, and enthusiastic.
Keep replies to 2-4 sentences for voice calls unless more detail is genuinely needed.
When a question is broad or could go in several directions (e.g. it touches multiple
campuses, multiple options, or multiple sub-topics), do NOT dump everything you know
in one long answer. Instead give a short 1-2 sentence direct answer to what was
actually asked, then ask a brief follow-up question to find out what they specifically
need before going into more detail. Only give a full, detailed answer up front when the
question is already specific and narrow.

BUSINESS HOURS: {hours_str}

CONTACT: {contact.get('address', '')} | {contact.get('email', '')} | {contact.get('website', '')}

SERVICES & PRICING:
{services_str}

FREQUENTLY ASKED QUESTIONS:
{faq_str}
{rag_section}
BOOKING: {'Enabled — collect ' + ', '.join(booking.get('fields', [])) + '. Payment: ' + booking.get('payment_terms', '') if booking.get('enabled') else 'Refer to the team for booking enquiries.'}

If a caller wants to speak to a human, say: "{personality.get('transfer_phrase', 'let me connect you with our team')}" and flag the conversation for follow-up.
Never make up prices, availability, or information not listed above. If unsure, offer to have the team follow up."""
