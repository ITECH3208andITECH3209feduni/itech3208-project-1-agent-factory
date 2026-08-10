#!/usr/bin/env bash
# scripts/deploy.sh — pull, rebuild, restart (PROJ-314..318)
#
#   ./scripts/deploy.sh                 deploy the current branch
#   ./scripts/deploy.sh --check         report whether a deploy is needed, do nothing
#   ./scripts/deploy.sh --force         deploy even if already up to date
#   DEPLOY_BRANCH=main ./scripts/deploy.sh
#
# Appends a structured result line to logs/deploy.log on every run, success or
# failure, so `tail logs/deploy.log` always answers "what happened last time".
#
# Exit codes:  0 deployed (or already current)   1 failed   2 misuse

set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p logs
LOG_FILE="$PROJECT_ROOT/logs/deploy.log"
STARTED_AT=$(date '+%Y-%m-%d %H:%M:%S')
START_EPOCH=$(date +%s)

# The ticket says "main", but this repo does its work on master. Defaulting to
# whatever is checked out is what a deployer actually wants; override with
# DEPLOY_BRANCH when that is wrong.
DEPLOY_BRANCH="${DEPLOY_BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
REMOTE="${DEPLOY_REMOTE:-origin}"

MODE="deploy"
case "${1:-}" in
  --check) MODE="check" ;;
  --force) MODE="force" ;;
  "")      ;;
  *)       echo "usage: $0 [--check|--force]" >&2; exit 2 ;;
esac

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fail() {
  local reason="$1"
  local elapsed=$(( $(date +%s) - START_EPOCH ))
  log "DEPLOY FAILED: $reason"
  echo "$STARTED_AT | FAILED | branch=$DEPLOY_BRANCH | from=${OLD_SHA:-unknown} | to=${NEW_SHA:-unknown} | ${elapsed}s | $reason" >> "$LOG_FILE"
  exit 1
}

log "=== Deploy started (branch=$DEPLOY_BRANCH, mode=$MODE) ==="

# ── Preflight ─────────────────────────────────────────────────
command -v git >/dev/null 2>&1 || fail "git not found"

# --check only reports whether an update exists. Requiring Docker for that
# would make the cheap read-only path hang whenever the daemon is down or
# slow, which defeats the point of having it.
if [ "$MODE" != "check" ]; then
  command -v docker >/dev/null 2>&1 || fail "docker not found"
  # `docker info` blocks for a long time against an unresponsive daemon, so
  # bound it rather than hanging the deploy.
  if command -v timeout >/dev/null 2>&1; then
    timeout 30 docker info >/dev/null 2>&1 || fail "Docker daemon not responding within 30s"
  else
    docker info >/dev/null 2>&1 || fail "Docker daemon not running"
  fi

  # Refuse to clobber uncommitted work. A deploy that silently discards local
  # edits is far worse than one that stops and says so.
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    fail "working tree has uncommitted changes; commit or stash them first"
  fi
fi

OLD_SHA=$(git rev-parse --short HEAD)

# ── Fetch ─────────────────────────────────────────────────────
log "Fetching $REMOTE/$DEPLOY_BRANCH"
git fetch --quiet "$REMOTE" "$DEPLOY_BRANCH" || fail "git fetch failed"

REMOTE_SHA=$(git rev-parse --short "$REMOTE/$DEPLOY_BRANCH" 2>/dev/null) \
  || fail "$REMOTE/$DEPLOY_BRANCH does not exist"

if [ "$OLD_SHA" = "$REMOTE_SHA" ] && [ "$MODE" != "force" ]; then
  log "Already up to date at $OLD_SHA"
  if [ "$MODE" = "check" ]; then
    echo "UP_TO_DATE $OLD_SHA"
    exit 0
  fi
  echo "$STARTED_AT | SKIPPED | branch=$DEPLOY_BRANCH | at=$OLD_SHA | 0s | already up to date" >> "$LOG_FILE"
  exit 0
fi

if [ "$MODE" = "check" ]; then
  log "Update available: $OLD_SHA -> $REMOTE_SHA"
  echo "UPDATE_AVAILABLE $OLD_SHA $REMOTE_SHA"
  exit 0
fi

# ── Pull ──────────────────────────────────────────────────────
log "Updating $OLD_SHA -> $REMOTE_SHA"
# --ff-only: never create a merge commit on a deployment box. If the local
# branch has diverged, that is a human problem, not something to auto-resolve.
git checkout --quiet "$DEPLOY_BRANCH" 2>/dev/null || fail "cannot check out $DEPLOY_BRANCH"
git merge --ff-only --quiet "$REMOTE/$DEPLOY_BRANCH" \
  || fail "cannot fast-forward; local branch has diverged from $REMOTE/$DEPLOY_BRANCH"

NEW_SHA=$(git rev-parse --short HEAD)
SUBJECT=$(git log -1 --format=%s)

# ── Rebuild ───────────────────────────────────────────────────
log "Rebuilding images"
if ! docker compose build 2>&1 | tail -20; then
  # Roll the checkout back so the box is not left on code with no image.
  log "Build failed; rolling back to $OLD_SHA"
  git reset --hard --quiet "$OLD_SHA"
  fail "docker compose build failed (rolled back to $OLD_SHA)"
fi

# ── Restart ───────────────────────────────────────────────────
log "Restarting containers"
docker compose up -d --remove-orphans 2>&1 | tail -20 \
  || fail "docker compose up failed"

# ── Verify ────────────────────────────────────────────────────
# A deploy that leaves the API down is a failed deploy, even if every command
# above exited 0.
log "Waiting for health"
HEALTH_URL="http://127.0.0.1:${AGENT_PORT:-8000}/health"
HEALTHY=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 2
done

ELAPSED=$(( $(date +%s) - START_EPOCH ))

if [ "$HEALTHY" -ne 1 ]; then
  log "WARNING: API did not report healthy within 60s"
  docker compose ps
  echo "$STARTED_AT | UNHEALTHY | branch=$DEPLOY_BRANCH | from=$OLD_SHA | to=$NEW_SHA | ${ELAPSED}s | $SUBJECT" >> "$LOG_FILE"
  exit 1
fi

log "=== Deploy OK: $OLD_SHA -> $NEW_SHA in ${ELAPSED}s ==="
log "    $SUBJECT"
echo "$STARTED_AT | SUCCESS | branch=$DEPLOY_BRANCH | from=$OLD_SHA | to=$NEW_SHA | ${ELAPSED}s | $SUBJECT" >> "$LOG_FILE"
exit 0
