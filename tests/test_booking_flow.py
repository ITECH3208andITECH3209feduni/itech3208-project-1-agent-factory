# tests/test_booking_flow.py
# The receptionist's booking conversation, the bookings store, the patient's
# confirmation page, the Calendar tab, and how calls speak "000".
import pytest
from fastapi.testclient import TestClient

import agent.memory as memory_module
import agent.receptionist as receptionist_module
from agent import bookings
from agent.delivery.base import DeliveryResult
from agent.receptionist import Receptionist, _parse_email, _parse_name, _parse_phone

DETAILS = {"summary": "Check-up", "start": "2030-03-04T10:00:00", "end": "2030-03-04T10:30:00", "clarify": None}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "bookings.db")
    monkeypatch.setattr(bookings, "BOOKINGS_DB", path)
    return path


@pytest.fixture
def sent(monkeypatch):
    """Capture the confirmation messages instead of sending them."""
    calls = []
    monkeypatch.setattr(bookings, "notify_in_background", lambda booking, token: calls.append((booking, token)))
    return calls


@pytest.fixture
def r(tmp_path, monkeypatch, fake_anthropic_reply, db, sent):
    faq_path = tmp_path / "faq.json"
    faq_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("agent.faq.FAQ_DATA_PATH", str(faq_path))
    from agent import faq

    faq.reload_faq()
    monkeypatch.setattr(receptionist_module, "ESCALATION_LOG", str(tmp_path / "esc.jsonl"))
    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: False)
    rec = Receptionist()
    rec.memory = memory_module.SessionMemory(db_path=str(tmp_path / "memory.db"))
    rec._extract_appointment = lambda message: dict(DETAILS)
    return rec


def _voice(r, text, sid="CA1"):
    return r.handle(text, session_id=sid, contact_channel="voice", contact_address="+61400111222", org_id=7)


# ── The conversation ──────────────────────────────────────────

def test_phone_booking_asks_for_name_phone_email_then_reads_back(r, db, sent):
    first = _voice(r, "I'd like to book a check-up")
    assert first["needs_info"] and "full name" in first["answer"] and "Monday 4 March at 10 am" in first["answer"]

    ask_phone = _voice(r, "My name is jane citizen")
    assert ask_phone["expect"] == "phone" and "Jane" in ask_phone["answer"]
    assert "this number" in ask_phone["answer"]

    ask_email = _voice(r, "this number")
    assert ask_email["expect"] == "email" and "dot" in ask_email["answer"]

    readback = _voice(r, "jane dot citizen at gmail dot com")
    assert readback["expect"] == "confirm"
    for part in ("check-up on Monday 4 March at 10 am", "Jane Citizen", "0400 111 222",
                 "jane.citizen@gmail.com", "Is that correct?"):
        assert part in readback["answer"]
    assert bookings.list_upcoming(None, db_path=db) == [], "nothing is saved before the yes"

    done = _voice(r, "yes that's right")
    assert done["booked"] is True and done["status"] == "unconfirmed"
    assert "a text and an email" in done["answer"]
    assert "](" not in done["answer"], "no Markdown links read out on a call"

    saved = bookings.list_upcoming(None, db_path=db)
    assert len(saved) == 1
    b = saved[0]
    assert (b["name"], b["phone"], b["email"], b["status"], b["org_id"], b["channel"]) == (
        "Jane Citizen", "+61400111222", "jane.citizen@gmail.com", "unconfirmed", 7, "voice")
    assert len(sent) == 1 and sent[0][0]["id"] == b["id"]
    assert r._get_pending("CA1") is None


def test_web_chat_booking_gives_the_confirm_link(r, db, sent):
    r.handle("book me a check-up", session_id="web")
    r.handle("Sam Lee", session_id="web")
    r.handle("0412 345 678", session_id="web")
    r.handle("sam@example.com", session_id="web")
    done = r.handle("yes", session_id="web")
    assert done["booked"] is True
    assert "/booking/confirm/" in done["answer"] and "/calendar/ics?" in done["answer"]
    assert bookings.list_upcoming(None, db_path=db)[0]["phone"] == "+61412345678"


