# Deploying Agent Factory

Three ways to run it. **Always-on machine (Mac mini, free, permanent URL): see
`docs/MAC_MINI.md`.** Option A below is a free laptop run with a temporary URL;
Option B (Fly.io) is a paid cloud host.

## Option A: free local run + public tunnel (open source)

Needs Docker and `cloudflared` (`brew install cloudflared`).

```bash
./scripts/demo_up.sh            # uses ./.env; or pass a path to an env file
```

This builds the image, starts the web app and the reminder loops in one
container with all SQLite data on a Docker volume, opens a Cloudflare quick
tunnel, and prints the public URL plus the three Twilio webhook URLs. If
`TWILIO_AUTH_TOKEN` is set, signature validation is switched on. Check
`<url>/status` and `<url>/status/scheduler`. Stop with
`./scripts/demo_up.sh --down`.

Limits: it only runs while your machine is on, and the tunnel URL changes
each start, so re-paste the Twilio webhook URLs after a restart.

## Option A2: Render (free, no card needed if you already have an account)

`render.yaml` in the repo root defines the whole service. Steps:

1. Push the branch you want to deploy to GitHub.
2. Render dashboard -> **New** -> **Blueprint** -> pick this repo and branch. Render reads `render.yaml`.
3. Fill in the secrets it asks for (they are `sync: false`, never stored in git):
   `ANTHROPIC_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`,
   the `SMTP_*` values, and **`DEMO_PASSWORD`** (pick a new one; it becomes the demo login password).
   Set `APP_BASE_URL` to the `https://<name>.onrender.com` address Render shows after the first deploy.
4. Open `https://<name>.onrender.com/status`. It should return 200.
5. Sign in at `/login` with `poster.demo@example.com` and your `DEMO_PASSWORD`.
6. Point the Twilio webhooks at `https://<name>.onrender.com/twilio/...` (see section 4 below). The URL is permanent, so you paste them once.

Free-plan limits (Render's):
- The service **sleeps after about 15 minutes idle**; the first request after that takes about a minute. Open it a few minutes before presenting.
- There is **no persistent disk**, so data is wiped on every restart or sleep. `SEED_DEMO=true` reloads the demo account, 6 contacts, 5 reminders and analytics on each boot, so the demo is always there. Anything created live is lost on the next sleep.
- The reminder scheduler only runs while the service is awake.
- The 750 free instance-hours a month are shared across every service in your Render workspace, including your other project.

Why `DEMO_PASSWORD` matters: a logged-in user can call `POST /delivery/send`, which sends SMS and email through our Twilio account. On a public URL, never leave the default demo password live. The start script refuses to seed unless `DEMO_PASSWORD` is set.

## Option B: Fly.io

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
`GOOGLE_CALENDAR_*`, `RAPIDAPI_KEY`. The script now refuses to run if any of
`ANTHROPIC_API_KEY`, `AUTH_SECRET_KEY` or the three `TWILIO_*` values are
missing, because each one fails at the first real request rather than at deploy
time (`ALLOW_INCOMPLETE=1` overrides). Set `AUTH_SECRET_KEY` explicitly:
without it a key is generated on first boot and sessions are lost if the volume
is recreated.

Google Calendar needs the service-account JSON on the volume, e.g.
`fly ssh sftp shell` then upload to `/data/calendar-key.json` and set
`GOOGLE_CALENDAR_KEY_PATH=/data/calendar-key.json`.

Non-secret production settings live in `fly.toml` under `[env]`. **Update
`APP_BASE_URL` there** to whatever app name `fly launch` gave you — it is what
password-reset emails put in their links, and its default points at localhost.

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

All four webhook routes verify `X-Twilio-Signature` — `/twilio/sms`,
`/twilio/voice`, `/twilio/voice/reply` and `/twilio/status-callback`. (Until
PROJ-466 only `/twilio/sms` did, so a forged status callback could rewrite
delivery records and a forged `/twilio/voice` could spend Claude tokens.)
Verification fails closed: if `TWILIO_VALIDATE_SIGNATURE=true` but
`TWILIO_AUTH_TOKEN` is unset, every request is rejected rather than waved
through.

If every webhook starts returning 403, check in this order:

1. `TWILIO_AUTH_TOKEN` matches the token for *this* Twilio account
   (`fly secrets list` shows names and digests, not values).
2. The app is seeing `https://`, not `http://` — signature covers the exact
   URL, so losing `--proxy-headers` breaks all of them at once.
3. The console URL matches the route exactly, including any trailing path.

The status-callback route also accepts JSON for our own tooling. Twilio signs
form-encoded parameters only, so that JSON path cannot pass verification and
works only with validation off.

## 5. Monitoring (PROJ-468)

`GET /status/scheduler` returns 200 while the reminder loops have ticked in
the last three poll intervals (minimum 60 s) and 503 otherwise. `fly.toml`
already registers it as a Fly health check. For alerts, point a free
external monitor (UptimeRobot, Better Stack) at it.
