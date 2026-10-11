#!/bin/sh
# Runs the web app and both reminder loops in one container. SQLite needs a
# single writer machine, so they share one process group and one volume.
set -eu

python -m agent.reminders.scheduler &
python -m agent.reminders.web_bridge &
# Behind the host's TLS proxy, trust X-Forwarded-* so request.url is https://
# — Twilio signature validation hashes the exact public URL.
exec uvicorn app.web_ui.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "*"