def test_saying_no_lets_the_person_fix_one_detail(r, db):
    for msg in ("book a check-up", "Sam Lee", "0412 345 678", "sam@example.com"):
        r.handle(msg, session_id="s")
    change = r.handle("no", session_id="s")
    assert "What would you like to change" in change["answer"]
    fixed = r.handle("my email is sam.lee@example.com", session_id="s")
    assert fixed["expect"] == "confirm" and "sam.lee@example.com" in fixed["answer"]
    assert r.handle("yes", session_id="s")["booked"] is True


def test_changing_the_time_asks_again(r):
    for msg in ("book a check-up", "Sam Lee", "0412 345 678", "no email"):
        r.handle(msg, session_id="t")
    r.handle("no", session_id="t")
    r._extract_appointment = lambda message: {**DETAILS, "start": "2030-03-05T15:00:00", "end": "2030-03-05T15:30:00"}
    again = r.handle("the time, make it Tuesday at 3pm", session_id="t")
    assert again["expect"] == "confirm" and "Tuesday 5 March at 3 pm" in again["answer"]
    assert "no email" in again["answer"]


def test_no_email_is_fine(r, sent):
    for msg in ("book a check-up", "Sam Lee", "0412 345 678"):
        r.handle(msg, session_id="n")
    readback = r.handle("I don't have an email", session_id="n")
    assert "no email" in readback["answer"]
    done = r.handle("yes", session_id="n")
    assert "a text with a link" in done["answer"]


def test_a_question_is_not_taken_as_a_name(r):
    r.handle("book a check-up", session_id="q")
    out = r.handle("where do I park?", session_id="q")
    assert out["expect"] == "name" and "full name" in out["answer"]
    assert "name" not in r._get_pending("q")


def test_bad_phone_number_is_asked_again(r):
    r.handle("book a check-up", session_id="p")
    r.handle("Sam Lee", session_id="p")
    out = r.handle("call me whenever", session_id="p")
    assert out["expect"] == "phone" and "didn't get that number" in out["answer"]


def test_google_calendar_mirror_when_connected(r, monkeypatch):
    calls = []
    monkeypatch.setattr(receptionist_module, "calendar_configured", lambda: True)
    monkeypatch.setattr(receptionist_module, "book_appointment",
                        lambda **kw: calls.append(kw) or {"ok": True, "event_url": "https://cal/x"})
    for msg in ("book a check-up", "Sam Lee", "0412 345 678", "no email"):
        r.handle(msg, session_id="g")
    done = r.handle("yes", session_id="g")
    assert calls[0]["summary"] == "Check-up - Sam Lee (unconfirmed)"
    assert done["event_url"] == "https://cal/x"


# ── Parsing what people say ───────────────────────────────────

@pytest.mark.parametrize("said, email", [
    ("john.smith@gmail.com", "john.smith@gmail.com"),
    ("my email is John.Smith@Gmail.com", "john.smith@gmail.com"),
    ("john dot smith at gmail dot com", "john.smith@gmail.com"),
    ("it's anna underscore lee at outlook dot com dot au", "anna_lee@outlook.com.au"),
    ("my email address is bob dash jones at example dot org", "bob-jones@example.org"),
    ("no idea", None),
])
def test_parse_email(said, email):
    assert _parse_email(said) == email


@pytest.mark.parametrize("said, phone", [
    ("0412 345 678", "+61412345678"),
    ("zero four one two three four five six seven eight", "+61412345678"),
    ("oh four double one, two three four, five six seven", "+61411234567"),
    ("+1 555 010 0199", "+15550100199"),
    ("12", None),
])
def test_parse_phone(said, phone):
    assert _parse_phone(said) == phone


def test_this_number_uses_the_callers_number():
    assert _parse_phone("yes, this number", "+61400111222") == "+61400111222"
    assert _parse_phone("this number") is None, "web chat has no number to fall back on"


@pytest.mark.parametrize("said, name", [
    ("My name is jane citizen", "Jane Citizen"),
    ("it's Ravi Kumar", "Ravi Kumar"),
    ("Sam O'Brien please", "Sam O'Brien"),
    ("0412 345 678", None),
])
def test_parse_name(said, name):
    assert _parse_name(said) == name


