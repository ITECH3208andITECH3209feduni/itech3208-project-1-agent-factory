# Deploying Agent Factory (Fly.io)

Covers PROJ-465 (hosting), PROJ-466 (Twilio webhooks), PROJ-467 (secrets) and
PROJ-468 (scheduler monitoring). The repo side is ready; the steps below need
your own Fly and Twilio accounts.

## Shape

One Fly machine runs three processes from `deploy/start.sh`: the web app, the
reminders scheduler and the dashboard reminder bridge. They share one volume
mounted at `/data` that holds every SQLite file, because SQLite needs a single
writer. Do not scale beyond one machine.

## 1. Provision (PROJ-465)

```bash
fly auth login
fly launch --no-deploy --copy-config      # pick a unique app name when prompted
fly volumes create agent_factory_data --region syd --size 1
```

## 2. Secrets (PROJ-467)

Fill in a local `.env` (never commit it), then:

```bash
./scripts/fly_set_secrets.sh
```

Only these names are sent: `ANTHROPIC_API_KEY`, `AUTH_SECRET_KEY`,
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `SMTP_*`,
`GOOGLE_CALENDAR_*`. Set `AUTH_SECRET_KEY` explicitly: without it a key is
generated on first boot and sessions are lost if the volume is recreated.
Google Calendar needs the service-account JSON on the volume, e.g.
`fly ssh sftp shell` then upload to `/data/calendar-key.json` and set
`GOOGLE_CALENDAR_KEY_PATH=/data/calendar-key.json`.

## 3. Deploy and verify

```bash
fly deploy
curl https://<app>.fly.dev/status             # {"status":"ok","agent":"ready"}
curl https://<app>.fly.dev/status/scheduler   # 200 once the loops are ticking
```

## 4. Point Twilio at it (PROJ-466)

In the Twilio console, on the project's number, set:

| Event | URL | Method |
|---|---|---|
| Messaging: a message comes in | `https://<app>.fly.dev/twilio/sms` | POST |
| Voice: a call comes in | `https://<app>.fly.dev/twilio/voice` | POST |
| Status callback | `https://<app>.fly.dev/twilio/status-callback` | POST |

`TWILIO_VALIDATE_SIGNATURE=true` is set in `fly.toml`, and `deploy/start.sh`
passes `--proxy-headers` so the app sees the public `https://` URL Twilio
signed. Then stop ngrok, text the number, and restart the machine
(`fly machine restart`) to confirm replies still arrive.

Known gap: only `/twilio/sms` checks the signature today; the voice and
status-callback routes do not.

## 5. Monitoring (PROJ-468)

`GET /status/scheduler` returns 200 while the reminder loops have ticked in
the last three poll intervals (minimum 60 s) and 503 otherwise. `fly.toml`
already registers it as a Fly health check. For alerts, point a free
external monitor (UptimeRobot, Better Stack) at it.
