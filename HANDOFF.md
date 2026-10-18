# Agent Factory: Handoff

State of the project as of **12 October 2026**, written so someone new (or you, after a break) can pick it up cold.
Repo: `ITECH3208andITECH3209feduni/itech3208-project-1-agent-factory`. Branch `main` is the source of truth.
Jira project: **PROJ** (students-team-c20eds71.atlassian.net).

---

## 1. What this is

A multi-tenant **Reminder & Communication Service** for client Zakir Ullah Shah (Federation University, ITECH3208). Organisations register, manage contacts, and schedule reminders that go out by SMS, voice or email, with consent enforced on every send. An AI Receptionist (Twilio voice and SMS, Claude) is an optional extra on the same stack.

Team: Dilraj Singh (product owner, lead dev), Prabhjot Singh (scrum master, full-stack), Dhiman Roy (backend: accounts and consent), Saifur Rahman Bhuiyan (delivery, analytics, web).

**Direction change:** the poster session replaces Sprints 4 and 5 as the final assessment. See section 8.

---

## 2. Where we are

| Area | State |
|---|---|
| Sprint 4 code (all four branches) | **On main.** PR #20 merged 7 Oct, tagged `v0.4.0` |
| CI on main | **Green** (pytest 485 on main, 491 on `fix-web-login`; script suites, secrets audit, Docker smoke test) |
| Platform running | **Yes**, locally in Docker, plus a temporary public tunnel (see section 4) |
| Hosting prep, Twilio webhook security, login lock-down, CRM fixes, Mac mini setup | **On main** (PRs #21 to #26) |
| Web login form (email or username) | **Fixed on branch `fix-web-login`, not yet committed or merged.** On main the form shows `[object Object]` and the demo user cannot sign in |
| Live phone number (voice) | **Working.** A real Twilio call reached the app; spoken-reply path verified |
| SMS to US numbers | **Blocked** by Twilio A2P registration (Twilio-side, not code) |
| Email | **Off.** SMTP values are not in `.env` |
| Always-on hosting | **Not yet.** Plan is the Mac mini (section 4) |

### Merged PRs since Sprint 4

| PR | What |
|---|---|
| #20 | Sprint 4 full integration (merged 7 Oct) |
| #21 | Hosting prep: `fly.toml`, one-machine start script, `/status/scheduler` health check, secrets script, runbook |
| #22 | Free local deploy: `docker-compose.web.yml` + `scripts/demo_up.sh` (Cloudflare quick tunnel) |
| #23 | (Prabhjot) Verify Twilio signatures on **every** webhook; align production env names |
| #24 | `demo_up.sh` binary-log fix |
| #25 | **Security:** require login on every route except an explicit public list |
| #26 | CRM fixed under `/crm`, data persistence fix, Mac mini setup, demo seed data |

---

## 3. Jira status

All Sprint 4 tickets (PROJ-392 to 452) are Done. Sprint 5 backlog was PROJ-453 to 472.

**Open now:** PROJ-456 (hosting epic, In Progress) and PROJ-467 (secrets/env, In Review). Only the SMTP values are missing for 467.

**Done but worth a second look:**
- **Dhiman's auth consolidation (PROJ-455, 461 to 464)** is marked Done in Jira, but **no PR, commit or branch for it exists**. Both login systems still coexist. Either find the work or reopen the tickets.
- **Saifur's PROJ-453 and 469 to 472** (WebSocket dashboard, multi-language voice, schema audit, e2e test) are marked Done. The code is one commit on branch `feat/proj-453-realtime-dashboard` (about 1,440 lines) with **no PR and nothing merged**. Untested by us. PROJ-472 ("e2e test on production") could not have run on a real production host.
- PROJ-465 and 468 are closed under Prabhjot's name; the work was done by Dilraj (PRs #21, #22).

---

## 3a. Sprint 5 progress (as of 14 Oct 2026, evening)

Verified against GitHub, not just Jira. PR states change fast; check GitHub for the current list.

| Area | Who | State |
|---|---|---|
| Reminder form (recurrence, pause, cancel, reschedule), template picker, password-reset wiring, SMS evidence, poster 3 builder, handover checklist | Prabhjot | **Merged** (PRs #29, #30) |
| Email-owner profile fix (PROJ-487) | Dhiman | **Merged** (#32) |
| Merge fields at send time (PROJ-485), template CRUD (PROJ-484), conversational rescheduling (PROJ-486) | Dhiman | PRs #33, #34, #35 open, CI green |
| RBAC and organisation API keys (PROJ-488) | Dhiman | PR #31 open; the fix PR #37 (encoding damage, 7 failing tests) is merged into its branch |
| Marketing site rework, CSV export, multi-language voice, WebSocket dashboard, FAQ hours fix | Saifur | PR #36 open (his branch merged with current main; the language controls now require login) |
| Post-call summary, FAQ inside booking, data-sovereignty note, main poster draft, recording scripts, timezone fix | Dilraj | Summary, booking, note and posters merged (#27); timezone fix is PR #28 |

**Needs a person, not code:** recordings (PROJ-497), individual journals (PROJ-499), the live
email and SMS proof (PROJ-481/482: SMTP secrets, Twilio A2P), the Render redeploy from `main`
(PROJ-475), the client's written feedback, and the session date.

**Known:** `tests/conftest.py` now gives the auto-login test user org 1 and the admin role (needed
once RBAC lands). A plain username-only account has no organisation, so RBAC locks it out of `/crm`;
email-registered accounts (including the demo login) are fine.

## 4. How to run it

### Fastest: your laptop, temporary public URL (free, no account)
```bash
./scripts/demo_up.sh                 # builds, starts, opens a Cloudflare quick tunnel
python3 scripts/seed_demo.py         # demo login + sample data (once)
./scripts/demo_up.sh --down          # stop
```
The tunnel URL **changes on every start**, so re-paste the Twilio webhooks after each run.

### Mac mini (always on, permanent free URL): preferred
Full setup in **`docs/MAC_MINI.md`**: keep it awake, Docker Desktop at login, Tailscale Funnel, then `./scripts/serve_up.sh`. Paste the Twilio webhooks **once**. `launchd/com.agentfactory.serve.plist` starts it at login. The Tailscale account setup has **not** been done yet.

### Render (free, no Mac mini needed)
The Mac mini has an Activation Lock, so the plan changed. `render.yaml` + `docs/DEPLOY.md` (Option A2) deploy the whole stack to Render's free plan. Permanent URL, webhooks pasted once. It sleeps when idle and loses data on restart, so demo data is re-seeded on every boot (`SEED_DEMO=true`, needs `DEMO_PASSWORD`). Not yet deployed: needs the Render Blueprint step and secrets entered in the Render dashboard.

### Other
`docs/DEPLOY.md` also covers Fly.io (paid, needs a card). `fly.toml` is ready if ever wanted.

### Demo login and data
`scripts/seed_demo.py` creates a demo organisation ("Demo Dental Clinic") and user, 6 contacts and 5 reminders. Sign in at `/login` with the **email** `poster.demo@example.com`; the password is a constant at the top of that file. All numbers are fictional 555-01xx; all reminders are 8+ days out so **nothing can send during a demo**. Safe to re-run.

Open in the browser once it is up (local: `http://localhost:8000`):

| Page | URL |
|---|---|
| Home (3 agents) | `/` |
| Reminders dashboard | `/crm/dashboard` |
| Contacts | `/crm/contacts` |
| Reminders | `/crm/reminders` |
| AI Receptionist (chat, activity, analytics) | `/` then pick AI Receptionist |

**Login bridge (branch `fix-web-login`):** `/auth/login` now accepts either `email` (checked against the org/token user table) or `username` (the older session users), and always sets the `af_session` cookie. `static/js/auth.js` stores a placeholder token so `requireAuth()` does not loop back to `/login`. Covered by `tests/test_web_login.py` (6 tests). The two auth systems are still separate underneath; this only lets one form sign in to both.

### Tests
```bash
python3 -m pytest -q                     # 491 pass on fix-web-login (485 on main)
for s in scripts/test_*.py; do python3 $s; done
```
Tests never use real Twilio or email credentials (`tests/conftest.py` blanks them).

---

## 5. Architecture in one screen

- **One FastAPI app**, `app/web_ui/main.py`. Routers: auth, orgs, receptionist, calendar, KB, Twilio, dashboard, delivery, analytics, settings.
- **CRM sub-app** (`app/web/main.py`) is **mounted at `/crm`**: dashboard, contacts, reminders UI and API. A middleware prefixes its internal URLs when mounted.
- **Login gate:** `require_login` middleware in `app/web_ui/main.py` (default-deny). Public list is `_PUBLIC_EXACT` / `_PUBLIC_PREFIXES` in that file.
- **Delivery** (`agent/delivery/`): SMS, voice, email behind one interface with exponential backoff and retriable vs non-retriable errors.
- **Reminders engine** (`agent/reminders/`): SQLite store with atomic claiming (no double sends), timezone-safe recurrence, `scheduler.py`, and `web_bridge.py` (sends reminders created in the dashboard).
- **Receptionist bookings** (`agent/bookings.py`, `app/web_ui/booking_routes.py`): asking to book (web chat, SMS or a call) collects the day and time, then name, phone and email, reads them back, and on "yes" saves an **unconfirmed** booking in `bookings.db` (next to `MEMORY_DB`, so `/data` on Render). The patient gets a text and an email with a link to `/booking/confirm/<token>` (public; only a hash of the token is stored). Opening the link shows the booking; only the Confirm button confirms it (link previews can't). Confirming schedules a reminder and the Calendar tab shows **Booking confirmed**. Google Calendar is optional and only mirrored when connected. Links use `APP_BASE_URL`, so it must be the public URL.
- **Heartbeat:** both loops write `agent/reminders/heartbeat.py`; `GET /status/scheduler` is 200 while they tick, 503 if not.
- **State:** all SQLite files in the Docker volume at `/data` (`AUTH_DB_PATH`, `AUTH_DB`, `MEMORY_DB`, `REMINDERS_DB`, `KB_DB`, and `bookings.db` beside `MEMORY_DB`) plus the CRM JSON store at `CRM_STORE_DIR=/data/store`. One machine only, SQLite has a single writer.
- **Container:** `app/web_ui/Dockerfile`; `deploy/start.sh` runs web + scheduler + bridge together.

---

## 6. Security state: read this

- **Fixed (PR #25):** before it, the public URL exposed contacts, reminders, call logs, and `POST /delivery/send` (anyone could send SMS or email through our Twilio account) with no login. Now default-deny; unauthenticated requests get 401, or a redirect to `/login` for pages.
- **Twilio webhooks** verify `X-Twilio-Signature` on all three routes when `TWILIO_VALIDATE_SIGNATURE=true` (set automatically by the scripts when a Twilio token exists). Unsigned requests return 403.
- **`/integrity` and `/` are public on purpose** (`tests/test_integrity.py` requires it). `/integrity` calls the Claude API, so it can be abused if the URL is public.
- **Two login systems still coexist** (session login on the web UI, and the token-based one in `auth/`). Consolidation is not done.
- Secrets live only in `.env` (gitignored). Never paste them into chat or commit them. `.env` is **not** baked into images; it is passed at run time.

### Incident to know about
While adding config I completed the Twilio settings in `.env`; two consent tests then ran with **real credentials** and attempted to send test texts ("Hello", "Allowed") to the hard-coded test number `+61 400 123 456`. Up to about 6 attempts, delivery unknown. **Do not touch the Australian number in Twilio.** The test suite now blanks all provider credentials so this cannot happen again. To check what happened, see Twilio Console → Monitor → Logs → Messaging, filtered to that number. The tests now use a fictional ACMA-reserved number (`0491 570 156`) instead.

---

## 7. Known gaps and open items (priority order)

0. **Commit, PR and merge branch `fix-web-login`** (login fix, `tests/test_web_login.py`, updated `seed_demo.py`, this file). Without it, main's login form is broken for the demo user. Email-registered users also have no org mapping for `/orgs/me` yet.
1. **Poster session deliverables** (section 8): not started.
2. **Hosting:** deploy to Render (`docs/DEPLOY.md`, Option A2). The Mac mini is blocked by Activation Lock; `docs/MAC_MINI.md` applies only if that is cleared.
3. **Email:** add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` to `.env` (a Gmail app password works). Then restart and send a test. Closes PROJ-467 and the epic.
4. **SMS:** needs Twilio A2P registration (may cost a fee; check the number's page). Until then show SMS via the web dashboard or a recording and say so on the poster.
5. **Resolve the Jira/code mismatches** for Dhiman's auth work and Saifur's branch (section 3).
6. **Twilio webhooks** currently point at an old temporary URL; re-paste after any restart, or once on the Mac mini.
7. **GitHub Pages is not enabled** on the repo, so the information website (`site/`, deploy workflow exists) is not live. Settings → Pages → Source: GitHub Actions (needs admin).
8. **`master` and `main` have diverged** (master has about 29 commits main lacks, including secrets work). Decide how to reconcile; `scripts/audit_secrets.sh` and `scripts/smoke_mcp_stdio.py` were copied from master.
9. ~~Replace the Australian test number in the tests~~ Done on `fix-web-login`.
10. Deliver the optional extras only if time allows: multi-language voice, WebSocket dashboard (Saifur's branch).

---

## 8. Poster session (replaces Sprints 4 and 5)

From the lecture slides. Format is a trade fair, hybrid (in person + MS Teams channel). Each team produces, in its channel:
1. a **marketing-style intro**: vision, achievements, **client feedback**;
2. a **technical presentation**: architecture and why it's a good solution;
3. a **demo** of the product;
4. a **team intro**: each member's role, contribution, what they learned;
5. **times you'll be available** to answer questions.

Poster must include: vision statement, team name/logo/roles, product name, client and problem, goals, methods (architecture **diagrams**), validation (how we know it meets the client's needs), results incl. client response. Design: readable at two distances, 2 to 3 colours and typefaces, no walls of text, no jargon.

Final marking: value delivered to the client, **individual understanding** (Week 12 individual interview), quality incl. documentation, implementation (be ready to show code). Submit the final product, a **video demo**, and **client handover evidence** to Moodle. Finish the individual journal before the interview.

**Still needed:** session date, poster format (PowerPoint deck vs one PDF), the client's written feedback, one-line roles per team member. Planned build: four posters (marketing, architecture, demo how-to with screenshots, team) in the navy/gold style of the Sprint 3/4 documents, plus scripts for the three recordings.

---

## 9. Gotchas that cost time

- **Tunnel URL is temporary** (`demo_up.sh`); only the Mac mini + Tailscale gives a permanent one.
- **`load_dotenv()` searches parent directories**, so from a git worktree it can find the main checkout's `.env`. Tests now defend against this.
- **zsh:** never name a shell variable `path`; it overwrites `PATH` and commands vanish.
- **Docker image** must copy `auth/`, `contracts/`, `integrations/`, `deploy/` (it did not originally; CI caught it).
- **Behind a TLS proxy**, uvicorn needs `--proxy-headers`, or Twilio signature checks see `http://` and reject everything. `deploy/start.sh` already does this.
- **Usernames** can't contain `@` (`3 to 32 characters: letters, numbers, . _ -`).
- **Sprint 4 deleted the `/status` handler** by accident; it's restored with a regression test. `/status` must stay public.
- Twilio **trial** accounts can only message verified numbers.

---

## 10. Where to look

| Need | File |
|---|---|
| Run on laptop / Fly / Mac mini | `docs/DEPLOY.md`, `docs/MAC_MINI.md` |
| Where data lives, what leaves it, demo vs on-premise | `docs/DATA_SOVEREIGNTY.md` |
| Release notes | `CHANGELOG-agent-factory.md` (the root `CHANGELOG.md` is upstream NanoClaw's) |
| Env var names | `.env.example`, `config/settings.py` (`validate_env()`) |
| Public/private route list | `app/web_ui/main.py` (`_PUBLIC_EXACT`, `_PUBLIC_PREFIXES`) |
| Twilio webhooks | `app/web_ui/twilio_routes.py` |
| Reminders and delivery | `agent/reminders/`, `agent/delivery/` |
| Demo data | `scripts/seed_demo.py` |
| Sprint 3 and 4 reports, team artefacts | PDFs built earlier in this project (Sprint 4: `AgentFactory_Sprint4_TechnicalReport_V1.0`, `..._TeamArtefacts_V1.0`) |
