# Secrets Management

How Agent Factory stores credentials locally, and how to rotate them (PROJ-319..323).

---

## Where secrets live

Everything lives in a single `.env` at the project root. Nowhere else — not in
`config/settings.py`, not in `docker-compose.yml`, not in a shell profile.

| Secret | Used for | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude routing, synthesis, summarisation | **Yes** |
| `BOT_TOKEN` | Telegram bot | Only with the `telegram` profile |
| `GOOGLE_CALENDAR_CREDENTIALS` | Calendar OAuth (a **path**, not the JSON) | Only for calendar features |
| `S2_API_KEY` | Semantic Scholar rate limit | No — degrades to a smaller quota |
| `JWT_SECRET` | Web API session tokens | Before exposing the API |
| `CLOUDFLARE_TUNNEL_TOKEN` | Public tunnel | Only with the `tunnel` profile |
| `DEPLOY_WEBHOOK_SECRET` | GitHub push webhook | Only for auto-deploy |

`.env` is gitignored (`.env`, `*.env` in `.gitignore`) and excluded from the
Docker build context (`.dockerignore`), so it never reaches an image layer.

`GOOGLE_CALENDAR_CREDENTIALS` holds a **filesystem path**, deliberately. Putting
the credential body in an environment variable leaks it into `docker inspect`,
crash reports, and any process that can read `/proc/<pid>/environ`.

### Setup

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
./scripts/secure-secrets.sh
```

`secure-secrets.sh` fixes permissions, confirms git is ignoring the file,
checks no placeholder values were left in, and runs the history audit.
Use `--verify` in CI to check without modifying anything.

---

## Rotation

Rotate on a schedule, and immediately if a key is pasted into a chat, commit,
screenshot, or log.

### General procedure

1. Create the **new** credential first — never revoke before you have a replacement
2. Update `.env`
3. `./scripts/secure-secrets.sh`
4. `./scripts/macos/agentctl.sh restart`
5. Verify the affected feature works
6. **Only then** revoke the old credential

Step 6 last is what keeps rotation from becoming an outage.

### Per-credential

**`ANTHROPIC_API_KEY`** — console.anthropic.com → API Keys → Create Key.
Update `.env`, restart, confirm with a query, then delete the old key.
*Verify:* `./run.sh -q "test"` returns a summary rather than a warning.

**`BOT_TOKEN`** — Telegram @BotFather → `/revoke` → `/token`. Note this
invalidates the old token **immediately**, so it is the one case where you
cannot overlap. Re-register the webhook afterwards:

```bash
source .env
curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://${PUBLIC_HOSTNAME}/telegram/webhook"
```

**`GOOGLE_CALENDAR_CREDENTIALS`** — Google Cloud Console → APIs & Services →
Credentials → the OAuth client → Add secret, then delete the old one. Download
the new JSON, point `GOOGLE_CALENDAR_CREDENTIALS` at it, delete the cached token
at `GOOGLE_CALENDAR_TOKEN_PATH` (default `store/google_calendar_token.json`), and
re-run the consent flow.

**`S2_API_KEY`** — request a new key from Semantic Scholar; the old one keeps
working until they expire it. Lowest urgency: the worst case is a rate limit.

**`JWT_SECRET`** — `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Rotating invalidates every issued session token, so all users re-authenticate.
Must be at least 32 characters; `validate_env()` flags anything shorter.

**`CLOUDFLARE_TUNNEL_TOKEN`** — Zero Trust dashboard → Networks → Tunnels →
the tunnel → Refresh token.

**`DEPLOY_WEBHOOK_SECRET`** — generate a new value, update `.env`, restart the
listener, then update the matching secret in GitHub → Settings → Webhooks.
Pushes fail signature verification in between, which is the safe direction.

### Suggested cadence

| Credential | Routine | Immediately if |
|---|---|---|
| `ANTHROPIC_API_KEY` | 90 days | exposed, or unexpected billing |
| `BOT_TOKEN` | 180 days | exposed |
| `JWT_SECRET` | 90 days | exposed, or suspected session hijack |
| `DEPLOY_WEBHOOK_SECRET` | 180 days | exposed |
| `GOOGLE_CALENDAR_CREDENTIALS` | 365 days | exposed |
| `S2_API_KEY` | as needed | exposed |

---

## History audit

```bash
./scripts/audit_secrets.sh              # full history
./scripts/audit_secrets.sh --staged     # staged changes only
```

Five checks: secret files untracked, never committed historically, no live
credential shapes anywhere in the diff history, `.gitignore` coverage, and
`.env` at 0600 on POSIX.

**Current result: PASS.** No `.env` has ever been committed across the
repository's history, and no live key material was found.

The scanner filters obvious placeholders (`your-token-here`, `xoxb-test-token`,
`.env.example`). That is deliberate: the first run flagged template files and
test fixtures, and a scanner that cries wolf every run is one people learn to
ignore. It was checked against a negative control to confirm it still catches
realistic Anthropic, Telegram, and AWS key shapes.

### Pre-commit

The Husky `pre-commit` hook runs `audit_secrets.sh --staged`, so a commit that
would introduce a credential is blocked before it becomes a history problem.

To bypass in an emergency — and only then:

```bash
git commit --no-verify
```

---

## If a secret is committed

**Rotate it first.** Everything else is secondary.

Once a secret is pushed, assume it is compromised. Automated scrapers find
credentials in public repos within minutes. Rewriting history does not undo
that — the value is already out, and it stays reachable through forks, clones,
caches, and the GitHub API for a long time.

1. **Revoke and reissue the credential.** This is the only step that genuinely fixes it.
2. Remove it from the working tree and commit.
3. Optionally scrub history with `git filter-repo` or BFG. This is disruptive —
   every collaborator must re-clone — and it is cosmetic once the key is rotated.
4. Tell the team, so nobody keeps using the dead credential.
5. Re-run `./scripts/audit_secrets.sh` to confirm the tree is clean.
