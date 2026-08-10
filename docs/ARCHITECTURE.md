# Agent Factory — Architecture (Sprint 3)

Component diagram and data flows as of Sprint 3 (PROJ-383).

Diagrams are Mermaid, which GitHub renders natively — no image files to
regenerate and fall out of date whenever the architecture changes.

---

## 1. System overview

```mermaid
graph TB
    subgraph users["Users"]
        TG["Telegram user"]
        WEB["Browser"]
        CLI["Terminal"]
    end

    subgraph mac["Dilraj's Mac — Docker Compose"]
        subgraph edge["Ingress"]
            CF["cloudflared<br/><i>tunnel profile</i>"]
        end

        BOT["telegram-bot<br/><i>telegram profile</i>"]
        API["agent<br/>FastAPI + uvicorn :8000"]

        subgraph dapr["Dapr — dapr profile"]
            DS1["daprd sidecar<br/>app-id: agent"]
            DS2["daprd sidecar<br/>app-id: telegram-bot"]
            DPL["placement :50006"]
        end

        subgraph agentcore["Agent core"]
            ORCH["Orchestrator<br/>routing + summarisation"]
            LIT["LiteratureSkill"]
            AMZ["AmazonSkill"]
        end

        CHROMA[("ChromaDB<br/>persistent volume")]
        OUT[("outputs/<br/>saved results")]
    end

    subgraph external["External services"]
        CLAUDE["Claude API"]
        ARXIV["arXiv"]
        S2["Semantic Scholar"]
        PUBMED["PubMed"]
        AMZN["Amazon<br/><i>scraped</i>"]
        GCAL["Google Calendar"]
        TGAPI["Telegram Bot API"]
    end

    TG <--> TGAPI
    TGAPI -->|"webhook<br/>HTTPS"| CF
    WEB -->|"HTTPS"| CF
    CF --> API
    CLI -->|"./run.sh"| ORCH

    BOT -->|"HTTP<br/>agent:8000"| API
    API --> ORCH
    ORCH --> LIT
    ORCH --> AMZ

    DS1 -.->|"127.0.0.1:8000"| API
    DS2 -.-> BOT
    DS1 <-.->|"pub/sub, state"| DPL
    DS2 <-.-> DPL

    ORCH <-->|"embeddings<br/>+ recall"| CHROMA
    ORCH --> OUT

    ORCH -->|"routing,<br/>summarisation"| CLAUDE
    LIT --> ARXIV
    LIT -->|"token bucket<br/>100 req/5 min"| S2
    LIT --> PUBMED
    AMZ -->|"Playwright<br/>Chromium"| AMZN
    API <-->|"OAuth"| GCAL

    classDef ext fill:#2d3748,stroke:#4a5568,color:#e2e8f0
    classDef store fill:#1a4731,stroke:#2f855a,color:#e2e8f0
    classDef opt stroke-dasharray: 4 4
    class CLAUDE,ARXIV,S2,PUBMED,AMZN,GCAL,TGAPI ext
    class CHROMA,OUT store
    class DS1,DS2,DPL,CF,BOT opt
```

Dashed components are behind Compose profiles and off by default. The core
stack is `agent` + `chromadb`; everything else is opt-in via
`COMPOSE_PROFILES`.

---

## 2. Request flow — Telegram

```mermaid
sequenceDiagram
    autonumber
    participant U as Telegram user
    participant T as Telegram API
    participant CF as cloudflared
    participant B as telegram-bot
    participant A as agent (FastAPI)
    participant O as Orchestrator
    participant S as Skill
    participant C as Claude

    U->>T: message
    T->>CF: POST /telegram/webhook (HTTPS)
    CF->>B: forward over tunnel
    B->>A: POST /query
    A->>O: run(query)

    O->>O: keyword pre-route
    alt ambiguous
        O->>C: classify intent
        C-->>O: skill name
    end

    O->>S: run(query)
    S-->>O: SkillResult
    O->>C: summarise results
    C-->>O: summary
    O-->>A: rendered + SkillResult
    A-->>B: JSON
    B->>T: sendMessage
    T->>U: reply
```

The keyword pre-route exists to skip an API call for obvious queries — a
message containing "paper" or "arxiv" never needs Claude to classify it.

---

## 3. Skills and MCP packaging

```mermaid
graph LR
    subgraph manifests["skills/manifests/"]
        M1["literature.skill.json"]
        M2["amazon.skill.json"]
    end

    LOADER["manifest_loader.py<br/>discover + validate"]

    subgraph consumers["Consumers"]
        EP["GET /skills<br/>registry endpoint"]
        UI["Web UI sidebar"]
        MCP1["literature_server<br/><i>MCP / stdio</i>"]
        MCP2["amazon_server<br/><i>MCP / stdio</i>"]
    end

    EXT["External MCP clients<br/>Claude Desktop, IDEs"]

    M1 --> LOADER
    M2 --> LOADER
    LOADER --> EP
    LOADER --> MCP1
    LOADER --> MCP2
    EP --> UI
    MCP1 <--> EXT
    MCP2 <--> EXT
```

