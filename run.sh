#!/usr/bin/env bash
# run.sh — Canonical entry point for Agent Factory (PROJ-380)
#
# This is THE way to launch the app. Before this existed we had several
# competing invocations (python main.py from wherever you happened to be
# cd'd, a venv that may or may not be active, ad-hoc PYTHONPATH exports),
# and running from the wrong worktree silently picked up the wrong code.
#
# The script resolves its own directory and cd's there, so it behaves
# identically no matter where you invoke it from or which clone it lives in.
#
# Usage:
#   ./run.sh                                 # interactive CLI
#   ./run.sh -q "RAG architecture"           # single query
#   ./run.sh -q "best laptop" --save         # save output
#   ./run.sh --history                       # recent queries
#   ./run.sh serve                           # FastAPI web server (uvicorn)
#   ./run.sh test                            # run the smoke tests
#   ./run.sh --no-venv ...                   # use ambient Python, skip venv
#
# Environment:
#   AGENT_FACTORY_PYTHON   override interpreter (default: python3, then python)
#   HOST / PORT            bind address for `serve` (default 0.0.0.0:8000)

set -euo pipefail

# ── Resolve the real project root, following symlinks ─────────
# BASH_SOURCE can be a symlink (e.g. /usr/local/bin/agent-factory -> run.sh);
# walk the chain so PROJECT_ROOT is always the actual checkout.
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  # Relative symlink targets resolve against the link's directory.
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")" && pwd)"

cd "$PROJECT_ROOT"

# Anything the app imports resolves against the root, not the caller's cwd.
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Unbuffered output so `./run.sh serve | tee` and container logs stay live.
export PYTHONUNBUFFERED=1

VENV_DIR="$PROJECT_ROOT/.venv"
USE_VENV=1

# ── Flags consumed by the launcher itself ─────────────────────
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --no-venv) USE_VENV=0 ;;
    *)         ARGS+=("$arg") ;;
  esac
done
set -- ${ARGS[@]+"${ARGS[@]}"}

# ── Pick an interpreter ───────────────────────────────────────
# Being on PATH is not enough. On Windows, `python3` is often a Microsoft
# Store stub that resolves fine under `command -v` but fails the moment you
# execute it. So actually run each candidate and check it reports a version.
works() {
  command -v "$1" >/dev/null 2>&1 && "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

pick_python() {
  if [ -n "${AGENT_FACTORY_PYTHON:-}" ]; then
    if works "$AGENT_FACTORY_PYTHON"; then
      echo "$AGENT_FACTORY_PYTHON"
      return
    fi
    echo "ERROR: AGENT_FACTORY_PYTHON='$AGENT_FACTORY_PYTHON' is not a working Python 3.9+." >&2
    exit 1
  fi

  for candidate in python3 python py; do
    if works "$candidate"; then
      echo "$candidate"
      return
    fi
  done

  echo "ERROR: no working Python 3.9+ found (tried python3, python, py)." >&2
  echo "       Install Python 3.9+ or set AGENT_FACTORY_PYTHON to its path." >&2
  echo "       On Windows, a bare 'python3' is often the Microsoft Store stub;" >&2
  echo "       install real Python from python.org or use Git Bash with it on PATH." >&2
  exit 1
}

PYTHON="$(pick_python)"

# ── Virtualenv ────────────────────────────────────────────────
# Created on first run. Skipped entirely inside Docker, where the image
# already has the deps installed and a nested venv is just overhead.
if [ "$USE_VENV" = "1" ] && [ ! -f /.dockerenv ]; then
  if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating virtualenv at .venv"
    "$PYTHON" -m venv "$VENV_DIR"
  fi

  # shellcheck disable=SC1091
  if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"          # macOS / Linux
  elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    source "$VENV_DIR/Scripts/activate"      # Windows (Git Bash)
  fi
  PYTHON="python"

  # Install deps when requirements.txt is newer than our last-install stamp.
  STAMP="$VENV_DIR/.deps-installed"
  if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
    echo "==> Installing dependencies"
    "$PYTHON" -m pip install --quiet --upgrade pip
    "$PYTHON" -m pip install --quiet -r requirements.txt
    touch "$STAMP"
  fi
fi

# ── .env ──────────────────────────────────────────────────────
# config/settings.py calls load_dotenv() itself; this is only so the
# warning fires early rather than deep inside a traceback.
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  echo "WARNING: no .env found at project root."
  echo "         cp .env.example .env  and fill in ANTHROPIC_API_KEY"
fi

# ── Subcommands ───────────────────────────────────────────────
case "${1:-}" in
  serve)
    shift
    HOST="${HOST:-0.0.0.0}"
    PORT="${PORT:-8000}"
    echo "==> Agent Factory API on http://${HOST}:${PORT}  (root: $PROJECT_ROOT)"
    exec "$PYTHON" -m uvicorn app.web.main:app --host "$HOST" --port "$PORT" "$@"
    ;;
  test)
    shift
    echo "==> Running smoke tests  (root: $PROJECT_ROOT)"
    # Run every suite even if an early one fails, then report once — a single
    # red suite shouldn't hide the state of the others.
    rc=0
    for suite in scripts/test_*.py; do
      [ -e "$suite" ] || continue
      echo
      echo "--- $suite"
      "$PYTHON" "$suite" "$@" || rc=1
    done
    echo
    [ "$rc" -eq 0 ] && echo "==> All suites passed" || echo "==> One or more suites FAILED"
    exit "$rc"
    ;;
  *)
    exec "$PYTHON" main.py "$@"
    ;;
esac
