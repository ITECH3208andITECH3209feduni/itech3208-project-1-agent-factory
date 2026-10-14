# Data sovereignty and where the demo runs

PROJ-476. Brief reference: Part C (data ethics, data sovereignty) and the product vision
("intelligent, privacy-first communication at the edge", Privacy Act 1988).

This note says plainly what is true today, so the poster and the marketing site never claim
more than the platform does. It is not legal advice and does not claim Privacy Act compliance.

## 1. Two deployment targets

| | **Target: on-premise edge** | **What we run for the poster: Render free plan** |
|---|---|---|
| Where | A machine the client controls (for example a Mac mini on their premises), reached through a Tailscale Funnel or Cloudflare tunnel | Render's cloud, one Docker web service (`render.yaml`) |
| Storage | SQLite files and the CRM JSON store on the client's own disk (`docker-compose.web.yml`, `docs/MAC_MINI.md`) | Ephemeral container disk, wiped on every sleep or restart |
| Data in it | The client's real contacts, consent records and reminders | **Seeded fictional demo data only** (`scripts/seed_demo.py`, 555-01xx numbers). No real customer data |
| Region | The client's choice | Render's default region (US), not Australian |
| Status | Documented and scripted. The Mac mini we own is blocked by Activation Lock, so it has not been exercised end to end | Live, used for the demo |

**The poster demo is not on-premise.** It runs in the cloud on a free plan so that visitors
can try it. The edge model is the product's design target, and the same code and images
run in both places. Nothing real is stored on the demo host, which is why using it for the
demo does not undermine the sovereignty claim. Do not describe the demo itself as "on the
edge" anywhere.

## 2. What data exists and where it lives (one deployment)

| Data | Stored in | Notes |
|---|---|---|
| Organisations, users, password hashes | `AUTH_DB_PATH` (SQLite) | Passwords are hashed with bcrypt. Session cookies are HMAC-signed |
| Contacts, consent state, preferences | Tenancy tables in the auth DB and the CRM store (`CRM_STORE_DIR`) | Every row is scoped to an organisation |
| Consent audit trail | `consent_events` | Who opted in or out, when, and by which route (for example STOP by SMS) |
| Reminders and delivery history | `REMINDERS_DB`, `delivery_history` | Status from Twilio and email webhooks |
| Conversations and call activity | `MEMORY_DB`, `activity`, `call_summaries` | Receptionist transcripts and post-call summaries |
| Secrets (API keys, Twilio token, SMTP password) | `.env` locally, Render environment variables on the demo | Never committed. `scripts/audit_secrets.sh` runs in CI |

All of it lives with the deployment. There is no central copy we operate.

## 3. What leaves the deployment, and to whom

Keeping data at the edge does not mean nothing crosses the boundary. Using the product's
features sends the following to third parties, and a client must be told this:

| Third party | What they receive | When |
|---|---|---|
| **Twilio** (US) | The message text, the recipient's phone number, call audio and speech transcripts | Every SMS, voice reminder or inbound call |
| **Anthropic API** (US) | The caller's words and recent conversation, to write receptionist replies, extract appointment details and summarise calls | Receptionist and post-call summary only. Contacts are not bulk-sent; the keyword fallback in `agent/call_summary.py` works without the model |
| **SMTP provider** (for example Gmail) | Recipient address, subject and body | Email reminders and password-reset emails |
| **Google Calendar** (optional) | Appointment title and time | Only if calendar booking is configured |

Consequence for Australian clients: phone numbers and message content do pass through US
services. If that is unacceptable for a client, the honest options are to disable the
channel, or to replace the provider. It is not something the edge deployment alone solves.

## 4. Privacy and consent controls that exist today

- **Consent before sending.** No message is sent to a contact who has not opted in or who
  has opted out. The check runs before every send (`app/web/consent.py`).
- **STOP works automatically.** STOP, START and HELP are handled on inbound SMS before the
  AI sees the message (`integrations/sms_consent.py`), and the change is audit-logged.
- **Quiet hours and channel preferences** are respected per contact.
- **Tenant isolation.** Each organisation sees only its own contacts, reminders and templates.
- **Public routes are an explicit allowlist.** Everything else requires login; Twilio
  webhooks verify `X-Twilio-Signature`.

## 5. How this lines up with the Australian Privacy Principles (informal)

Mapping for discussion with the client, not a compliance claim.

| APP | What the platform does | Gap |
|---|---|---|
| APP 1, 5 (open handling, notice) | Marketing site and docs describe what is stored | Site has no privacy page yet (PROJ-490) |
| APP 3, 6 (collection, use) | Only contact details the organisation enters; used for reminders it schedules | No per-purpose tagging |
| APP 7 (direct marketing) | Opt-in required, STOP honoured | None known |
| APP 8 (cross-border disclosure) | Disclosed in section 3 above | Twilio, Anthropic and SMTP are offshore |
| APP 11 (security) | bcrypt, signed sessions, login required, signature-checked webhooks, secrets outside git | No encryption at rest beyond the host disk; no automated retention or purge |
| APP 12, 13 (access, correction) | Contacts can be viewed and edited in the CRM | No data-export or delete-my-data workflow |

## 6. Known limits to state, not hide

- No automatic data retention limit or deletion workflow.
- No encryption of the SQLite files beyond whatever the host disk provides.
- The on-premise path has not been run end to end on the Mac mini.
- The demo host is in the US and loses its data on every restart.
- SMS to US numbers is blocked by Twilio A2P registration (Twilio-side), so the demo shows
  voice and the dashboard; email needs SMTP configured.

## 7. Wording to use

- Poster and site: "Designed for on-premise deployment, so a client's data stays on their
  own machine. The live demo runs in the cloud with fictional data only."
- Never: "Your data never leaves your premises" (messages and calls pass through Twilio,
  and receptionist text goes to the Anthropic API).
