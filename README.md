<p align="center">
  <img src="assets/nanoclaw-logo.png" alt="NanoClaw" width="400">
</p>

<p align="center">
  An AI assistant that runs agents securely in their own containers. Lightweight, built to be easily understood and completely customized for your needs.
</p>

<p align="center">
  <a href="https://nanoclaw.dev">nanoclaw.dev</a>&nbsp; • &nbsp;
  <a href="https://docs.nanoclaw.dev">docs</a>&nbsp; • &nbsp;
  <a href="README_zh.md">中文</a>&nbsp; • &nbsp;
  <a href="README_ja.md">日本語</a>&nbsp; • &nbsp;
  <a href="https://discord.gg/VDdww8qS42"><img src="https://img.shields.io/discord/1470188214710046894?label=Discord&logo=discord&v=2" alt="Discord" valign="middle"></a>&nbsp; • &nbsp;
  <a href="repo-tokens"><img src="repo-tokens/badge.svg" alt="34.9k tokens, 17% of context window" valign="middle"></a>
</p>

---

> **🔥 New Version Preview: Chat SDK + Approval Dialogs**
>
> A new version of NanoClaw is available for preview, featuring Vercel Chat SDK integration (15 messaging platforms from one codebase) and one-tap approval dialogs for sensitive agent actions. [Read the announcement →](https://venturebeat.com/orchestration/should-my-enterprise-ai-agent-do-that-nanoclaw-and-vercel-launch-easier-agentic-policy-setting-and-approval-dialogs-across-15-messaging-apps)
>
> <details>
> <summary>Try the preview</summary>
>
> ```bash
> gh repo fork qwibitai/nanoclaw --clone && cd nanoclaw
> git checkout v2
> claude
> ```
> Then run `/setup`. Feedback welcome on [Discord](https://discord.gg/VDdww8qS42). Expect breaking changes before merge to main.
>
> </details>

## Why I Built NanoClaw

[OpenClaw](https://github.com/openclaw/openclaw) is an impressive project, but I wouldn't have been able to sleep if I had given complex software I didn't understand full access to my life. OpenClaw has nearly half a million lines of code, 53 config files, and 70+ dependencies. Its security is at the application level (allowlists, pairing codes) rather than true OS-level isolation. Everything runs in one Node process with shared memory.

NanoClaw provides that same core functionality, but in a codebase small enough to understand: one process and a handful of files. Claude agents run in their own Linux containers with filesystem isolation, not merely behind permission checks.

## Quick Start

```bash
gh repo fork qwibitai/nanoclaw --clone
cd nanoclaw
claude
```

<details>
<summary>Without GitHub CLI</summary>

1. Fork [qwibitai/nanoclaw](https://github.com/qwibitai/nanoclaw) on GitHub (click the Fork button)
2. `git clone https://github.com/<your-username>/nanoclaw.git`
3. `cd nanoclaw`
4. `claude`

</details>

Then run `/setup`. Claude Code handles everything: dependencies, authentication, container setup and service configuration.

> **Note:** Commands prefixed with `/` (like `/setup`, `/add-whatsapp`) are [Claude Code skills](https://code.claude.com/docs/en/skills). Type them inside the `claude` CLI prompt, not in your regular terminal. If you don't have Claude Code installed, get it at [claude.com/product/claude-code](https://claude.com/product/claude-code).

## Philosophy

**Small enough to understand.** One process, a few source files and no microservices. If you want to understand the full NanoClaw codebase, just ask Claude Code to walk you through it.

**Secure by isolation.** Agents run in Linux containers (Apple Container on macOS, or Docker) and they can only see what's explicitly mounted. Bash access is safe because commands run inside the container, not on your host.

**Built for the individual user.** NanoClaw isn't a monolithic framework; it's software that fits each user's exact needs. Instead of becoming bloatware, NanoClaw is designed to be bespoke. You make your own fork and have Claude Code modify it to match your needs.

**Customization = code changes.** No configuration sprawl. Want different behavior? Modify the code. The codebase is small enough that it's safe to make changes.

**AI-native.**
- No installation wizard; Claude Code guides setup.
- No monitoring dashboard; ask Claude what's happening.
- No debugging tools; describe the problem and Claude fixes it.

**Skills over features.** Instead of adding features (e.g. support for Telegram) to the codebase, contributors submit [claude code skills](https://code.claude.com/docs/en/skills) like `/add-telegram` that transform your fork. You end up with clean code that does exactly what you need.

**Best harness, best model.** NanoClaw runs on the Claude Agent SDK, which means you're running Claude Code directly. Claude Code is highly capable and its coding and problem-solving capabilities allow it to modify and expand NanoClaw and tailor it to each user.

## What It Supports

- **Multi-channel messaging** - Talk to your assistant from WhatsApp, Telegram, Discord, Slack, or Gmail. Add channels with skills like `/add-whatsapp` or `/add-telegram`. Run one or many at the same time.
- **Isolated group context** - Each group has its own `CLAUDE.md` memory, isolated filesystem, and runs in its own container sandbox with only that filesystem mounted to it.
- **Main channel** - Your private channel (self-chat) for admin control; every group is completely isolated
- **Scheduled tasks** - Recurring jobs that run Claude and can message you back
- **Web access** - Search and fetch content from the Web
- **Container isolation** - Agents are sandboxed in Docker (macOS/Linux), [Docker Sandboxes](docs/docker-sandboxes.md) (micro VM isolation), or Apple Container (macOS)
- **Credential security** - Agents never hold raw API keys. Outbound requests route through [OneCLI's Agent Vault](https://github.com/onecli/onecli), which injects credentials at request time and enforces per-agent policies and rate limits.
- **Agent Swarms** - Spin up teams of specialized agents that collaborate on complex tasks
- **Optional integrations** - Add Gmail (`/add-gmail`) and more via skills

## Usage

Talk to your assistant with the trigger word (default: `@Andy`):

```
@Andy send an overview of the sales pipeline every weekday morning at 9am (has access to my Obsidian vault folder)
@Andy review the git history for the past week each Friday and update the README if there's drift
@Andy every Monday at 8am, compile news on AI developments from Hacker News and TechCrunch and message me a briefing
```

From the main channel (your self-chat), you can manage groups and tasks:
```
@Andy list all scheduled tasks across groups
@Andy pause the Monday briefing task
@Andy join the Family Chat group
```

## Customizing

NanoClaw doesn't use configuration files. To make changes, just tell Claude Code what you want:

- "Change the trigger word to @Bob"
- "Remember in the future to make responses shorter and more direct"
- "Add a custom greeting when I say good morning"
- "Store conversation summaries weekly"

Or run `/customize` for guided changes.

The codebase is small enough that Claude can safely modify it.

## Contributing

**Don't add features. Add skills.**

If you want to add Telegram support, don't create a PR that adds Telegram to the core codebase. Instead, fork NanoClaw, make the code changes on a branch, and open a PR. We'll create a `skill/telegram` branch from your PR that other users can merge into their fork.

Users then run `/add-telegram` on their fork and get clean code that does exactly what they need, not a bloated system trying to support every use case.

### RFS (Request for Skills)

Skills we'd like to see:

**Communication Channels**
- `/add-signal` - Add Signal as a channel

### Windows Users

Use `python` instead of `python3`:

```cmd
set ANTHROPIC_API_KEY=your-key-here
python main.py
```

### Running with Docker (NanoClaw)

```cmd
docker-compose up
```

The agent will be available at http://localhost:8080

---

## Requirements

- macOS, Linux, or Windows (via WSL2)
- Node.js 20+
- [Claude Code](https://claude.ai/download)
- [Apple Container](https://github.com/apple/container) (macOS) or [Docker](https://docker.com/products/docker-desktop) (macOS/Linux)

## Architecture

```
Channels --> SQLite --> Polling loop --> Container (Claude Agent SDK) --> Response
```

Single Node.js process. Channels are added via skills and self-register at startup — the orchestrator connects whichever ones have credentials present. Agents execute in isolated Linux containers with filesystem isolation. Only mounted directories are accessible. Per-group message queue with concurrency control. IPC via filesystem.

For the full architecture details, see the [documentation site](https://docs.nanoclaw.dev/concepts/architecture).

Key files:
- `src/index.ts` - Orchestrator: state, message loop, agent invocation
- `src/channels/registry.ts` - Channel registry (self-registration at startup)
- `src/ipc.ts` - IPC watcher and task processing
- `src/router.ts` - Message formatting and outbound routing
- `src/group-queue.ts` - Per-group queue with global concurrency limit
- `src/container-runner.ts` - Spawns streaming agent containers
- `src/task-scheduler.ts` - Runs scheduled tasks
- `src/db.ts` - SQLite operations (messages, groups, sessions, state)
- `groups/*/CLAUDE.md` - Per-group memory

## FAQ

**Why Docker?**

Docker provides cross-platform support (macOS, Linux and even Windows via WSL2) and a mature ecosystem. On macOS, you can optionally switch to Apple Container via `/convert-to-apple-container` for a lighter-weight native runtime. For additional isolation, [Docker Sandboxes](docs/docker-sandboxes.md) run each container inside a micro VM.

**Can I run this on Linux or Windows?**

Yes. Docker is the default runtime and works on macOS, Linux, and Windows (via WSL2). Just run `/setup`.

**Is this secure?**

Agents run in containers, not behind application-level permission checks. They can only access explicitly mounted directories. Credentials never enter the container — outbound API requests route through [OneCLI's Agent Vault](https://github.com/onecli/onecli), which injects authentication at the proxy level and supports rate limits and access policies. You should still review what you're running, but the codebase is small enough that you actually can. See the [security documentation](https://docs.nanoclaw.dev/concepts/security) for the full security model.

**Why no configuration files?**

We don't want configuration sprawl. Every user should customize NanoClaw so that the code does exactly what they want, rather than configuring a generic system. If you prefer having config files, you can tell Claude to add them.

**Can I use third-party or open-source models?**

Yes. NanoClaw supports any Claude API-compatible model endpoint. Set these environment variables in your `.env` file:

```bash
ANTHROPIC_BASE_URL=https://your-api-endpoint.com
ANTHROPIC_AUTH_TOKEN=your-token-here
```

This allows you to use:
- Local models via [Ollama](https://ollama.ai) with an API proxy
- Open-source models hosted on [Together AI](https://together.ai), [Fireworks](https://fireworks.ai), etc.
- Custom model deployments with Anthropic-compatible APIs

Note: The model must support the Anthropic API format for best compatibility.

**How do I debug issues?**

Ask Claude Code. "Why isn't the scheduler running?" "What's in the recent logs?" "Why did this message not get a response?" That's the AI-native approach that underlies NanoClaw.

**Why isn't the setup working for me?**

If you have issues, during setup, Claude will try to dynamically fix them. If that doesn't work, run `claude`, then run `/debug`. If Claude finds an issue that is likely affecting other users, open a PR to modify the setup SKILL.md.

**What changes will be accepted into the codebase?**

Only security fixes, bug fixes, and clear improvements will be accepted to the base configuration. That's all.

Everything else (new capabilities, OS compatibility, hardware support, enhancements) should be contributed as skills.

This keeps the base system minimal and lets every user customize their installation without inheriting features they don't want.

## Community

Questions? Ideas? [Join the Discord](https://discord.gg/VDdww8qS42).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for breaking changes, or the [full release history](https://docs.nanoclaw.dev/changelog) on the documentation site.

## License

MIT
---

# Agent Factory — Setup Guide

## Prerequisites

- Python 3.9+
- pip
- Git
- Docker Desktop (optional, for containerised run)

## Installation

```bash
git clone https://github.com/ITECH3208andITECH3209feduni/itech3208-project-1-agent-factory.git
cd itech3208-project-1-agent-factory
./run.sh
```

`run.sh` is the canonical entry point (PROJ-380). On first run it creates
`.venv`, installs `requirements.txt`, and starts the interactive CLI. It
resolves its own directory before doing anything, so it works from any
working directory and always uses the checkout it lives in — no more
"which worktree am I actually running?" ambiguity.

If you prefer to manage the environment yourself:

```bash
pip install -r requirements.txt
./run.sh --no-venv          # or: python main.py
```

> **Windows:** run `./run.sh` from Git Bash. The repo's other scripts
> (`setup.sh`, the Husky hooks) already assume bash, so there is one
> launcher rather than a PowerShell copy that can drift out of sync.
> `python main.py` also still works.

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Then lock it down and check it:

```bash
chmod 600 .env
./scripts/secure-secrets.sh
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | — | Claude API key. Get one at [console.anthropic.com](https://console.anthropic.com) |
| `S2_API_KEY` | No | `""` | Semantic Scholar key — raises the quota to 100 requests / 5 min. [Register here](https://www.semanticscholar.org/product/api-key). `SEMANTIC_SCHOLAR_API_KEY` still works as an alias |
| `BOT_TOKEN` | For Telegram | `""` | Bot token from [@BotFather](https://t.me/BotFather) |
| `GOOGLE_CALENDAR_CREDENTIALS` | For Calendar | `""` | **Path** to the OAuth client secrets JSON — not the JSON itself |
| `CHROMADB_PATH` | No | `store/chromadb` | Vector store location |
| `JWT_SECRET` | Before exposing the API | `""` | Session signing secret, 32+ chars |
| `COMPOSE_PROFILES` | No | `""` | Which services start: `telegram`, `dapr`, `tunnel` |
| `CLOUDFLARE_TUNNEL_TOKEN` | For the tunnel | `""` | Cloudflare Zero Trust tunnel token |
| `DEPLOY_WEBHOOK_SECRET` | For auto-deploy | `""` | Shared secret for the GitHub push webhook |
| `MAX_RESULTS` | No | `10` | Max items per skill call |
| `REQUEST_TIMEOUT` | No | `15` | HTTP timeout in seconds |
| `MAX_RETRIES` | No | `3` | Retry attempts on network failure |

Check what is and isn't configured at any time:

```bash
python -c "from config.settings import validate_env; print(*validate_env(), sep='\n')"
```

> **`.env` wins over your shell.** `config/settings.py` loads it with
> `override=True`, so an exported variable will *not* beat the file. Edit
> `.env`, not your shell profile.

> `GOOGLE_CALENDAR_CREDENTIALS` is a **path** on purpose. Putting the
> credential body in an environment variable leaks it into `docker inspect`,
> crash reports, and `/proc/<pid>/environ`.

See [docs/SECRETS.md](docs/SECRETS.md) for rotation procedures.

## Running the Agent

All of these work from any directory — `run.sh` cd's to the project root itself.

**Interactive mode:**
```bash
./run.sh
```

**Single query mode:**
```bash
./run.sh -q "Find papers on transformer architecture"
./run.sh -q "Best wireless earbuds under $50"
```

**Save output to file:**
```bash
./run.sh -q "RAG architecture" --save
```

**Show query history:**
```bash
./run.sh --history
```

**API server:**
```bash
./run.sh serve                 # http://0.0.0.0:8000
HOST=127.0.0.1 PORT=9000 ./run.sh serve
```

**Smoke tests:**
```bash
./run.sh test
```

| Subcommand | Runs |
|-----------|------|
| *(none)* | `main.py` — interactive CLI, plus all its flags |
| `serve` | `uvicorn app.web.main:app` |
| `test` | the smoke-test scripts |
| `--no-venv` | skips venv creation, uses whatever Python is active |

Running `python main.py` directly still works, but only from the project
root and only with your environment already set up.

### VS Code

`.vscode/launch.json` is committed (PROJ-380) with four configs: interactive
CLI, single query, API server, and the rate limiter tests. Each pins `cwd`
and `PYTHONPATH` to the workspace folder, so F5 debugs the same code
`./run.sh` executes.

## Running with Docker Compose

The stack is profile-based. The core is `agent` + `chromadb`; everything else
is opt-in.

```bash
docker compose up -d                     # agent + ChromaDB
docker compose --profile telegram up -d  # + Telegram bot
docker compose --profile dapr up -d      # + Dapr sidecars and placement
docker compose --profile tunnel up -d    # + Cloudflare Tunnel

docker compose ps
docker compose logs -f agent
docker compose down
```

Or set `COMPOSE_PROFILES=telegram,tunnel` in `.env` and use
`./scripts/macos/agentctl.sh start`, which reads it.

| Service | Profile | Port | Notes |
|---|---|---|---|
| `agent` | default | `8000` | FastAPI. `/query`, `/skills`, `/health`, `/ui` |
| `chromadb` | default | — | Not published to the host: only the agent needs it, and Chroma ships with no auth |
| `telegram-bot` | `telegram` | — | Reaches the API at `agent:8000` over the compose network |
| `agent-dapr`, `telegram-dapr` | `dapr` | — | Sidecars sharing their app's network namespace |
| `dapr-placement` | `dapr` | `50006` | Actor placement |
| `cloudflared` | `tunnel` | — | Public HTTPS ingress |

Once up: <http://localhost:8000/ui> for the web UI,
<http://localhost:8000/docs> for the OpenAPI explorer.

`./outputs` is bind-mounted, so saved results land on the host. ChromaDB and
`/data` use **named volumes**, not bind mounts — Chroma's SQLite backing store
misbehaves across the macOS virtiofs boundary.

> Give Docker Desktop **at least 4 GB** (Settings → Resources). The image
> builds `lxml` from source and installs Chromium; it OOMs on less.

---

## Sprint 3 setup

### Telegram bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`, follow the prompts
2. Copy the token into `.env`:

```bash
BOT_TOKEN=123456789:AAE...
COMPOSE_PROFILES=telegram
```

3. Restart: `docker compose --profile telegram up -d`

For the bot to receive messages from outside your network it needs a public
HTTPS webhook — see [Exposing it publicly](#exposing-it-publicly) below, then:

```bash
source .env
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://${PUBLIC_HOSTNAME}/telegram/webhook"
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python -m json.tool
```

A climbing `pending_update_count` with a non-empty `last_error_message` means
Telegram is reaching Cloudflare but not your container.

> **Status:** the Compose service and webhook plumbing exist; the bot module
> `app/channels/telegram_bot.py` is not implemented yet.

### ChromaDB

Runs as a container with a persistent named volume — no host install needed.

```bash
docker compose up -d chromadb
docker compose logs chromadb
```

Configure with `CHROMADB_PATH` (default `store/chromadb`, set to `/data/chromadb`
inside the container) and `CHROMADB_COLLECTION` (default `agent_factory`).

> **Status:** the service runs and the app is configured to reach it, but the
> embedding and recall paths are not implemented. Memory currently lives in
> `outputs/memory.json` via `agent/memory.py`.

### Dapr

You do **not** need the Dapr CLI or `dapr init` — the sidecars run as
containers under the `dapr` profile.

```bash
docker compose --profile dapr up -d
docker compose logs agent-dapr
```

Components are in `config-examples/dapr/components/`: `statestore` and
`pubsub`, both `in-memory` so the local stack needs no Redis. State is lost on
sidecar restart, which is fine because ChromaDB owns anything durable. For
messaging that survives restarts, switch both to `.redis` and add a `redis`
service.

If you want the CLI for `dapr dashboard`:

```bash
brew install dapr/tap/dapr-cli     # macOS
```

> **Status:** sidecars are configured and start, but no application code calls
> Dapr yet.

### Google Calendar OAuth

1. [Google Cloud Console](https://console.cloud.google.com/) → create or select a project
2. **APIs & Services → Library** → enable **Google Calendar API**
3. **OAuth consent screen** → External → add your Google account as a test user
4. **Credentials → Create credentials → OAuth client ID → Desktop app**
5. Download the JSON, store it **outside the repo** (or somewhere gitignored)
6. Point `.env` at it:

```bash
GOOGLE_CALENDAR_CREDENTIALS=/Users/you/.config/agent-factory/gcal_client.json
GOOGLE_CALENDAR_TOKEN_PATH=store/google_calendar_token.json
```

The first authorised call opens a browser consent flow and caches a token at
`GOOGLE_CALENDAR_TOKEN_PATH`. Delete that file to force re-consent (needed
after rotating the client secret).

> **Status:** config is wired through and validated, but the OAuth flow and
> calendar tools are not implemented yet — nothing reads these values.

### Deployment

The client confirmed on 29 Jul 2026 that the app runs **locally on a Mac**
rather than on AWS/Azure, so the Sprint 3 plan's cloud-deploy step was
superseded. Full guide: **[docs/DEPLOYMENT-MAC.md](docs/DEPLOYMENT-MAC.md)**.

```bash
./scripts/macos/install-service.sh        # launchd: start at login, restart on crash
./scripts/macos/agentctl.sh status
./scripts/deploy.sh                        # pull, rebuild, restart, verify health
```

#### Exposing it publicly

A tunnel rather than port-forwarding, because Telegram webhooks need public
HTTPS with a valid certificate and a home connection has a dynamic IP and
often CGNAT.

1. Cloudflare Zero Trust → **Networks → Tunnels → Create a tunnel** → Cloudflared
2. Add a public hostname routing to `HTTP` → **`agent:8000`** (the container
   name on the compose network — *not* `localhost`)
3. Put the token and hostname in `.env`, add `tunnel` to `COMPOSE_PROFILES`
4. `curl https://your-host/health`

---

## Skills and MCP

Skills are described by manifests in `skills/manifests/*.skill.json` and
served over HTTP:

```bash
curl localhost:8000/skills              # all manifests
curl localhost:8000/skills/literature   # one
curl localhost:8000/skills/amazon/tools # tool definitions
```

Each skill also runs as a standalone MCP server:

```bash
python -m skills.mcp.literature_server
python -m skills.mcp.amazon_server
```

To use them from an MCP client such as Claude Desktop:

```json
{
  "mcpServers": {
    "literature": {
      "command": "python",
      "args": ["-m", "skills.mcp.literature_server"],
      "cwd": "/path/to/itech3208-project-1-agent-factory"
    }
  }
}
```

The manifest is the single source of truth — the registry endpoint, the UI
sidebar, and both MCP servers all read tool definitions from it, so they
cannot drift apart. Adding a skill is one new `skill.json`.

Architecture diagrams: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Example Queries

**Literature search:**
- `Find research papers on AI`
- `Research on CRISPR gene editing 2024`

**Amazon product research:**
- `Search laptop under $1000`
- `Best wireless earbuds under $50`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python3` not found | Use `python`, or set `AGENT_FACTORY_PYTHON`. On Windows a bare `python3` is often the Microsoft Store stub — it satisfies `command -v` but fails on execution |
| pip not working | Run `python -m pip install -r requirements.txt` |
| Playwright browser error | Run `playwright install chromium` |
| Permission error on pip | Run `pip install --user -r requirements.txt` |
| Docker build OOMs | Raise Docker Desktop memory to 4 GB+ (Settings → Resources) |
| `docker compose up` complains about a missing variable | `ANTHROPIC_API_KEY` is required. Others are optional and default to empty |
| Containers up but API unreachable | The healthcheck has a 20s `start_period`. Wait, then `curl localhost:8000/health` |
| `/query` returns 503 | Not a crash — `ANTHROPIC_API_KEY` is unset. `/health` lists what is missing |
| `/skills` shows an `errors` array | A manifest is malformed. `python scripts/test_manifests.py` names the problem |
| Tunnel returns 502 | The Cloudflare service target must be `agent:8000`, not `localhost:8000` |
| Telegram not delivering | Check `getWebhookInfo` — the URL must be HTTPS with a valid cert |
| A `.env` edit seems ignored | It shouldn't be: `override=True` means the file wins. Confirm you edited the `.env` at the project root |
| `ANTHROPIC_API_KEY not set` warning | Create a `.env` file with your key (see above) |

## PROJ-48 Validation

Cross-machine testing (PROJ-47) verified that the system runs successfully across macOS and Windows environments. All core features (Literature and Amazon skills) executed without errors, and no critical environment issues were identified.