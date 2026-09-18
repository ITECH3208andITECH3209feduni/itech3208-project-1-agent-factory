# tests/test_consent_edge_cases.py
# ──────────────────────────────────────────────────────────────
# PROJ-416 — consent edge cases and STOP variations
#
# The failure mode these tests guard against is sending a message
# to someone who asked you to stop. That can happen two ways: a
# STOP that isn't recognised, or a phrase that isn't a STOP being
# treated as one. Both are tested here, along with the transition
# rules that stop an opt-out being silently reversed.
# ──────────────────────────────────────────────────────────────

import importlib
import os
import tempfile

import pytest

from contracts.schemas import ConsentState, normalise_phone
from integrations.sms_consent import (
    HELP_KEYWORDS,
    START_KEYWORDS,
    STOP_KEYWORDS,
    classify,
    normalise_keyword,
)


# ── Keyword classification (no database needed) ────────────────
@pytest.mark.parametrize("body", [
    "STOP", "stop", "Stop", "sToP",
    " STOP ", "stop.", "STOP!", "stop,", "Stop?",
    "\nstop\n", "  stop  ",
    "UNSUBSCRIBE", "unsubscribe", "Cancel", "END", "quit",
    "OPTOUT", "opt-out", "opt out", "remove", "NO",
    "stopall", "STOPALL",
])
def test_stop_variations_are_recognised(body):
    assert classify(body) == "stop", f"{body!r} should be an opt-out"


@pytest.mark.parametrize("body", [
    "stop sending me so many papers",
    "please stop",
    "can you stop the emails",
    "I want to stop using this",
    "don't stop",
    "stop and search laws",
    "find me papers on stop codons",
    "unsubscribe me from the other service",
    "no results found",
    "no idea what you mean",
])
def test_phrases_containing_stop_are_not_opt_outs(body):
    """
    Only an exact keyword counts. A substring check would silently
    unsubscribe people who meant something else — 'stop codons' is
    a genuine literature query.
    """
    assert classify(body) is None, f"{body!r} should reach the orchestrator"


@pytest.mark.parametrize("body", ["START", "start", "Yes", "SUBSCRIBE", "unstop", "opt in"])
def test_start_variations_are_recognised(body):
    assert classify(body) == "start"


@pytest.mark.parametrize("body", ["HELP", "help", "Info", "INFO"])
def test_help_variations_are_recognised(body):
    assert classify(body) == "help"


@pytest.mark.parametrize("body", ["", "   ", "\n", None])
def test_empty_bodies_are_not_keywords(body):
    assert classify(body) is None


def test_keyword_sets_do_not_overlap():
    """A word can't be both an opt-out and an opt-in."""
    assert not (STOP_KEYWORDS & START_KEYWORDS)
    assert not (STOP_KEYWORDS & HELP_KEYWORDS)
    assert not (START_KEYWORDS & HELP_KEYWORDS)


def test_normalise_keyword_collapses_whitespace():
    assert normalise_keyword("  OPT   OUT  ") == "opt out"


# ── Phone normalisation ────────────────────────────────────────
@pytest.mark.parametrize("raw", [
    "0400123456", "+61400123456", "0400 123 456",
    "(04) 0012 3456", "04-0012-3456", " 0400123456 ",
])
def test_phone_formats_normalise_to_one_value(raw):
    """
    A STOP has to match the contact it came from. If the same
    number can be stored two ways, an opt-out lands on one record
    and the send-block checks the other.
    """
    assert normalise_phone(raw) == "+61400123456"


def test_unparseable_phone_raises():
    with pytest.raises(ValueError):
        normalise_phone("not a number")


