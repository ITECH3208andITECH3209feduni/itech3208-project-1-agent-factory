# app/web_ui/Dockerfile — Agent Factory Web UI (PROJ-374-378)
# ──────────────────────────────────────────────────────────────
# Honest scope note: this Dockerfile is new for this ticket. The two
# Dockerfiles that already existed in this repo (root ./Dockerfile,
# ./container/Dockerfile) build the *NanoClaw orchestrator* and the
# *NanoClaw agent-runner container* respectively — neither one builds
# or serves the FastAPI web app (app/web_ui). "Docker smoke-test the
# deployable app" therefore had nothing to smoke-test until this file
# existed, which is why PROJ-374 was left in To Do rather than
# claimed done. This file + the docker-smoke-test CI job below close
# that specific gap.
#
# Still explicitly out of scope: Dapr. There is no Dapr sidecar,
# component, or reference anywhere in this codebase (verified via
# repo-wide search before writing this file) — Dapr was never
# introduced, so there is nothing to build a Dapr CI stage against.
# That's a real architecture decision for the team, not something a
# Dockerfile can silently invent.
# ──────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt requirements_web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements_web.txt

# Copy application code
COPY agent/ ./agent/
COPY app/ ./app/
COPY config/ ./config/
COPY static/ ./static/
COPY skills/ ./skills/
COPY components/ ./components/

# Runtime data directory (SQLite DBs — see config/settings.py) lives
# under outputs/, created on first write; declared here so it's
# obvious this is where persistent state would need a volume mount
# in a real deployment.
RUN mkdir -p /app/outputs

EXPOSE 8000

# No secrets baked into the image — API keys are supplied at runtime
# via environment variables / mounted .env, same as local dev.
CMD ["uvicorn", "app.web_ui.main:app", "--host", "0.0.0.0", "--port", "8000"]
