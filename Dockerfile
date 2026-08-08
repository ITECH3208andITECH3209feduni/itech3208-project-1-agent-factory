# Dockerfile — Agent Factory (PROJ-299..303)
#
# Multi-stage: a builder that compiles wheels, and a slim runtime that gets
# only the installed packages. Build toolchains and pip caches never reach
# the final image.
#
#   docker build -t agent-factory .
#   docker run --rm -p 8000:8000 --env-file .env agent-factory

# ══════════════════════════════════════════════════════════════
# Stage 1 — builder
# ══════════════════════════════════════════════════════════════
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build-time only: lxml needs libxml2/libxslt headers and a C compiler.
# None of this is carried into the runtime stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install into a self-contained venv we can copy wholesale into the runtime.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Its own layer, so editing application code does not reinstall dependencies.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ══════════════════════════════════════════════════════════════
# Stage 2 — runtime
# ══════════════════════════════════════════════════════════════
FROM python:3.11-slim AS runtime

# Runtime libraries only: Chromium for Playwright, and the shared objects
# lxml links against. No compilers.
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        fonts-liberation \
        fonts-noto-color-emoji \
        libgbm1 \
        libnss3 \
        libatk-bridge2.0-0 \
        libgtk-3-0 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libpangocairo-1.0-0 \
        libcups2 \
        libdrm2 \
        libxshmfence1 \
        libxml2 \
        libxslt1.1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
    PLAYWRIGHT_BROWSERS_PATH=/usr/bin

# Tunable at run time (docker run -e / compose environment:).
ENV HOST=0.0.0.0 \
    PORT=8000 \
    LOG_LEVEL=INFO \
    APP_VERSION=3.0.0 \
    CHROMADB_PATH=/data/chromadb

# Non-root. A fixed uid/gid keeps ownership stable across rebuilds and makes
# bind-mounted volume permissions predictable on the host.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appuser . .

# Writable paths. /data is where the compose volume mounts.
RUN mkdir -p /app/outputs /data/chromadb \
    && chown -R appuser:appuser /app/outputs /data

USER appuser

EXPOSE 8000

# Hits the app's own readiness logic rather than just opening a socket.
# /health returns 200 while serving even when under-configured, so a missing
# API key surfaces in the body instead of causing a restart loop that cannot
# possibly fix it.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# Shell form so ${HOST} and ${PORT} expand from the environment.
CMD uvicorn app.web.main:app --host "${HOST}" --port "${PORT}"
