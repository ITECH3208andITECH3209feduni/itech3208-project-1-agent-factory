#!/usr/bin/env bash
# scripts/serve_up.sh — run Agent Factory on an always-on machine (Mac mini)
# and publish it at a PERMANENT free URL with Tailscale Funnel.
#
# Usage: ./scripts/serve_up.sh [env-file]     (default: .env)
#        ./scripts/serve_up.sh --down         (stop the app and the tunnel)
#
# Tunnel choice (default is unchanged): TUNNEL=tailscale (Funnel, the default).
# Opt in to ngrok's free static domain with
#        TUNNEL=ngrok NGROK_DOMAIN=<name>.ngrok-free.app ./scripts/serve_up.sh
# ngrok is never started unless TUNNEL=ngrok is set explicitly.
#
# One-time Tailscale setup is in docs/MAC_MINI.md. Unlike scripts/demo_up.sh
# (quick tunnel, new URL every run), the URL here never changes, so the Twilio
# webhooks are pasted once.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.web.yml"
TUNNEL="${TUNNEL:-tailscale}"
NGROK_PID_FILE="${TMPDIR:-/tmp}/agentfactory-ngrok.pid"
NGROK_LOG="${TMPDIR:-/tmp}/agentfactory-ngrok.log"

case "$TUNNEL" in
  tailscale)
    TS="$(command -v tailscale || true)"
    [ -n "$TS" ] || TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    [ -x "$TS" ] || { echo "Tailscale not found. See docs/MAC_MINI.md step 3." >&2; exit 1; }
    ;;
  ngrok)
    NGROK="$(command -v ngrok || true)"
    [ -n "$NGROK" ] || NGROK="$HOME/bin/ngrok"
    [ -x "$NGROK" ] || { echo "ngrok not found. See docs/MAC_MINI.md (ngrok option)." >&2; exit 1; }
    if [ "${1:-}" != "--down" ]; then
      [ -n "${NGROK_DOMAIN:-}" ] || { echo "Set NGROK_DOMAIN to your free static domain, e.g. NGROK_DOMAIN=name.ngrok-free.app" >&2; exit 1; }
    fi
    ;;
  *)
    echo "Unknown TUNNEL='$TUNNEL' (use tailscale or ngrok)." >&2; exit 1
    ;;
esac

if [ "${1:-}" = "--down" ]; then
  if [ "$TUNNEL" = "ngrok" ]; then
    if [ -f "$NGROK_PID_FILE" ]; then kill "$(cat "$NGROK_PID_FILE")" 2>/dev/null || true; rm -f "$NGROK_PID_FILE"; fi
  else
    "$TS" funnel reset || true
  fi
  $COMPOSE down
  echo "Stopped."
  exit 0
fi

command -v docker >/dev/null || { echo "Install Docker Desktop first." >&2; exit 1; }

export ENV_FILE="${1:-.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "warning: $ENV_FILE not found — starting without API keys (Claude, Twilio and email stay off)." >&2
fi
if [ -f "$ENV_FILE" ] && grep -q '^TWILIO_AUTH_TOKEN=.\+' "$ENV_FILE"; then
  export TWILIO_VALIDATE_SIGNATURE=true
fi

$COMPOSE up -d --build

for _ in $(seq 1 60); do
  curl -sf http://localhost:8000/status >/dev/null && break
  sleep 1
done
curl -sf http://localhost:8000/status >/dev/null || { echo "App did not come up:" >&2; $COMPOSE logs --tail 30 >&2; exit 1; }

if [ "$TUNNEL" = "ngrok" ]; then
  # Replace a previous tunnel of ours, then start the new one in the background.
  if [ -f "$NGROK_PID_FILE" ]; then kill "$(cat "$NGROK_PID_FILE")" 2>/dev/null || true; fi
  nohup "$NGROK" http --url="$NGROK_DOMAIN" 8000 --log=stdout >"$NGROK_LOG" 2>&1 &
  echo $! >"$NGROK_PID_FILE"
  URL=""
  for _ in $(seq 1 20); do
    if ! kill -0 "$(cat "$NGROK_PID_FILE")" 2>/dev/null; then break; fi
    if grep -q "started tunnel" "$NGROK_LOG" 2>/dev/null; then URL="https://${NGROK_DOMAIN}"; break; fi
    sleep 1
  done
  [ -n "$URL" ] || { echo "ngrok did not start. Is the authtoken set (ngrok config add-authtoken ...)?" >&2; tail -5 "$NGROK_LOG" >&2 || true; exit 1; }
  STOP_HINT="Stop everything with: TUNNEL=ngrok ./scripts/serve_up.sh --down"
else
  "$TS" funnel --bg 8000 >/dev/null
  URL="$("$TS" funnel status 2>/dev/null | grep -oE 'https://[A-Za-z0-9.-]+\.ts\.net' | head -1 || true)"
  [ -n "$URL" ] || { echo "Funnel did not start. Is Funnel enabled for this tailnet? See docs/MAC_MINI.md." >&2; "$TS" funnel status >&2 || true; exit 1; }
  STOP_HINT="Stop everything with: ./scripts/serve_up.sh --down"
fi

cat <<MSG

Agent Factory is live at: $URL   (permanent — this URL does not change)

  health      $URL/status
  scheduler   $URL/status/scheduler

Paste these into the Twilio console ONCE (HTTP POST):
  Messaging webhook   $URL/twilio/sms
  Voice webhook       $URL/twilio/voice
  Status callback     $URL/twilio/status-callback

$STOP_HINT
MSG
