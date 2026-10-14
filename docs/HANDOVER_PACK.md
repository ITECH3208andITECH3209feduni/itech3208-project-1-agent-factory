# Client handover evidence pack (PROJ-498)

Everything the client and Moodle need, in one place. Each row says where the item is and whether it is ready. **Do not submit until every row is ✅.** Then link this file, or the zip made from it, in PROJ-498.

Client: Zakir Ullah Shah, Federation University (ITECH3208). Product: Agent Factory, a multi-tenant reminder and communication service.

## Checklist

| # | Item | Where | State |
|---|---|---|---|
| 1 | Final repository | https://github.com/ITECH3208andITECH3209feduni/itech3208-project-1-agent-factory, branch `main` | ✅ |
| 2 | Release tag | `v0.5.0`, to be tagged on `main` after the Sprint 5 PRs merge (latest now: `v0.4.0`) | ⏳ tag after merge |
| 3 | Handoff document: state, architecture, security, gaps | [`HANDOFF.md`](../HANDOFF.md) | ✅ (update the date and section 2 at submission) |
| 4 | Deploy runbook: laptop, Render, Mac mini, Fly; email set-up | [`docs/DEPLOY.md`](DEPLOY.md), [`docs/MAC_MINI.md`](MAC_MINI.md) | ✅ |
| 5 | Where data lives and what leaves the machine | [`docs/DATA_SOVEREIGNTY.md`](DATA_SOVEREIGNTY.md) | ✅ |
| 6 | Live demo | https://agent-factory-fvtq.onrender.com (open `/status` first; the free host sleeps) | ✅ running |
| 7 | **Client's written feedback** | `docs/handover/client_feedback.pdf` (save the email or signed note here) | ❌ **blocked: ask the client** |
| 8 | Test and CI results | Section "Test results" below; add a screenshot of the green GitHub Actions run on `main` | ⏳ CI screenshot after merge |
| 9 | Email delivery evidence | `python scripts/email_smoke.py --to <you> --reminder` output, plus screenshots of both received emails and a password-reset email | ⏳ needs the Gmail app password (PROJ-481) |
| 10 | SMS / voice evidence | `python scripts/sms_status.py` output; [`docs/SMS_DELIVERY.md`](SMS_DELIVERY.md); recording of the receptionist call | ⏳ needs Twilio credentials (PROJ-482) |
| 11 | Known limitations and descoped items | Section below | ✅ |
| 12 | Video demo | Uploaded with the final product (PROJ-497) | ⏳ Dilraj |
| 13 | Posters | `docs/poster/` (PDFs of posters 1 to 4) | ⏳ Poster 3 needs a rebuild from the live site |

Keep the evidence files in `docs/handover/`. Never put `.env` values, Render secrets, the demo password or Twilio tokens in a screenshot.

## Test results

Run on 14 October 2026 on branch `proj-479-480-reminder-form-ui`, from the repo root:

```
.venv\Scripts\python.exe -m pytest -q
555 passed, 7 skipped
```

Provider credentials are blanked in `tests/conftest.py`, so the suite never sends a real SMS or email. CI on GitHub runs the same suite plus the script suites, a secrets audit and a Docker smoke test on every push to `main`.

## What was delivered against the brief

| Brief | Delivered |
|---|---|
| Organisations, accounts, contacts with CSV import | Yes |
| Consent: opt-in, STOP, quiet hours, enforced on every send | Yes |
| One-off and recurring reminders; edit, pause, resume, cancel, reschedule from the UI | Yes (PROJ-479) |
| Message templates with personalisation and preview | Yes (PROJ-480): `{name}`, `{first_name}`, `{date}`, `{time}`, `{org}` |
| Delivery by SMS, voice and email, with retries and delivery status | Yes; live email needs the SMTP set-up, US SMS needs A2P registration |
| Password recovery by email | Yes (PROJ-481) |
| Dashboard and analytics | Yes |
| AI receptionist (voice and SMS) with FAQ, booking, escalation, call summaries | Yes |
| On-premise (edge) deployment | Designed and documented; the demo runs on Render |

## Known limitations and descoped items

- **SMS to US numbers** is blocked by carrier rules until the Twilio number completes A2P 10DLC registration. Production for an Australian client should use an Australian sender. See [`SMS_DELIVERY.md`](SMS_DELIVERY.md).
- **Render free plan** (demo host only): it sleeps after about 15 minutes idle, wipes its data on restart (demo data is re-seeded), and reminders only send while it is awake.
- **Two login systems still coexist** (session users and email/org users). One form signs in to both; consolidation is open (PROJ-487).
- **Templates are a minimal store** built for PROJ-480 (create, edit, delete, merge fields). Template versioning, sharing and per-channel variants are not built (see PROJ-484 and PROJ-485).
- **Conversational rescheduling** of an existing booking (PROJ-486) and **role-based access control and API keys** (PROJ-488, stretch) are not delivered.
- **Telegram** appears as a contact channel but has no delivery adapter; reminders to a Telegram-preferred contact are marked failed with that reason.
- The **information website** (`site/`) is not published on GitHub Pages; that needs a repository admin.
