# Running Agent Factory on the Mac mini

The Mac mini stays on, so the app, the reminder scheduler and the Twilio webhooks
run around the clock at one permanent URL. Everything here is free.

You need: Docker Desktop, a free Tailscale account, and this repo.

## 1. Keep the Mac mini awake

System Settings → Energy (or Battery):
- turn on **Prevent automatic sleeping when the display is off**
- turn on **Start up automatically after a power failure**

System Settings → Users & Groups → **Automatic login** → your user. (Docker Desktop
and the launcher below start at login.)

## 2. Docker Desktop

Install Docker Desktop. In its settings, turn on **Start Docker Desktop when you
sign in to your computer**. The app container uses `restart: unless-stopped`, so it
comes back by itself after a reboot.

## 3. Tailscale Funnel (the permanent URL)

1. `brew install --cask tailscale`, open it, and sign in with a free account.
2. In the Tailscale admin console (login.tailscale.com/admin):
   - **DNS** → turn on **HTTPS certificates** and note your tailnet name.
   - **Access controls** → Funnel must be allowed for your devices. The console
     offers an "Enable Funnel" prompt; accept it.
3. Check it works: `tailscale funnel status` should run without an error.

Your URL will look like `https://<mac-mini-name>.<tailnet>.ts.net` and never changes.

## 4. Get the code and your secrets onto the Mac mini

```bash
git clone https://github.com/ITECH3208andITECH3209feduni/itech3208-project-1-agent-factory.git
cd itech3208-project-1-agent-factory
```

Copy your `.env` over by AirDrop or `scp`. **Never commit it, and never paste it into
chat.** The `.env` needs at least `ANTHROPIC_API_KEY`, the three `TWILIO_*` values,
`AUTH_SECRET_KEY`, and the `SMTP_*` values if you want email.

## 5. Start it

```bash
./scripts/serve_up.sh
```

It builds the image, starts the app, publishes it with Funnel, and prints the
permanent URL and the three Twilio webhook URLs. Paste those into the Twilio console
**once** (your number → Configure). They never need changing.

Load demo data for the poster session (fictional contacts, reminders 8+ days out):

```bash
DEMO_PASSWORD='choose-a-new-password-here' python3 scripts/seed_demo.py
```

The demo login is `poster.demo@example.com` with the password you just chose. **Always
set `DEMO_PASSWORD`.** Without it the script uses the default written in the public
repo, and anyone who finds your Funnel URL could sign in and send texts and email
through your Twilio account.

## 6. Start automatically at login (optional)

```bash
cp launchd/com.agentfactory.serve.plist ~/Library/LaunchAgents/
# edit the two REPLACE_ME paths in the copy to your repo location, then:
launchctl load ~/Library/LaunchAgents/com.agentfactory.serve.plist
```

## Day to day

| Task | Command |
|---|---|
| Check it is healthy | `curl https://<your-url>/status` and `/status/scheduler` |
| Update to the latest code | `git pull && ./scripts/serve_up.sh` |
| Stop | `./scripts/serve_up.sh --down` |
| Logs | `docker compose -f docker-compose.web.yml logs -f` |

Data (accounts, contacts, reminders, call history) lives in the Docker volume
`agent_factory_data`, so rebuilding or updating keeps it. Back it up with
`docker run --rm -v <project>_agent_factory_data:/data -v "$PWD":/backup alpine tar czf /backup/af-data.tgz /data`.

## Safety notes

- Every route needs a login except health checks, the login pages, the marketing
  site and the Twilio webhooks (which verify Twilio's signature). Keep
  `TWILIO_VALIDATE_SIGNATURE=true`, which `serve_up.sh` sets whenever a Twilio token
  is present.
- Keep the Mac mini's macOS and Docker Desktop updated, since it is on the internet.
- The test suite never uses real Twilio or SMTP credentials (`tests/conftest.py`).