# ── The store and the messages ────────────────────────────────

def test_store_keeps_only_a_hash_and_confirming_twice_is_harmless(db):
    b, token = bookings.create_booking(summary="Check-up", start_local="2030-03-04T10:00:00",
                                       end_local="2030-03-04T10:30:00", name="Sam Lee",
                                       phone="+61412345678", db_path=db)
    import sqlite3

    raw = sqlite3.connect(db).execute("SELECT token_hash FROM bookings").fetchone()[0]
    assert token not in raw and len(raw) == 64
    assert bookings.get_by_token(token, db)["id"] == b["id"]
    first, newly = bookings.confirm_by_token(token, db)
    again, newly_again = bookings.confirm_by_token(token, db)
    assert first["status"] == "confirmed" and newly is True and newly_again is False
    assert bookings.get_by_token("not-a-token", db) is None


def test_calendar_shows_each_clinic_only_its_bookings(db):
    kw = dict(summary="Check-up", end_local="2030-03-04T10:30:00", name="A", phone="+61400000000", db_path=db)
    bookings.create_booking(start_local="2030-03-04T10:00:00", org_id=1, **kw)
    bookings.create_booking(start_local="2030-03-04T11:00:00", org_id=None, **kw)
    bookings.create_booking(start_local="2030-03-04T12:00:00", org_id=2, **kw)
    bookings.create_booking(start_local="2001-01-01T09:00:00", org_id=2, **kw)  # past
    assert [b["start_local"][11:16] for b in bookings.list_upcoming(1, db_path=db)] == ["10:00", "11:00"]
    assert [b["start_local"][11:16] for b in bookings.list_upcoming(2, db_path=db)] == ["12:00"]


class _FakeChannel:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def send(self, to, message, **kwargs):
        self.sent.append((to, message, kwargs))
        return DeliveryResult(ok=self.ok, channel="x", to=to, provider_id=None,
                              error=None if self.ok else "boom")


