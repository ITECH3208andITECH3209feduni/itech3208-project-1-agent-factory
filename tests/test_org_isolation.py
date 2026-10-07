# tests/test_org_isolation.py
# ──────────────────────────────────────────────────────────────
# PROJ-411 — one org cannot read another's data
#
# Each test uses a temporary database so the suite never touches
# auth_users.db and can run repeatedly without leftover state.
#
# Two orgs are created with one user and one contact each. Every
# test then attempts a cross-org read or write and asserts it
# fails — not that it returns filtered results, but that the
# caller is told the record doesn't exist. Leaking "that row
# exists but isn't yours" is itself an information leak.
# ──────────────────────────────────────────────────────────────

import importlib
import os
import sqlite3
import tempfile

import pytest


@pytest.fixture()
def two_orgs(monkeypatch):
    """
    Build a throwaway database with two isolated organisations.

    Modules read DB_PATH at import time, so the env var is set and
    the modules reloaded before anything touches the database.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("AUTH_DB_PATH", path)

    from auth import consent, consent_audit, db, tenancy
    importlib.reload(db)
    importlib.reload(tenancy)
    importlib.reload(consent)
    importlib.reload(consent_audit)

    db.init_db()
    tenancy.init_tenancy()
    consent.init_consent()
    consent_audit.init_consent_audit()

    org_a = tenancy.create_org("Org A", "a@example.com")
    org_b = tenancy.create_org("Org B", "b@example.com")

    user_a = db.create_user("owner@orga.com", "hash-a")
    user_b = db.create_user("owner@orgb.com", "hash-b")
    tenancy.assign_user_to_org(user_a, org_a, "owner")
    tenancy.assign_user_to_org(user_b, org_b, "owner")

    contact_a = tenancy.create_contact(org_a, "+61400000001", "Contact A")
    contact_b = tenancy.create_contact(org_b, "+61400000002", "Contact B")

    yield {
        "db": db, "tenancy": tenancy, "consent": consent,
        "consent_audit": consent_audit,
        "org_a": org_a, "org_b": org_b,
        "user_a": user_a, "user_b": user_b,
        "contact_a": contact_a, "contact_b": contact_b,
    }

    try:
        os.unlink(path)
    except OSError:
        pass


# ── Contacts ───────────────────────────────────────────────────
def test_org_can_read_own_contact(two_orgs):
    t = two_orgs["tenancy"]
    row = t.get_contact(two_orgs["contact_a"], two_orgs["org_a"])
    assert row is not None
    assert row["name"] == "Contact A"


def test_org_cannot_read_other_orgs_contact(two_orgs):
    t = two_orgs["tenancy"]
    # Org A asking for Org B's contact by id.
    assert t.get_contact(two_orgs["contact_b"], two_orgs["org_a"]) is None


def test_contact_list_is_scoped(two_orgs):
    t = two_orgs["tenancy"]
    a_contacts = t.list_contacts(two_orgs["org_a"])
    b_contacts = t.list_contacts(two_orgs["org_b"])
    assert [c["name"] for c in a_contacts] == ["Contact A"]
    assert [c["name"] for c in b_contacts] == ["Contact B"]


def test_phone_lookup_is_scoped(two_orgs):
    t = two_orgs["tenancy"]
    # Org B's number must not resolve inside Org A.
    assert t.get_contact_by_phone(two_orgs["org_a"], "+61400000002") is None
    assert t.get_contact_by_phone(two_orgs["org_b"], "+61400000002") is not None


def test_same_phone_can_exist_in_both_orgs(two_orgs):
    """
    Two orgs may legitimately have the same person as a contact.
    The uniqueness constraint is per-org, not global.
    """
    t = two_orgs["tenancy"]
    shared = "+61400009999"
    id_a = t.create_contact(two_orgs["org_a"], shared, "Shared A")
    id_b = t.create_contact(two_orgs["org_b"], shared, "Shared B")
    assert id_a != id_b
    assert t.get_contact(id_b, two_orgs["org_a"]) is None


def test_duplicate_phone_within_one_org_is_rejected(two_orgs):
    t = two_orgs["tenancy"]
    with pytest.raises(sqlite3.IntegrityError):
        t.create_contact(two_orgs["org_a"], "+61400000001", "Duplicate")


# ── Organisations ──────────────────────────────────────────────
def test_org_profile_reads_are_separate(two_orgs):
    t = two_orgs["tenancy"]
    assert t.get_org(two_orgs["org_a"])["name"] == "Org A"
    assert t.get_org(two_orgs["org_b"])["name"] == "Org B"


def test_updating_one_org_leaves_the_other_untouched(two_orgs):
    t = two_orgs["tenancy"]
    t.update_org(two_orgs["org_a"], name="Org A Renamed")
    assert t.get_org(two_orgs["org_a"])["name"] == "Org A Renamed"
    assert t.get_org(two_orgs["org_b"])["name"] == "Org B"


def test_user_belongs_to_exactly_one_org(two_orgs):
    t = two_orgs["tenancy"]
    assert t.get_user_org_id(two_orgs["user_a"]) == two_orgs["org_a"]
    assert t.get_user_org_id(two_orgs["user_b"]) == two_orgs["org_b"]


# ── Consent state ──────────────────────────────────────────────
def test_consent_state_is_scoped(two_orgs):
    c = two_orgs["consent"]
    from contracts.schemas import ConsentState

    c.set_consent_state(two_orgs["contact_a"], two_orgs["org_a"],
                        ConsentState.OPTED_IN, "web_form")
    assert c.get_consent_state(two_orgs["contact_a"], two_orgs["org_a"]) \
        == ConsentState.OPTED_IN
    # Org B's contact is unaffected.
    assert c.get_consent_state(two_orgs["contact_b"], two_orgs["org_b"]) \
        == ConsentState.UNKNOWN


def test_cannot_change_consent_across_orgs(two_orgs):
    c = two_orgs["consent"]
    from contracts.schemas import ConsentState

    with pytest.raises(c.ConsentTransitionError) as exc:
        c.set_consent_state(two_orgs["contact_b"], two_orgs["org_a"],
                            ConsentState.OPTED_OUT, "manual")
    # The error says "not found", not "belongs to another org" —
    # the caller learns nothing about the other tenant.
    assert "not found" in str(exc.value)


def test_cannot_read_consent_across_orgs(two_orgs):
    c = two_orgs["consent"]
    assert c.get_consent_state(two_orgs["contact_b"], two_orgs["org_a"]) is None


def test_is_opted_in_fails_closed_across_orgs(two_orgs):
    c = two_orgs["consent"]
    from contracts.schemas import ConsentState

    c.set_consent_state(two_orgs["contact_b"], two_orgs["org_b"],
                        ConsentState.OPTED_IN, "web_form")
    # Opted in for B, but must read as not-opted-in from A.
    assert c.is_opted_in(two_orgs["contact_b"], two_orgs["org_b"]) is True
    assert c.is_opted_in(two_orgs["contact_b"], two_orgs["org_a"]) is False


# ── Audit trail ────────────────────────────────────────────────
def test_audit_history_is_scoped(two_orgs):
    c = two_orgs["consent"]
    audit = two_orgs["consent_audit"]
    from contracts.schemas import ConsentState

    c.set_consent_state(two_orgs["contact_b"], two_orgs["org_b"],
                        ConsentState.OPTED_IN, "web_form",
                        detail="signup form")

    assert len(audit.get_history(two_orgs["contact_b"], two_orgs["org_b"])) == 1
    # Org A must not see the event, even knowing the contact id.
    assert audit.get_history(two_orgs["contact_b"], two_orgs["org_a"]) == []


def test_opt_in_proof_is_scoped(two_orgs):
    c = two_orgs["consent"]
    audit = two_orgs["consent_audit"]
    from contracts.schemas import ConsentState

    c.set_consent_state(two_orgs["contact_b"], two_orgs["org_b"],
                        ConsentState.OPTED_IN, "web_form")
    assert audit.get_opt_in_proof(two_orgs["contact_b"], two_orgs["org_b"]) is not None
    assert audit.get_opt_in_proof(two_orgs["contact_b"], two_orgs["org_a"]) is None


def test_recent_events_do_not_mix_orgs(two_orgs):
    c = two_orgs["consent"]
    audit = two_orgs["consent_audit"]
    from contracts.schemas import ConsentState

    c.set_consent_state(two_orgs["contact_a"], two_orgs["org_a"],
                        ConsentState.OPTED_IN, "web_form")
    c.set_consent_state(two_orgs["contact_b"], two_orgs["org_b"],
                        ConsentState.OPTED_IN, "manual")

    a_events = audit.recent_events(two_orgs["org_a"])
    b_events = audit.recent_events(two_orgs["org_b"])
    assert all(e["org_id"] == two_orgs["org_a"] for e in a_events)
    assert all(e["org_id"] == two_orgs["org_b"] for e in b_events)
    assert len(a_events) == 1
    assert len(b_events) == 1