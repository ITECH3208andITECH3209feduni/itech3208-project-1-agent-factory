#!/usr/bin/env bash
# Writes Gmail SMTP settings into .env without the password ever appearing in
# chat, shell history, or process arguments.
#
#   ./scripts/set_gmail_smtp.sh [path/to/.env]
#
# You need a Gmail account with 2-step verification on and an App Password
# (Google Account > Security > App passwords). Use the 16-character app
# password, not your normal Gmail password.
set -euo pipefail

ENV_FILE="${1:-.env}"
[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE found." >&2; exit 1; }

read -r -p "Gmail address: " GMAIL
read -r -s -p "App password (hidden): " APP_PW
echo
APP_PW="${APP_PW// /}"   # Google shows it with spaces; they are not part of it

[ -n "$GMAIL" ] && [ -n "$APP_PW" ] || { echo "Both values are required." >&2; exit 1; }

GMAIL="$GMAIL" APP_PW="$APP_PW" ENV_FILE="$ENV_FILE" python3 - <<'PY'
import os, re
path = os.environ["ENV_FILE"]
vals = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": os.environ["GMAIL"],
    "SMTP_PASSWORD": os.environ["APP_PW"],
    "SMTP_FROM_EMAIL": os.environ["GMAIL"],
    "SMTP_USE_TLS": "true",
}
lines = open(path).read().splitlines()
seen = set()
out = []
for line in lines:
    m = re.match(r"^([A-Z_]+)=", line)
    if m and m.group(1) in vals:
        out.append(f"{m.group(1)}={vals[m.group(1)]}")
        seen.add(m.group(1))
    else:
        out.append(line)
for k, v in vals.items():
    if k not in seen:
        out.append(f"{k}={v}")
open(path, "w").write("\n".join(out) + "\n")
PY

echo "Saved SMTP settings to $ENV_FILE (password not shown)."
echo "Next: restart the stack, then tell Claude to send a test email."
