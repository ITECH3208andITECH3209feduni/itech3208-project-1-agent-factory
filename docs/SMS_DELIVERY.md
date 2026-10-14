# SMS delivery: status, limitation and evidence (PROJ-482)

Written for the client handover. Short version: **the SMS code path works and is tested; texts to US mobile numbers from our US Twilio number are blocked by US carrier rules until the number is registered for A2P 10DLC.** That is a Twilio and carrier registration step, not a code change. For an Australian business, the production setup would not hit this rule at all (see "Recommendation").

## What works

| Piece | Where | Evidence |
|---|---|---|
| Sending a reminder by SMS | `agent/delivery/sms_channel.py` via `WebReminderBridge` | `tests/test_delivery.py`, `tests/test_web_reminder_bridge.py` |
| Consent checked before every send; opted-out contacts are blocked, not sent | `app/web/consent.py`, `dispatch_check()` | `tests/test_web_reminder_bridge.py` |
| Retry with backoff; permanent errors (bad number, opted out, unverified on trial) are not retried | `agent/delivery/base.py`, `_NON_RETRIABLE_CODES` | `tests/test_delivery.py` |
| Delivery status reported back by Twilio and recorded | `/twilio/status-callback` (signature-checked) | `tests/test_delivery_status.py` |
| Each SMS asks Twilio for those status reports when the app runs on a public https URL | `_status_callback_url()` in `sms_channel.py` | `tests/test_delivery.py` |
| Voice reminders and the AI receptionist on the same number | `agent/delivery/voice_channel.py`, `app/web_ui/twilio_routes.py` | A real call reached the live app (HANDOFF.md) |

Before PROJ-482, SMS sends did not request status callbacks, so the app never learned whether a text was delivered. It now does, so every attempt ends with a recorded `delivered` or `undelivered` plus Twilio's error code.

## The limitation

US carriers require every business sending application-to-person (A2P) texts from an ordinary 10-digit US number to register a **brand** and a **campaign** ("A2P 10DLC"). Unregistered traffic is blocked by the carriers and Twilio reports error **30034**. Registration is done in the Twilio Console under Messaging → Regulatory Compliance. It has one-off and monthly fees and a vetting wait, so check the current costs on the number's page before starting.

Trial accounts have a second limit: they can only text **verified** numbers (error **21608** otherwise) and they add a trial prefix to every message.

Neither is something the app can work around, and it should not try to.

## How to capture the evidence

Run from a machine whose `.env` has the Twilio values (or the Render shell):

```bash
python scripts/sms_status.py                      # read-only: account type, number, A2P state, last 20 messages
python scripts/sms_status.py --send +1XXXXXXXXXX  # one test SMS to a verified number, then its final status
```

The script refuses to send to the Australian test number from the earlier incident (HANDOFF.md section 6). Its output contains no secrets, so paste it into the handover pack. Either outcome closes the ticket:

- **`delivered`**: SMS works end to end. Screenshot the phone and the output.
- **`undelivered 30034`** (or a 21608 rejection): this document plus that output is the evidence. The status-callback record is also returned by `GET /delivery/history`.

## Recommendation for the client

The client is an Australian business texting Australian customers. In production that means an **Australian sender** (an Australian mobile number or a registered alphanumeric sender ID), where A2P 10DLC does not apply. The code does not change: set `TWILIO_FROM_NUMBER` to the new sender. Email reminders (PROJ-481) and voice reminders work today without any registration and can carry the demo.
