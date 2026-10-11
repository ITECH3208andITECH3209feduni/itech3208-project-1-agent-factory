#!/usr/bin/env bash
# scripts/fly_set_secrets.sh — push production secrets from your local .env to
# Fly (PROJ-467). Only the allow-listed names below are sent, and values are
# never printed. Nothing is written to the repo or baked into the image.
#
# Usage: ./scripts/fly_set_secrets.sh [path-to-env-file]   (default: .env)
set -euo pipefail

ENV_FILE="${1:-.env}"
[ -f "$ENV_FILE" ] || { echo "No such file: $ENV_FILE" >&2; exit 1; }
command -v fly >/dev/null || { echo "Install flyctl first: https://fly.io/docs/flyctl/install/" >&2; exit 1; }

ALLOWED="ANTHROPIC_API_KEY AUTH_SECRET_KEY TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM_NUMBER \
SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD SMTP_FROM_EMAIL SMTP_USE_TLS \
GOOGLE_CALENDAR_ID GOOGLE_CALENDAR_KEY_PATH"

args=()
for name in $ALLOWED; do
  line=$(grep -E "^${name}=" "$ENV_FILE" | tail -1 || true)
  value="${line#*=}"
  if [ -n "$value" ]; then
    args+=("${name}=${value}")
  else
    echo "skip  $name (not set in $ENV_FILE)"
  fi
done

[ ${#args[@]} -gt 0 ] || { echo "Nothing to set." >&2; exit 1; }
# Values go over stdin, not argv, so they never show up in `ps`.
printf '%s\n' "${args[@]}" | fly secrets import
echo "Set ${#args[@]} secret(s). Names only: $(printf '%s ' "${args[@]%%=*}")"
