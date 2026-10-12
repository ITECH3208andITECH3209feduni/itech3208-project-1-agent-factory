#!/usr/bin/env bash
# scripts/demo_up.sh — run Agent Factory locally and expose it with a free
# Cloudflare quick tunnel (no account, no card). Prints the public URL and the
# three Twilio webhook URLs to paste into the Twilio console.
#
# Usage: ./scripts/demo_up.sh [env-file]     (default: .env)
#        ./scripts/demo_up.sh --down         (stop the app and the tunnel)
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.web.yml"
PIDFILE="outputs/.tunnel.pid"
LOGFILE="outputs/.tunnel.log"
mkdir -p outputs

if [ "${1:-}" = "--down" ]; then
  [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
  $COMPOSE down
  echo "Stopped."
  exit 0
fi

command -v docker >/dev/null      || { echo "Install Docker Desktop first." >&2; exit 1; }
command -v cloudflared >/dev/null || { echo "Install cloudflared: brew install cloudflared" >&2; exit 1; }

export ENV_FILE="${1:-.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "warning: $ENV_FILE not found — starting without API keys (Claude, Twilio and email features stay off)." >&2
fi
if [ -f "$ENV_FILE" ] && grep -q '^TWILIO_AUTH_TOKEN=.\+' "$ENV_FILE"; then
  export TWILIO_VALIDATE_SIGNATURE=true
fi

$COMPOSE up -d --build

echo "Waiting for the app..."
for _ in $(seq 1 40); do
  curl -sf http://localhost:8000/status >/dev/null && break
  sleep 1
done
curl -sf http://localhost:8000/status >/dev/null || { echo "App did not come up:" >&2; $COMPOSE logs --tail 30 >&2; exit 1; }

[ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null || true
: > "$LOGFILE"
nohup cloudflared tunnel --no-autoupdate --url http://localhost:8000 >"$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

URL=""
for _ in $(seq 1 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGFILE" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "Tunnel did not start; see $LOGFILE" >&2; exit 1; }

cat <<MSG

Agent Factory is live at: $URL

  health      $URL/status
  scheduler   $URL/status/scheduler

Paste these into the Twilio console for your number (HTTP POST):
  Messaging webhook   $URL/twilio/sms
  Voice webhook       $URL/twilio/voice
  Status callback     $URL/twilio/status-callback

The URL changes every time the tunnel restarts. Stop everything with:
  ./scripts/demo_up.sh --down
MSG
