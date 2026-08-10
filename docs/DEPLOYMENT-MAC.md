# Local Mac Deployment

Running Agent Factory 24/7 on a Mac (PROJ-309..313).

Per the client decision of 29 Jul 2026, the app runs locally on Dilraj's Mac
rather than on AWS/Azure. This document covers making that survive crashes and
reboots, and making the Telegram webhook reachable from the internet.

---

## 1. Prerequisites

- macOS 13 or later
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — **set it to start at login**
  (Settings → General → *Start Docker Desktop when you sign in*). launchd will nudge it
  awake, but if it never starts the stack cannot run.
- A populated `.env` (`cp .env.example .env && chmod 600 .env`)

Give Docker Desktop at least **4 GB** of memory (Settings → Resources). The image
builds Chromium, which OOMs on less.

---

## 2. Install the service

```bash
./scripts/macos/install-service.sh
```

This renders `launchd/com.agentfactory.plist` into
`~/Library/LaunchAgents/com.agentfactory.plist`, validates it with `plutil`, and
loads it. The stack now starts at login and restarts if it crashes.

Choose which services run by setting `COMPOSE_PROFILES` in `.env`:

```bash
COMPOSE_PROFILES=telegram,tunnel     # agent + chromadb + bot + tunnel
```

Leave it empty for just the agent and ChromaDB.

### Day-to-day

```bash
./scripts/macos/agentctl.sh status        # containers, launchd, API health
./scripts/macos/agentctl.sh logs agent    # follow one service
./scripts/macos/agentctl.sh restart
tail -f logs/agentfactory.log             # launchd's own stdout

launchctl kickstart -k gui/$(id -u)/com.agentfactory   # force a restart
./scripts/macos/install-service.sh --uninstall         # remove the agent
```

### How the supervision works

launchd runs `agentctl.sh supervise`, which:

1. waits up to 180s for the Docker daemon (launching Docker Desktop if needed) —
   at login launchd starts us well before Docker is accepting connections
2. rebuilds images if they are stale
3. runs `docker compose up` in the **foreground**

Step 3 is the important one. With `up -d` the script would exit immediately and
`KeepAlive` would relaunch it in a loop forever. Running in the foreground gives
launchd a real process to supervise.

`KeepAlive` is set to `SuccessfulExit: false`, so a crash restarts the stack but a
deliberate `agentctl.sh stop` does not fight you. `ThrottleInterval` is 30s so
launchd does not burn through its restart budget while Docker is still booting.

---

## 3. Exposing it to the internet

Telegram webhooks require a **public HTTPS endpoint with a valid certificate**.
A home connection typically has a dynamic IP and often CGNAT, so port-forwarding
is unreliable even when the router cooperates. A tunnel dials outward instead,
which sidesteps both problems.

### Cloudflare Tunnel (recommended)

Stable hostname, free, survives IP changes and reboots.

1. Cloudflare Zero Trust dashboard → **Networks → Tunnels → Create a tunnel**
2. Choose **Cloudflared**, name it (e.g. `agent-factory`)
3. Copy the token out of the Docker command it shows you
4. Add a **public hostname**:
   - Subdomain/domain: e.g. `agent.example.com`
   - Service: `HTTP` → `agent:8000`
     (the container name on the compose network — *not* `localhost`)
5. Put both values in `.env`:

```bash
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiO...
PUBLIC_HOSTNAME=agent.example.com
COMPOSE_PROFILES=telegram,tunnel
```

6. Restart: `./scripts/macos/agentctl.sh restart`
7. Verify: `curl https://agent.example.com/health`

### ngrok (quick testing only)

```bash
brew install ngrok
ngrok http 8000
```

The free tier issues a **new hostname every restart**, which means re-registering
the Telegram webhook every time. Fine for a demo, not for the 24/7 deployment.

---

## 4. Registering the Telegram webhook

Once the tunnel is up:

```bash
source .env
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://${PUBLIC_HOSTNAME}/telegram/webhook"
```

Confirm it took:

```bash
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python -m json.tool
```

