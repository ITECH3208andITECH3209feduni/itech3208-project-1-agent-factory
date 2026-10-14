# Recording scripts (PROJ-497)

Three short recordings for the Teams channel, plus the video demo for Moodle (the demo
recording is both). Say the words in your own voice; the scripts are the order and the facts.
Anything in [square brackets] is missing input. Do not record until it is filled in.

## Before you press record (every take)

1. Wake the live site: open `https://agent-factory-fvtq.onrender.com/status` and wait for
   `{"status":"ok","agent":"ready"}`. The free host sleeps after about 15 minutes.
2. Sign in at `/login` with `poster.demo@example.com` and the `DEMO_PASSWORD` set in Render.
3. Check the demo data is there: 6 contacts, 5 upcoming reminders. It reloads on every boot.
4. Close other tabs and notifications. Browser at 100% zoom, window about 1280 wide.
5. Have the phone ready to call the receptionist. Keep a backup recording on disk, in case
   Wi-Fi or the host fails on the day.
6. Never show the `.env`, Render environment values, the Twilio console token, or the demo password on screen.

## 1. Marketing intro (about 2 minutes)

| Time | Say | Show |
|---|---|---|
| 0:00 | "We are [team name]. Our product is Agent Factory." | Title slide or the `/showcase` home page |
| 0:10 | The problem: service businesses lose money to no-shows and spend hours phoning customers. | Poster 1 |
| 0:35 | Our client, Zakir Ullah Shah, asked for reminders by SMS and email that always respect consent, and an AI receptionist that answers calls. | Poster 1 vision statement |
| 1:00 | What we built: accounts, contacts with CSV import, consent and STOP, scheduled and recurring reminders, delivery by SMS, voice and email, dashboard and analytics. | Dashboard, contacts |
| 1:30 | What the client said: [CLIENT QUOTE, written feedback needed]. | Quote on screen |
| 1:50 | "Come and try it. The QR code on the poster opens the live demo." | QR code |

Only claim what is live. If email or SMS is still waiting on setup when you record, say so
(see `docs/DATA_SOVEREIGNTY.md` section 6).

## 2. Technical presentation (about 3 minutes)

| Time | Say | Show |
|---|---|---|
| 0:00 | "One container runs three things: the web app, the reminder scheduler and a bridge that sends reminders created in the dashboard." | Poster 2 architecture diagram |
| 0:30 | "Everything passes the consent gate first. No opt-in, no message. STOP is handled before the AI sees the text." | Consent gate box |
| 1:00 | "A reminder is claimed atomically, so it cannot send twice. Recurring times follow the local clock through daylight saving." | Reminders engine box |
| 1:25 | "Each organisation sees only its own data. Everything except a short public list needs login. Twilio calls are signature-checked, and a forged call gets 403." | Run `curl -X POST .../twilio/voice` in a terminal and show the 403 |
| 1:55 | "The receptionist answers from an FAQ first, then escalates to a human, then books, then falls back to Claude. A booking in progress survives side questions. After a call we store a summary with a sentiment and priority." | Activity tab with tagged calls |
| 2:25 | "We design for on-premise hosting so the client's data stays on their machine. This demo runs on a free cloud plan with fictional data only. Phone and message content do pass through Twilio, and receptionist text goes to the Anthropic API." | "Where it runs" section of Poster 2 |
| 2:50 | "516 automated tests run in CI on every change." | CI page or test output |

## 3. Product demo (about 3 minutes, also the Moodle video demo)

1. **Sign in** (0:00): `/login`. "This is a demo organisation with fictional data."
2. **Contacts** (0:20): `/crm/contacts`. Point out opted-in and opted-out contacts. "Only opted-in contacts can be sent to."
3. **Schedule a reminder** (0:50): `/crm/reminders` and the new reminder form. Pick an opted-in contact, write a message, choose a time at least a day ahead. For a demo, never schedule a message to a real number.
4. **Consent block** (1:20): try the opted-out contact (Mei Tanaka). Show it is refused.
5. **Dashboard** (1:40): `/crm/dashboard`, upcoming and history.
6. **Call the receptionist** (2:00): call +1 802 444 8729 on speaker, ask "What services do you offer?", then say goodbye. Switch to the Activity tab and show the call row with its summary, sentiment and priority.
7. **Close** (2:45): "Thank you. The poster has the QR code and our contact times."

Do not touch the Australian number in Twilio, and do not show it.

## After recording

- Watch each recording once, start to finish, before uploading.
- Upload to the Teams channel and to Moodle, and keep a copy on disk.
- Tick PROJ-497 only when all three are uploaded and the local backup exists.
