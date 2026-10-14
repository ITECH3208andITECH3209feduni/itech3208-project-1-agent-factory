#!/bin/sh
# Runs the web app and both reminder loops in one container. SQLite needs a
# single writer machine, so they share one process group and one volume.
set -eu

# Hosts without a persistent disk (Render free) have no /data yet.
mkdir -p "${CRM_STORE_DIR:-/data/store}"

python -m agent.reminders.scheduler &
python -m agent.reminders.web_bridge &
# Behind the host's TLS proxy, trust X-Forwarded-* so request.url is https://
# — Twilio signature validation hashes the exact public URL.
# Optional: reload the demo account and sample data on every boot, for hosts
# that wipe storage on restart. Needs DEMO_PASSWORD so the public URL never
# serves the well-known default login.
if [ "${SEED_DEMO:-}" = "true" ]; then
  if [ -n "${DEMO_PASSWORD:-}" ]; then
    (
      for _ in $(seq 1 60); do
        if python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/status', timeout=2)" 2>/dev/null; then
          python scripts/seed_demo.py "http://127.0.0.1:${PORT:-8000}" || true
          exit 0
        fi
        sleep 2
      done
    ) &
  else
    echo "SEED_DEMO=true but DEMO_PASSWORD is not set; skipping demo seed." >&2
  fi
fi

exec uvicorn app.web_ui.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "*"