def test_notify_sends_text_and_email_with_the_link(db, monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://clinic.example")
    monkeypatch.setenv("BRAND_NAME", "Bright Smile Dental")
    b, token = bookings.create_booking(summary="Check-up", start_local="2030-03-04T10:00:00",
                                       end_local="2030-03-04T10:30:00", name="Sam Lee",
                                       phone="+61412345678", email="sam@example.com", db_path=db)
    sms, email = _FakeChannel(), _FakeChannel()
    out = bookings.notify(b, token, sms_channel=sms, email_channel=email, db_path=db)
    assert out == {"sms": "sent", "email": "sent"}
    link = f"https://clinic.example/booking/confirm/{token}"
    assert sms.sent[0][0] == "+61412345678" and link in sms.sent[0][1] and "Bright Smile Dental" in sms.sent[0][1]
    assert email.sent[0][0] == "sam@example.com" and link in email.sent[0][1]
    assert "confirm" in email.sent[0][2]["subject"].lower()
    assert bookings.get_by_token(token, db)["sms_status"] == "sent"


def test_notify_records_a_failure_and_skips_opted_out_numbers(db, monkeypatch):
    b, token = bookings.create_booking(summary="Check-up", start_local="2030-03-04T10:00:00",
                                       end_local="2030-03-04T10:30:00", name="Sam",
                                       phone="+61412345678", email="sam@example.com", db_path=db)
    out = bookings.notify(b, token, sms_channel=_FakeChannel(), email_channel=_FakeChannel(ok=False), db_path=db)
    assert out["email"].startswith("failed")

    monkeypatch.setattr(bookings, "_sms_opted_out", lambda booking: True)
    sms = _FakeChannel()
    out = bookings.notify(b, token, sms_channel=sms, email_channel=_FakeChannel(), db_path=db)
    assert out["sms"] == "opted_out" and sms.sent == []


def test_when_and_phone_text():
    assert bookings.when_text("2030-03-04T14:30:00") == "Monday 4 March at 2:30 pm"
    assert bookings.phone_text("+61412345678") == "0412 345 678"
    assert bookings.phone_text("+15550100199") == "+15550100199"


# ── The patient's confirmation page ───────────────────────────

@pytest.fixture
def client(db):
    c = TestClient(__import__("app.web_ui.main", fromlist=["app"]).app)
    c.cookies.clear()  # the patient is not signed in
    return c


def _booking(db):
    return bookings.create_booking(summary="Check-up", start_local="2030-03-04T10:00:00",
                                   end_local="2030-03-04T10:30:00", name="Sam Lee",
                                   phone="+61412345678", org_id=None, db_path=db)


def test_opening_the_link_shows_the_booking_but_does_not_confirm_it(client, db):
    b, token = _booking(db)
    page = client.get(f"/booking/confirm/{token}")
    assert page.status_code == 200
    assert "Confirm my appointment" in page.text and "Sam Lee" in page.text
    assert page.headers["cache-control"] == "no-store" and page.headers["referrer-policy"] == "no-referrer"
    assert bookings.get_by_token(token, db)["status"] == "unconfirmed"


def test_pressing_confirm_confirms_and_schedules_a_reminder(client, db, monkeypatch):
    reminders = []
    monkeypatch.setattr(bookings, "schedule_reminder", lambda b: reminders.append(b["id"]) or {"ok": True})
    b, token = _booking(db)
    done = client.post(f"/booking/confirm/{token}")
    assert done.status_code == 200 and "You're all set" in done.text
    assert bookings.get_by_token(token, db)["status"] == "confirmed"
    client.post(f"/booking/confirm/{token}")
    assert reminders == [b["id"]], "one reminder, however many times it is pressed"


def test_unknown_link_is_a_404(client):
    page = client.get("/booking/confirm/made-up-token")
    assert page.status_code == 404 and "isn't valid" in page.text


def test_calendar_tab_lists_bookings_with_their_status(db, monkeypatch):
    import app.web_ui.dashboard_routes as dashboard_routes

    seen = {}

    def fake_list(org_id):
        seen["org"] = org_id
        return [{"summary": "Check-up", "start_local": "2030-03-04T10:00:00", "name": "Sam Lee",
                 "phone": "+61412345678", "email": "", "status": "unconfirmed", "id": 3}]

    monkeypatch.setattr(dashboard_routes.bookings, "list_upcoming", fake_list)
    c = TestClient(__import__("app.web_ui.main", fromlist=["app"]).app)
    rows = c.get("/calendar/appointments").json()
    assert seen["org"] is not None
    assert rows[0]["status"] == "unconfirmed" and rows[0]["caller"] == "Sam Lee · 0412 345 678"


# ── Calls ─────────────────────────────────────────────────────

def test_calls_say_triple_zero():
    from app.web_ui.twilio_routes import _speakable

    assert _speakable("If it's severe, call 000 now.") == "If it's severe, call triple zero now."


def test_calls_read_phone_numbers_digit_by_digit():
    from app.web_ui.twilio_routes import _speakable

    assert _speakable("phone 0400 111 222.") == "phone zero four zero zero, one one one, two two two."
    assert _speakable("call you back on +61400111222") == "call you back on zero four zero zero, one one one, two two two"
    assert _speakable("Ring 1800 000 123.") == "Ring one eight zero zero, zero zero zero, one two three."
    assert _speakable("(03) 9123 4567") == "zero three, nine one two three, four five six seven"
    assert _speakable("+15550100199") == "plus one, five five five, zero one zero, zero one nine nine"


def test_calls_spell_out_email_addresses():
    from app.web_ui.twilio_routes import _speakable

    assert _speakable("email Jane.Citizen@gmail.com.") == "email jane dot citizen at gmail dot com."
    assert _speakable("anna_lee-x@outlook.com.au") == "anna underscore lee dash x at outlook dot com dot au"


def test_calls_still_read_times_dates_and_prices_normally():
    from app.web_ui.twilio_routes import _speakable

    for text in ("at 10:30 on 26 October 2026", "it costs $1,250", "booked for 2026-10-26 10:00", "Room 12"):
        assert _speakable(text) == text


def test_booking_question_on_a_call_is_not_followed_by_anything_else(monkeypatch):
    import app.web_ui.twilio_routes as twilio_routes

    monkeypatch.setattr(twilio_routes, "log_activity", lambda **kw: None)
    monkeypatch.setattr(twilio_routes._receptionist, "handle", lambda message, **kw: {
        "answer": "And your email address?", "intent": "appointment", "needs_info": True, "expect": "email"})
    c = TestClient(__import__("app.web_ui.main", fromlist=["app"]).app)
    xml = c.post("/twilio/voice/reply", data={"SpeechResult": "Sam Lee", "CallSid": "CA9",
                                              "From": "+61400111222", "To": "+61300000000"}).text
    assert "And your email address?" in xml
    assert "anything else" not in xml
    assert 'hints="at, dot' in xml


# ── Asking to book is a request, not a FAQ question ───────────

def test_asking_to_book_starts_the_booking_even_with_a_booking_faq(r, tmp_path, monkeypatch):
    import json

    from agent import faq

    path = tmp_path / "clinic_faq.json"
    path.write_text(json.dumps([{"question": "How do I book an appointment?",
                                 "answer": "FAQ: just tell me the day and time.",
                                 "tags": ["book", "appointment", "booking", "check-up"]}]), encoding="utf-8")
    monkeypatch.setattr("agent.faq.FAQ_DATA_PATH", str(path))
    faq.reload_faq()

    asked = r.handle("Hi, can you book me an appointment for next Monday?", session_id="f")
    assert asked["intent"] == "appointment" and "FAQ:" not in asked["answer"]
    how = r.handle("how do I book an appointment?", session_id="other")
    assert how["intent"] == "faq"


def test_the_chat_is_told_never_to_claim_a_booking(monkeypatch):
    monkeypatch.setenv("BRAND_MODE", "clinic")
    assert "Never say an appointment is booked" in receptionist_module._system_prompt()
    monkeypatch.delenv("BRAND_MODE")
    assert "Never say an appointment is booked" in receptionist_module._system_prompt()


def test_a_detail_that_mentions_a_faq_word_is_still_a_detail(r, tmp_path, monkeypatch):
    import json

    from agent import faq

    path = tmp_path / "clinic_faq.json"
    path.write_text(json.dumps([{"question": "How do I book an appointment?", "answer": "FAQ text",
                                 "tags": ["book", "appointment", "check-up"]}]), encoding="utf-8")
    monkeypatch.setattr("agent.faq.FAQ_DATA_PATH", str(path))
    faq.reload_faq()
    seen = []
    r._extract_appointment = lambda m: seen.append(m) or (
        dict(DETAILS) if "10am" in m else {"clarify": "What time, and what is it for?"})
    r.handle("can you book me an appointment for next Monday?", session_id="d")
    out = r.handle("a check-up at 10am please", session_id="d")
    assert out["expect"] == "name", "the detail completed the booking details"
    assert "a check-up at 10am" in seen[-1]


# ── A call that doesn't hear the answer ───────────────────────

@pytest.fixture
def call_client(tmp_path, monkeypatch):
    import app.web_ui.twilio_routes as twilio_routes

    monkeypatch.setattr(twilio_routes, "log_activity", lambda **kw: None)
    monkeypatch.setattr(twilio_routes, "_summarise_call_later", lambda *a, **kw: None)
    monkeypatch.setattr(receptionist_module, "ESCALATION_LOG", str(tmp_path / "esc.jsonl"))
    rec = twilio_routes._receptionist
    rec._pending_bookings.clear()
    twilio_routes._unheard.clear()
    c = TestClient(__import__("app.web_ui.main", fromlist=["app"]).app)
    yield c, rec, twilio_routes
    rec._pending_bookings.clear()
    twilio_routes._unheard.clear()


def _open_booking(rec, sid, stage="name", ask="What's your full name?"):
    import time

    rec._pending_bookings[sid] = {"stage": stage, "ask": ask, "ts": time.time(), "messages": [],
                                  "details": {"summary": "Check-up", "start": "2030-03-04T10:00:00",
                                              "end": "2030-03-04T10:30:00"}}


def _post(c, speech, sid="CAhear"):
    return c.post("/twilio/voice/reply", data={"SpeechResult": speech, "CallSid": sid,
                                               "From": "+61400111222", "To": "+61300000000"}).text


def test_unheard_booking_answer_is_asked_again_not_hung_up(call_client):
    c, rec, _ = call_client
    _open_booking(rec, "CAhear")
    xml = _post(c, "")
    assert "Sorry, I didn't hear that. What's your full name?" in xml
    assert 'actionOnEmptyResult="true"' in xml and 'timeout="8"' in xml
    assert rec.booking_question("CAhear") == "What's your full name?", "the booking is still open"


def test_after_repeated_silence_the_team_is_asked_to_call_back(call_client):
    import json

    c, rec, _ = call_client
    _open_booking(rec, "CAhear")
    _post(c, "")
    _post(c, "")
    xml = _post(c, "")
    assert "asked the team to call you back on zero four zero zero, one one one, two two two" in xml
    assert "<Hangup" in xml
    assert rec.booking_question("CAhear") is None
    rows = [json.loads(line) for line in open(receptionist_module.ESCALATION_LOG, encoding="utf-8")]
    assert rows[-1]["reason"].startswith("BOOKING CALL-BACK:") and rows[-1]["contact"] == "+61400111222"
    assert "Check-up on Monday 4 March at 10 am" in rows[-1]["reason"]


def test_silence_after_anything_else_still_ends_the_call(call_client):
    c, _, _ = call_client
    xml = _post(c, "", sid="CAdone")
    assert "Goodbye" in xml and "<Hangup" in xml and "didn't hear" not in xml


def test_no_thanks_mid_booking_is_an_answer_not_a_goodbye(call_client, monkeypatch):
    c, rec, _ = call_client
    _open_booking(rec, "CAmail", stage="email", ask="And your email address?")
    seen = []
    monkeypatch.setattr(rec, "handle", lambda message, **kw: seen.append(message) or {
        "answer": "Let me check I have that right.", "intent": "appointment", "needs_info": True, "expect": "confirm"})
    xml = _post(c, "no thanks", sid="CAmail")
    assert seen == ["no thanks"] and "<Hangup" not in xml.split("</Gather>")[0]


def test_phone_and_email_questions_allow_pauses(call_client, monkeypatch):
    c, rec, _ = call_client
    monkeypatch.setattr(rec, "handle", lambda message, **kw: {
        "answer": "What's the best phone number?", "intent": "appointment", "needs_info": True, "expect": "phone"})
    xml = _post(c, "Sam Lee", sid="CAph")
    assert 'speechTimeout="3"' in xml and 'timeout="8"' in xml


# ── The demo clinic owns the Twilio number ────────────────────

def test_seed_links_the_twilio_number_to_the_demo_clinic(monkeypatch, tmp_path):
    import importlib.util
    import pathlib

    import auth.db
    from auth.db import init_db
    from auth.sms_routing import init_sms_routing, resolve_org_by_twilio_number
    from auth.tenancy import create_org, init_tenancy

    monkeypatch.setattr(auth.db, "DB_PATH", str(tmp_path / "auth_users.db"))  # its own database
    init_db()
    init_tenancy()

    spec = importlib.util.spec_from_file_location(
        "seed_demo", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py")
    seed = importlib.util.module_from_spec(spec)
    monkeypatch.setenv("DEMO_PASSWORD", "test-only")
    spec.loader.exec_module(seed)

    init_sms_routing()
    demo, other = create_org("Demo Clinic Test"), create_org("Someone Else Test")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+61399990000")
    monkeypatch.setattr(seed, "call", lambda method, path, body=None: (200, {"id": demo}))
    seed.link_twilio_number()
    assert resolve_org_by_twilio_number("+61399990000") == demo

    monkeypatch.setattr(seed, "call", lambda method, path, body=None: (200, {"id": other}))
    seed.link_twilio_number()  # already taken by the demo clinic: left alone
    assert resolve_org_by_twilio_number("+61399990000") == demo