The manifest is the single source of truth. Tool names, descriptions,
versions, and JSON Schemas are read from it by the registry endpoint, the UI,
and both MCP servers — so a published manifest and a running server cannot
disagree. A test enforces the parity.

Adding a skill is one new `skill.json`; it then appears in the API, the
sidebar, and the registry with no code change.

---

## 4. Deployment and update flow

```mermaid
graph TB
    DEV["Developer"] -->|"git push"| GH["GitHub<br/>master"]

    GH -->|"push webhook<br/>HMAC-SHA256"| WH["deploy_webhook.py<br/>:9000 (host)"]
    WH -->|"if branch matches"| DEPLOY["deploy.sh"]
    DEV -.->|"manual"| DEPLOY

    DEPLOY --> P1["git fetch + ff-only"]
    P1 --> P2["docker compose build"]
    P2 --> P3["docker compose up -d"]
    P3 --> P4["poll /health 60s"]
    P4 -->|"healthy"| OK["log SUCCESS"]
    P4 -->|"unreachable"| BAD["log UNHEALTHY<br/>exit 1"]
    P2 -->|"build fails"| RB["reset to previous commit<br/>log FAILED"]

    LD["launchd<br/>com.agentfactory"] -->|"RunAtLoad<br/>KeepAlive"| CTL["agentctl.sh supervise"]
    CTL -->|"foreground"| STACK["docker compose up"]

    classDef bad fill:#4a1d1d,stroke:#c53030,color:#fed7d7
    classDef good fill:#1a4731,stroke:#2f855a,color:#c6f6d5
    class BAD,RB bad
    class OK good
```

Two deliberate properties:

- **Build failure rolls the checkout back.** The box is never left on code
  that has no matching image.
- **An unreachable API is a failed deploy**, even when every command exited 0.
  Otherwise a green deploy can leave the service down.

---

## 5. Configuration and secrets

```mermaid
graph LR
    ENV[".env<br/>0600, gitignored"]
    EX[".env.example<br/>committed template"]

    ENV -->|"load_dotenv<br/>override=True"| SET["config/settings.py"]
    SET --> VAL["validate_env()"]
    SET --> APP["Application"]

    ENV -->|"env_file"| COMPOSE["docker compose"]
    COMPOSE --> CONTAINERS["containers"]

    AUDIT["audit_secrets.sh"] -.->|"scans history"| GITH["git history"]
    AUDIT -.->|"pre-commit --staged"| STAGED["staged diff"]

    EX -.->|"cp"| ENV

    classDef secret fill:#4a3d1d,stroke:#d69e2e,color:#faf089
    class ENV secret
```

`override=True` makes the file authoritative over an already-exported shell
variable — the opposite of the default, and deliberate: a stale export
silently beating the `.env` you just edited cost real debugging time in
Sprint 2.

`GOOGLE_CALENDAR_CREDENTIALS` holds a **path**, not the credential body. An
environment variable leaks into `docker inspect`, crash reports, and
`/proc/<pid>/environ`.

---

## 6. Component reference

| Component | Runs as | Profile | Purpose |
|---|---|---|---|
| `agent` | container | default | FastAPI API — `/query`, `/skills`, `/health`, `/ui` |
| `chromadb` | container | default | Vector store, named volume, not published to host |
| `telegram-bot` | container | `telegram` | Bridges Telegram to the API |
| `agent-dapr`, `telegram-dapr` | container | `dapr` | Sidecars, `network_mode: service:<app>` |
| `dapr-placement` | container | `dapr` | Actor placement |
| `cloudflared` | container | `tunnel` | Public HTTPS ingress |
| `deploy_webhook.py` | host process | — | Push-triggered deploys; on the host so it can restart containers |
| `launchd` agent | host | — | Supervises the stack, restarts on crash and reboot |
| MCP servers | on demand | — | `python -m skills.mcp.{literature,amazon}_server` |

---

## 7. What is not built yet

Stated plainly so the diagram is not read as a description of working
software:

- **Google Calendar** appears above because Sprint 3 scopes it, but the OAuth
  flow and calendar tools are not implemented. `GOOGLE_CALENDAR_CREDENTIALS`
  is wired through config and nothing reads it yet.
- **ChromaDB** runs as a service and the app is configured to reach it, but
  the embedding and recall paths are not implemented — memory is still
  `outputs/memory.json` via `agent/memory.py`.
- **`telegram-bot`** has a Compose service and a command
  (`app.channels.telegram_bot`); that module does not exist yet.
- **Dapr sidecars** are configured with in-memory state and pub/sub
  components, but no application code calls Dapr.
- The **`docker build` has never completed successfully** — see PROJ-199.

Everything else in this document is implemented and covered by the test suite
(`./run.sh test`, 208 checks).
