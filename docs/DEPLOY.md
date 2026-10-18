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

Where this host sits against the client's on-premise brief: see [DATA_SOVEREIGNTY.md](DATA_SOVEREIGNTY.md). Render is a demo host; the edge deployment is the product target.

Free-plan limits (Render's):
- The service **sleeps after about 15 minutes idle**; the first request after that takes about a minute. Open it a few minutes before presenting.
- There is **no persistent disk**, so data is wiped on every restart or sleep. `SEED_DEMO=true` reloads the demo account, 6 contacts, 5 reminders and analytics on each boot, so the demo is always there. Anything created live is lost on the next sleep.
- The reminder scheduler only runs while the service is awake.
- The 750 free instance-hours a month are shared across every service in your Render workspace, including your other project.

Why `DEMO_PASSWORD` matters: a logged-in user can call `POST /delivery/send`, which sends SMS and email through our Twilio account. On a public URL, never leave the default demo password live. The start script refuses to seed unless `DEMO_PASSWORD` is set.

### Keeping contacts and reminders across restarts (free)

Render's free plan has no disk, so `/data` is empty after every restart or sleep. `deploy/persist.py`
saves the whole data folder (accounts, contacts, reminders, templates, activity, the escalation log) to
any S3-compatible bucket and restores it on boot. It saves every 60 seconds when something changed, and
once more when Render stops the service. Nothing happens until all four `PERSIST_S3_*` settings exist.

Backblaze B2 gives 10 GB free (Cloudflare R2 works the same way):

1. Sign up at backblaze.com, then **Buckets, Create a Bucket**. Name it, set **Private**, leave encryption on.
2. Open the bucket and copy its **Endpoint** (like `s3.us-west-004.backblazeb2.com`).
3. **Application Keys, Add a New Application Key**. Restrict it to that bucket, allow read and write.
   Copy the **keyID** and the **applicationKey** (shown once).
4. In Render, **Environment**, add:
   - `PERSIST_S3_ENDPOINT` = `https://` + the endpoint from step 2
   - `PERSIST_S3_BUCKET` = the bucket name
   - `PERSIST_S3_KEY_ID` = the keyID
   - `PERSIST_S3_SECRET` = the applicationKey
   - `PERSIST_S3_REGION` = the region in the endpoint, e.g. `us-west-004`
   - `ESCALATION_LOG` = `/data/escalations.jsonl` (so escalations are saved too)
5. Save. The deploy log shows `persist: restored saved data` on later boots, and `persist: saved N bytes`
   within a minute of any change.

Limits to know: the bucket holds personal data (names, numbers), so keep it private and use a key limited to
that one bucket; a change made in the last minute before a crash can be lost; one service only (two
instances would overwrite each other's copy).

### Turning email on (PROJ-481)

1. Make a project Gmail account, turn on 2-step verification, then create an **App password** (Google Account → Security → App passwords). Use that 16-character password, never the normal one.
2. Locally: `./scripts/set_gmail_smtp.sh` writes the `SMTP_*` values into `.env` without the password appearing on screen.
3. Prove it from your machine: `python scripts/email_smoke.py --to <your address> --reminder`. It sends one direct email, then schedules a real reminder one minute out (in a throwaway store) and runs the reminder bridge until it is sent. Both should print `PASS`. Screenshot the output and the two received emails.
4. **Render's free plan blocks outgoing SMTP** (ports 25, 465, 587, since September 2025), so Gmail SMTP works locally but every email from Render fails. On Render, send through Brevo's HTTPS API instead (free, 300 emails a day):
   1. Create a free account at brevo.com.
   2. **Senders, domains & dedicated IPs** → **Senders** → add the address in `SMTP_FROM_EMAIL` and click the link Brevo emails to it.
   3. **SMTP & API** → **API keys** → generate a key.
   4. On Render, **Environment** → add `BREVO_API_KEY` with that key (keep `SMTP_FROM_EMAIL` as the verified address). Save; Render redeploys. Booking confirmations, reminders and password resets then go through Brevo.
5. On Render without Brevo (paid plans allow SMTP): **Environment** tab → set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USERNAME` and `SMTP_FROM_EMAIL` to the Gmail address, `SMTP_PASSWORD` to the app password, and `APP_BASE_URL` to the `https://<name>.onrender.com` address (reset links use it). Save; Render redeploys.
6. Password reset on the live site: the demo login (`poster.demo@example.com`) is not a real inbox, so first register an organisation at `/register` with an email you can read. Then open `/forgot-password`, enter that address and follow the link in the email. Only accounts registered with an email can reset; username-only accounts have nowhere to send it.
7. A reminder on the live site only sends **while the service is awake** (free plan). To film one arriving on time, schedule an email reminder a few minutes out and keep a tab open on the site until it arrives.

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
