# Q&A prep: Saifur Rahman Bhuiyan

A study sheet for the poster session and the Week 12 interview. It explains the work that
is on your tickets so you can answer "how" and "why" in your own words. It is not your
journal; that has to be yours. Read the code named here before the session.

## What you built, in one breath each

| Ticket | What it is | Where |
|---|---|---|
| PROJ-469 live dashboard | The operator dashboard gets updates pushed over a WebSocket instead of polling every 30 seconds | `app/web_ui/ws_routes.py`, `_notify_ws` in `app/web_ui/activity_db.py`, WS client in `static/js/app.js` |
| PROJ-470 voice languages | The phone receptionist can greet and speak in 7 languages | `app/web_ui/voice_languages.py`, language routes in `app/web_ui/twilio_routes.py` |
| PROJ-471 schema audit | Tests that prove there is no duplicate data store and each database holds what it should | `tests/test_schema_audit.py` |
| PROJ-472 end-to-end test | One test from organisation to contact to reminder to delivery, with external services mocked | `tests/test_e2e_production_flow.py` |
| PROJ-483 FAQ fix | The hours answer no longer mentions a Telegram bot that is not running | `config/faq_seed.json` |
| PROJ-489/490 site | The marketing site sells reminders and a receptionist to clinics, salons and trades, plus an architecture and privacy page | `site/index.html`, `site/architecture.html` |
| PROJ-491 review | Brought your dashboard branch up to date and into a PR (#36) | PR #36 |
| PROJ-492 CSV export | Download reminder history and daily delivery trends as CSV | `history_csv` in `app/web/reminders.py`, `/analytics/export.csv` |

## How the pieces work

**WebSocket dashboard.** `DashboardConnectionManager` keeps the list of open browser
connections. When something happens (`log_activity`, a delivery event, a status change),
`activity_db` calls `_notify_ws`, which calls `broadcast_dashboard_event`, which sends a JSON
message to every connected browser. The browser updates the tiles and the activity feed
without reloading. The client sends `ping` and gets `pong` as a keepalive, and reconnects if
the connection drops. `/ws/status` reports how many clients are connected.

**Voice languages.** `VOICE_MAP` maps a language code (for example `es-US`) to a Twilio
Polly voice. `detect_language` guesses from the caller's words: Chinese and Hindi by their
scripts, and French, German and Spanish by common words. `resolve_voice` falls back to the default
(`en-AU`) when the code is unknown. An operator can set the default with
`POST /twilio/voice/language`.

**CSV export.** `history_csv` lists reminders that were sent, blocked or failed, newest
first, for one organisation, and writes them with Python's `csv` module.

## Things we found and fixed in your work (expect a question on these)

1. **The WebSocket had no login check.** The login middleware only covers normal HTTP
   requests, so `/ws/dashboard` accepted anyone and streamed caller numbers, call summaries
   and delivery recipients. It now checks the session cookie before accepting and refuses
   with code 1008. Test: `test_dashboard_websocket_rejects_anonymous_connections`.
2. **The language controls were public.** `/twilio/voice/language(s)` sit under `/twilio/`,
   which is public because the real Twilio webhooks verify their own signature. They are
   operator controls, not webhooks, so they now need a login.
3. **CSV formula injection.** A message starting with `=`, `+`, `-` or `@` runs as a formula
   when the export opens in Excel. `csv_safe` prefixes those cells with an apostrophe and
   leaves phone numbers alone.
4. **The home page showed numbers we could not back up** ("98.5% delivery rate") and
   research-agent leftovers. They were replaced with true statements.

## Likely questions, and honest answers

- **Why a WebSocket and not faster polling?** Polling asks every few seconds even when
  nothing changed, and still lags. A WebSocket pushes only when something happens, so it is
  both lighter and instant.
- **What happens if the connection drops?** The client reconnects with a delay, and the
  `refresh` message re-sends the current stats.
- **How do you pick the language on a call?** The operator default applies to the greeting.
  After that, the caller's speech is checked with `detect_language`, and the voice follows.
  It is a simple word and script check, not a trained model, so short or mixed phrases can
  be missed.
- **Does it scale to many organisations?** Not yet. The dashboard feed and the analytics
  export are not organisation-scoped (the analytics tables have no organisation column).
  For one organisation that is fine; for many it would leak counts across them. Say this
  plainly and describe the fix: add an organisation id to the delivery history.
- **Is the data safe on the dashboard feed?** Now yes (login required), but it was not
  before we reviewed it. Explain finding 1 above; it shows you understand why middleware
  does not cover WebSockets.
- **Why is SMS not shown delivering?** US carriers block unregistered texts from our US
  number. The registration is submitted and waiting. Voice, email and the dashboard are
  unaffected.
- **What would you do next?** Scope analytics per organisation, add a contact or sign-up
  form behind "Start a Pilot", and bring the Features page in line with the reminders
  positioning (it still describes the research agents).

## Run it yourself before the session

```bash
python3 -m pytest tests/test_websocket.py tests/test_multilingual_voice.py tests/test_reminders_export.py -q
```

Then open the live dashboard in two browser tabs, make a test call, and watch the second tab
update without a refresh.
