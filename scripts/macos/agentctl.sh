#!/usr/bin/env bash
# scripts/macos/agentctl.sh — Agent Factory service control (PROJ-309..313)
#
#   ./agentctl.sh supervise   run the stack in the foreground (used by launchd)
#   ./agentctl.sh start       start detached
#   ./agentctl.sh stop        stop the stack
#   ./agentctl.sh restart     stop then start
#   ./agentctl.sh status      show container and health state
#   ./agentctl.sh logs [svc]  follow logs
#
# Profiles are read from COMPOSE_PROFILES in .env, so which services run is
# configuration rather than something baked into the launchd plist.

set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")/../.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p logs

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agentctl] $*"; }

# ── Compose profiles ──────────────────────────────────────────
# Read COMPOSE_PROFILES from .env without sourcing the file (which would
# execute anything in it and choke on values containing spaces).
PROFILES="${COMPOSE_PROFILES:-}"
if [ -z "$PROFILES" ] && [ -f .env ]; then
  PROFILES="$(grep -E '^COMPOSE_PROFILES=' .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
fi

PROFILE_ARGS=()
if [ -n "$PROFILES" ]; then
  IFS=',' read -ra _profiles <<< "$PROFILES"
  for p in "${_profiles[@]}"; do
    [ -n "$p" ] && PROFILE_ARGS+=(--profile "$p")
  done
fi

compose() { docker compose ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} "$@"; }

# Compose interpolates the whole file before applying profiles, so the tunnel
# token cannot be marked required there without breaking the default stack.
# Validate it here instead, where we know whether the profile is actually on.
check_profile_requirements() {
  if [[ ",$PROFILES," == *",tunnel,"* ]]; then
    local token="${CLOUDFLARE_TUNNEL_TOKEN:-}"
    if [ -z "$token" ] && [ -f .env ]; then
      token="$(grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' .env 2>/dev/null | tail -1 | cut -d= -f2-)"
    fi
    if [ -z "$token" ]; then
      log "ERROR: COMPOSE_PROFILES includes 'tunnel' but CLOUDFLARE_TUNNEL_TOKEN is empty."
      log "       Set it in .env, or drop 'tunnel' from COMPOSE_PROFILES."
      return 1
    fi
  fi

  if [[ ",$PROFILES," == *",telegram,"* ]]; then
    local bot="${BOT_TOKEN:-}"
    if [ -z "$bot" ] && [ -f .env ]; then
      bot="$(grep -E '^BOT_TOKEN=' .env 2>/dev/null | tail -1 | cut -d= -f2-)"
    fi
    if [ -z "$bot" ]; then
      log "ERROR: COMPOSE_PROFILES includes 'telegram' but BOT_TOKEN is empty."
      log "       Get one from @BotFather, or drop 'telegram' from COMPOSE_PROFILES."
      return 1
    fi
  fi

  return 0
}

# ── Wait for Docker ───────────────────────────────────────────
# At login launchd starts us before Docker Desktop is accepting connections.
# Polling beats failing, but only up to a point — if Docker is genuinely not
# installed we should exit non-zero and let launchd back off.
wait_for_docker() {
  local timeout="${1:-180}"
  local waited=0

  if ! command -v docker >/dev/null 2>&1; then
    log "ERROR: docker not on PATH. Is Docker Desktop installed?"
    return 1
  fi

  # Nudge Docker Desktop awake if the daemon is not answering.
  if ! docker info >/dev/null 2>&1; then
    if [ -d "/Applications/Docker.app" ]; then
      log "Docker daemon not responding; launching Docker Desktop"
      open -g -a Docker || true
    fi
  fi

  while ! docker info >/dev/null 2>&1; do
    if [ "$waited" -ge "$timeout" ]; then
      log "ERROR: Docker daemon did not become ready within ${timeout}s"
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
  done

  log "Docker ready after ${waited}s"
  return 0
}

# ── Commands ──────────────────────────────────────────────────
cmd_supervise() {
  log "=== Agent Factory starting (profiles: ${PROFILES:-none}) ==="
  check_profile_requirements || exit 1
  wait_for_docker 180 || exit 1

  # Pick up image changes made since the last run.
  log "Building images if needed"
  compose build --quiet || log "WARN: build failed; using existing images"

  # Foreground, so launchd supervises the real process. --abort-on-container-failure
  # is deliberately NOT used: one crashed optional service should not tear down
  # the whole stack, and `restart: unless-stopped` already handles recovery.
  log "Starting stack in foreground"
  exec compose up --remove-orphans
}

cmd_start() {
  check_profile_requirements || exit 1
  wait_for_docker 180 || exit 1
  compose up -d --remove-orphans
  log "Started. Check: ./agentctl.sh status"
}

cmd_stop() {
  compose down
  log "Stopped"
}

cmd_status() {
  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon: NOT RUNNING"
    exit 1
  fi
  echo "Docker daemon: ok"
  echo
  compose ps
  echo
  echo "launchd:"
  if launchctl list 2>/dev/null | grep -q com.agentfactory; then
    launchctl list | grep -E 'PID|com.agentfactory' || true
  else
    echo "  com.agentfactory not loaded (run scripts/macos/install-service.sh)"
  fi
  echo
  echo "API health:"
  curl -fsS --max-time 5 "http://127.0.0.1:${AGENT_PORT:-8000}/health" 2>/dev/null || echo "  unreachable"
  echo
}

cmd_logs() {
  if [ $# -gt 0 ]; then
    compose logs -f --tail=100 "$@"
  else
    compose logs -f --tail=100
  fi
}

case "${1:-status}" in
  supervise) cmd_supervise ;;
  start)     cmd_start ;;
  stop)      cmd_stop ;;
  restart)   cmd_stop; cmd_start ;;
  status)    cmd_status ;;
  logs)      shift; cmd_logs "$@" ;;
  *)
    echo "usage: $0 {supervise|start|stop|restart|status|logs [service]}" >&2
    exit 2
    ;;
esac