`pending_update_count` climbing with a non-empty `last_error_message` means
Telegram is reaching Cloudflare but not your container — check
`./scripts/macos/agentctl.sh logs agent`.

To go back to polling: `curl "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook"`

---

## 5. Deploying updates

### By hand

```bash
./scripts/deploy.sh --check     # is there anything to deploy?
./scripts/deploy.sh             # pull, rebuild, restart, verify health
./scripts/deploy.sh --force     # redeploy the same commit
```

The script fast-forwards only — it will not create a merge commit on the
deployment box — and refuses to run with uncommitted changes in the working
tree, rather than silently discarding them. If the image build fails it resets
the checkout back to the previous commit, so the box is never left on code with
no matching image. A deploy that finishes but leaves `/health` unreachable is
reported as `UNHEALTHY` and exits non-zero.

Every run appends one line to `logs/deploy.log`:

```
2026-08-10 13:22:04 | SUCCESS   | branch=master | from=fbf3bec | to=27d0b85 | 94s | feat: ...
2026-08-10 14:01:11 | FAILED    | branch=master | from=27d0b85 | to=unknown | 3s  | git fetch failed
```

`--check` is a read-only probe and deliberately does not require Docker, so it
stays fast when the daemon is down.

### On push (optional)

`scripts/deploy_webhook.py` is a stdlib-only listener that runs `deploy.sh`
when a push lands on the deploy branch.

1. Generate a secret and put it in `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# DEPLOY_WEBHOOK_SECRET=...
```

2. Install it as a launchd agent:

```bash
sed -e "s|{{PROJECT_ROOT}}|$PWD|g" -e "s|{{HOME}}|$HOME|g" \
    launchd/com.agentfactory.webhook.plist \
    > ~/Library/LaunchAgents/com.agentfactory.webhook.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.agentfactory.webhook.plist
```

3. Add a public hostname in Cloudflare pointing at `http://host.docker.internal:9000`,
   or route `/deploy-hook` through the existing tunnel.

4. GitHub repo → Settings → Webhooks → Add webhook:
   - Payload URL: `https://<your-host>/deploy-hook`
   - Content type: `application/json`
   - Secret: the value from step 1
   - Events: **Just the push event**

The endpoint verifies GitHub's `X-Hub-Signature-256` with `hmac.compare_digest`,
ignores pushes to other branches, and returns `202` immediately — GitHub times
deliveries out after 10s and a deploy takes minutes. Concurrent deploys are
locked out so two pushes cannot fight over the same checkout.

**It refuses every request when `DEPLOY_WEBHOOK_SECRET` is empty** — this
endpoint executes code on the host, so failing closed is the only safe default.

```bash
tail -f logs/deploy-webhook.log
curl localhost:9000/health
```

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `agentctl status` says Docker not running | Desktop not started at login | Enable it in Docker Desktop settings |
| launchd restarts every 30s | `supervise` exiting immediately | `tail -f logs/agentfactory.error.log`; usually a missing `.env` var |
| Service does not start after reboot | Agent not loaded | `launchctl list \| grep agentfactory`, re-run the installer |
| Tunnel 502s | Wrong service target | Must be `agent:8000`, not `localhost:8000` |
| Telegram not delivering | Webhook not registered, or non-HTTPS URL | Check `getWebhookInfo` |
| Build OOMs | Docker memory too low | Raise to 4 GB+ in Settings → Resources |
| Containers up, API unreachable | Still starting | `HEALTHCHECK` has a 20s `start_period`; wait, then check `/health` |

### A note on sleep

A sleeping Mac serves nothing. For genuine 24/7:

```bash
sudo pmset -a sleep 0 disablesleep 1     # revert with disablesleep 0
```

Or System Settings → Displays → Advanced → *Prevent automatic sleeping when the
display is off*. `caffeinate -s` also works but only lasts for the session.

---

## Why launchd rather than pm2

The ticket allowed either. launchd wins here because the workload is
`docker compose`, not a Node process — pm2 would supervise a shell wrapper
around Docker, adding a layer without adding supervision. launchd is also
already in the repo (`launchd/com.nanoclaw.plist`) and needs no extra runtime
installed on the Mac.
