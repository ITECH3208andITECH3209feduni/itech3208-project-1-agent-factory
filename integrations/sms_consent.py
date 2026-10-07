# integrations/sms_consent.py
# ──────────────────────────────────────────────────────────────
# Automatic STOP keyword handler on inbound SMS (PROJ-414)
#
# Runs before the orchestrator sees an inbound message. If the
# body is an opt-out keyword, consent is revoked and a
# confirmation is returned — the message is never treated as a
# query.
#
# Keyword matching is deliberately loose on formatting (case,
# whitespace, punctuation) and strict on content: only an exact
# keyword match counts, so "stop sending me so many papers" is
# handled as a query, not an opt-out. Carriers apply the same
# rule, and treating any message containing "stop" as an opt-out
# would silently unsubscribe people who meant something else.
# ──────────────────────────────────────────────────────────────

import logging
import re

from auth.consent import (
    ConsentTransitionError,
    get_consent_by_phone,
    set_consent_state,
)
from auth.sms_routing import resolve_org_by_twilio_number
from auth.tenancy import create_contact, get_contact_by_phone
from contracts.schemas import ConsentState, normalise_phone

log = logging.getLogger("sms_consent")

# Carrier-standard opt-out keywords, plus common variants.
STOP_KEYWORDS = {
    "stop", "stopall", "unsubscribe", "cancel", "end", "quit",
    "optout", "opt-out", "opt out", "remove", "no",
}

# Opt-in keywords, for someone re-subscribing by text.
START_KEYWORDS = {"start", "unstop", "yes", "subscribe", "optin", "opt-in", "opt in"}

# Carriers require HELP to be answered too.
HELP_KEYWORDS = {"help", "info"}

STOP_REPLY = (
    "You've been unsubscribed and will get no further messages. "
    "Reply START to opt back in."
)
START_REPLY = "You're subscribed again. Reply STOP at any time to opt out."
HELP_REPLY = (
    "Agent Factory research assistant. Send a question to search. "
    "Reply STOP to unsubscribe."
)


def normalise_keyword(body: str) -> str:
    """Strip case, whitespace and trailing punctuation for matching."""
    return re.sub(r"[\s\.\!\,\?]+", " ", (body or "").strip().lower()).strip()


def classify(body: str) -> str | None:
    """Return 'stop', 'start', 'help', or None if this isn't a keyword."""
    word = normalise_keyword(body)
    if word in STOP_KEYWORDS:
        return "stop"
    if word in START_KEYWORDS:
        return "start"
    if word in HELP_KEYWORDS:
        return "help"
    return None


def handle_inbound(body: str, from_number: str, to_number: str) -> str | None:
    """
    Process an inbound SMS for consent keywords.

    Returns the reply text if this was a consent keyword and the
    message should not reach the orchestrator, or None if it's an
    ordinary query.
    """
    kind = classify(body)
    if kind is None:
        return None

    if kind == "help":
        return HELP_REPLY

    org_id = resolve_org_by_twilio_number(to_number)
    if org_id is None:
        # Better to acknowledge the opt-out than to ignore it. We
        # can't record state without knowing the tenant, so this is
        # logged loudly for follow-up.
        log.error(
            "consent keyword '%s' from %s to unmapped number %s — not recorded",
            kind, from_number, to_number,
        )
        return STOP_REPLY if kind == "stop" else START_REPLY

    try:
        phone = normalise_phone(from_number)
    except ValueError:
        log.error("unparseable sender number: %r", from_number)
        return STOP_REPLY if kind == "stop" else START_REPLY

    existing = get_contact_by_phone(org_id, phone)
    if existing is None:
        # Someone texting STOP who isn't on file still deserves a
        # recorded opt-out, so create the contact then opt them out.
        contact_id = create_contact(org_id, phone)
        log.info("created contact %s for inbound consent keyword", contact_id)
    else:
        contact_id = existing["id"]

    new_state = ConsentState.OPTED_OUT if kind == "stop" else ConsentState.OPTED_IN
    source = "sms_stop" if kind == "stop" else "sms_start"

    try:
        set_consent_state(
            contact_id, org_id, new_state, source,
            detail=f"inbound SMS: {(body or '')[:120]}",
        )
        log.info("contact %s (org %s) -> %s via %s",
                 contact_id, org_id, new_state.value, source)
    except ConsentTransitionError as exc:
        # A START from someone who opted out is refused by the
        # transition rules (PROJ-412 requires explicit first-party
        # consent to re-subscribe). Tell them how to proceed.
        log.warning("consent transition refused: %s", exc)
        if kind == "start":
            return (
                "To subscribe again, please opt in through the signup form. "
                "We can't reactivate by text."
            )

    return STOP_REPLY if kind == "stop" else START_REPLY