# ── Database-backed edge cases ─────────────────────────────────
@pytest.fixture()
def org(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("AUTH_DB_PATH", path)

    from auth import consent, consent_audit, db, tenancy
    from integrations import sms_sender
    importlib.reload(db)
    importlib.reload(tenancy)
    importlib.reload(consent)
    importlib.reload(consent_audit)
    importlib.reload(sms_sender)

    db.init_db()
    tenancy.init_tenancy()
    consent.init_consent()
    consent_audit.init_consent_audit()
    sms_sender.init_send_log()

    org_id = tenancy.create_org("Test Org")
    contact_id = tenancy.create_contact(org_id, "+61400123456", "Test Contact")

    yield {
        "consent": consent, "audit": consent_audit,
        "sender": sms_sender, "tenancy": tenancy,
        "org_id": org_id, "contact_id": contact_id,
    }

    try:
        os.unlink(path)
    except OSError:
        pass


def test_new_contact_starts_unknown_not_opted_in(org):
    """A contact nobody has asked must not default to subscribed."""
    c = org["consent"]
    assert c.get_consent_state(org["contact_id"], org["org_id"]) == ConsentState.UNKNOWN
    assert c.is_opted_in(org["contact_id"], org["org_id"]) is False


def test_import_cannot_opt_someone_in(org):
    """A bulk import isn't consent."""
    c = org["consent"]
    with pytest.raises(c.ConsentTransitionError):
        c.set_consent_state(org["contact_id"], org["org_id"],
                            ConsentState.OPTED_IN, "import")


def test_sms_cannot_opt_someone_in_from_unknown(org):
    c = org["consent"]
    with pytest.raises(c.ConsentTransitionError):
        c.set_consent_state(org["contact_id"], org["org_id"],
                            ConsentState.OPTED_IN, "sms_start")


def test_opt_out_is_allowed_from_any_source(org):
    """Never make it hard to leave."""
    c = org["consent"]
    for source in ["sms_stop", "import", "manual", "web_form", "anything"]:
        c.set_consent_state(org["contact_id"], org["org_id"],
                            ConsentState.OPTED_IN, "web_form")
        result = c.set_consent_state(org["contact_id"], org["org_id"],
                                     ConsentState.OPTED_OUT, source)
        assert result == ConsentState.OPTED_OUT


def test_opted_out_cannot_be_resurrected_by_import(org):
    c = org["consent"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop")
    with pytest.raises(c.ConsentTransitionError):
        c.set_consent_state(org["contact_id"], org["org_id"],
                            ConsentState.OPTED_IN, "import")
    assert c.get_consent_state(org["contact_id"], org["org_id"]) == ConsentState.OPTED_OUT


def test_opted_out_cannot_be_resurrected_by_sms(org):
    c = org["consent"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop")
    with pytest.raises(c.ConsentTransitionError):
        c.set_consent_state(org["contact_id"], org["org_id"],
                            ConsentState.OPTED_IN, "sms_start")


def test_opted_out_can_resubscribe_via_explicit_form(org):
    c = org["consent"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop")
    result = c.set_consent_state(org["contact_id"], org["org_id"],
                                 ConsentState.OPTED_IN, "web_form")
    assert result == ConsentState.OPTED_IN


def test_repeated_stop_is_idempotent(org):
    """
    Someone texting STOP twice shouldn't produce two audit rows or
    an error — the second is a no-op.
    """
    c, audit = org["consent"], org["audit"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop")
    before = len(audit.get_history(org["contact_id"], org["org_id"]))
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop")
    after = len(audit.get_history(org["contact_id"], org["org_id"]))
    assert before == after


def test_every_state_change_is_audited(org):
    c, audit = org["consent"], org["audit"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_IN, "web_form", detail="form")
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop", detail="STOP")
    history = audit.get_history(org["contact_id"], org["org_id"])
    assert len(history) == 2
    assert history[0]["new_state"] == "opted_in"
    assert history[1]["new_state"] == "opted_out"
    assert history[1]["old_state"] == "opted_in"


def test_audit_records_the_triggering_message(org):
    """The detail field is the evidence of what was said."""
    c, audit = org["consent"], org["audit"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop",
                        detail="inbound SMS: STOP")
    event = audit.get_history(org["contact_id"], org["org_id"])[-1]
    assert "STOP" in event["detail"]
    assert event["source"] == "sms_stop"


# ── Send-block edge cases ──────────────────────────────────────
@pytest.mark.parametrize("state,source", [
    (ConsentState.UNKNOWN, None),
    (ConsentState.OPTED_OUT, "sms_stop"),
])
def test_send_blocked_unless_opted_in(org, state, source):
    s, c = org["sender"], org["consent"]
    if source:
        c.set_consent_state(org["contact_id"], org["org_id"],
                            ConsentState.OPTED_IN, "web_form")
        c.set_consent_state(org["contact_id"], org["org_id"], state, source)
    with pytest.raises(s.SendBlocked):
        s.send_to_contact(org["contact_id"], org["org_id"], "Hello")


def test_send_allowed_once_opted_in(org):
    s, c = org["sender"], org["consent"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_IN, "web_form")
    # No provider configured in tests, so None means accepted-and-logged.
    assert s.send_to_contact(org["contact_id"], org["org_id"], "Hello") is None


def test_send_to_nonexistent_contact_is_blocked(org):
    s = org["sender"]
    with pytest.raises(s.SendBlocked):
        s.send_to_contact(99999, org["org_id"], "Hello")


def test_blocked_sends_are_logged_with_reason(org):
    s, c = org["sender"], org["consent"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_IN, "web_form")
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop")
    with pytest.raises(s.SendBlocked):
        s.send_to_contact(org["contact_id"], org["org_id"], "Hello")

    log = s.send_history(org["contact_id"], org["org_id"])
    assert log[0]["outcome"] == "blocked"
    assert log[0]["consent_state"] == "opted_out"
    assert log[0]["reason"] == "not opted in"


def test_bulk_send_cannot_bypass_the_block(org):
    s, c = org["sender"], org["consent"]
    t = org["tenancy"]
    opted_in = t.create_contact(org["org_id"], "+61400999888", "Subscribed")
    c.set_consent_state(opted_in, org["org_id"], ConsentState.OPTED_IN, "web_form")

    result = s.send_bulk(org["org_id"],
                         [opted_in, org["contact_id"], 99999],
                         "Bulk message")
    assert result["sent"] == 1
    assert result["blocked"] == 2
    assert org["contact_id"] in result["blocked_ids"]


def test_send_after_stop_then_resubscribe_is_allowed(org):
    """Full lifecycle: in, out, back in via form, send works."""
    s, c = org["sender"], org["consent"]
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_IN, "web_form")
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_OUT, "sms_stop")
    with pytest.raises(s.SendBlocked):
        s.send_to_contact(org["contact_id"], org["org_id"], "Blocked")
    c.set_consent_state(org["contact_id"], org["org_id"],
                        ConsentState.OPTED_IN, "web_form")
    assert s.send_to_contact(org["contact_id"], org["org_id"], "Allowed") is None