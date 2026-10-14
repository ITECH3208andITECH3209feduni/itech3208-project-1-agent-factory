#!/bin/sh
# Runs the web app and both reminder loops in one container. SQLite needs a
# single writer machine, so they share one process group and one volume.
set -eu

# Hosts without a persistent disk (Render free) start with an empty /data. If a
# bucket is configured (PERSIST_S3_*), bring the last saved copy back first, before
# anything opens a database; with no bucket configured this does nothing.
python deploy/persist.py restore || true
mkdir -p "${CRM_STORE_DIR:-/data/store}"
# ...and keep saving it while running (see the TERM handler below for the last save).
python deploy/persist.py loop &

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

uvicorn app.web_ui.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "*" &
UVICORN_PID=$!

# On stop or sleep the host sends TERM: let the web app finish, then save once more.
trap 'kill -TERM "$UVICORN_PID" 2>/dev/null; wait "$UVICORN_PID" 2>/dev/null; python deploy/persist.py snapshot || true; exit 0' TERM INT
wait "$UVICORN_PID"
