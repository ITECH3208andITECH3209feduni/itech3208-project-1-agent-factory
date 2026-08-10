#!/usr/bin/env bash
# scripts/macos/install-service.sh — install the launchd agent (PROJ-309..313)
#
#   ./scripts/macos/install-service.sh              install and start
#   ./scripts/macos/install-service.sh --uninstall  stop and remove
#
# Renders launchd/com.agentfactory.plist into ~/Library/LaunchAgents and loads
# it, so the stack survives crashes and comes back after reboot.

set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")/../.." && pwd)"

LABEL="com.agentfactory"
TEMPLATE="$PROJECT_ROOT/launchd/$LABEL.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET="$TARGET_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERROR: launchd is macOS-only. This machine reports $(uname -s)." >&2
  echo "       On Linux use a systemd --user unit instead." >&2
  exit 1
fi

# ── Uninstall ─────────────────────────────────────────────────
if [ "${1:-}" = "--uninstall" ]; then
  echo "==> Stopping and removing $LABEL"
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$TARGET"
  "$PROJECT_ROOT/scripts/macos/agentctl.sh" stop || true
  echo "Removed. The repo and Docker volumes are untouched."
  exit 0
fi

# ── Preflight ─────────────────────────────────────────────────
[ -f "$TEMPLATE" ] || { echo "ERROR: template missing: $TEMPLATE" >&2; exit 1; }

if [ ! -f "$PROJECT_ROOT/.env" ]; then
  echo "ERROR: no .env at $PROJECT_ROOT" >&2
  echo "       cp .env.example .env && chmod 600 .env, then fill it in." >&2
  exit 1
fi

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: docker not found. Install Docker Desktop first." >&2
  exit 1
}

chmod +x "$PROJECT_ROOT/scripts/macos/agentctl.sh"
mkdir -p "$TARGET_DIR" "$PROJECT_ROOT/logs"

# ── Render ────────────────────────────────────────────────────
# '|' as the sed delimiter because the substituted values are paths.
echo "==> Rendering $LABEL.plist"
sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
    -e "s|{{HOME}}|$HOME|g" \
    "$TEMPLATE" > "$TARGET"

# Catch templating mistakes before launchd rejects the file with a vague error.
if ! plutil -lint "$TARGET" >/dev/null; then
  echo "ERROR: rendered plist is not valid; leaving it at $TARGET for inspection" >&2
  exit 1
fi

if grep -q '{{' "$TARGET"; then
  echo "ERROR: unsubstituted placeholders remain in $TARGET:" >&2
  grep -o '{{[A-Z_]*}}' "$TARGET" | sort -u >&2
  exit 1
fi

# ── Load ──────────────────────────────────────────────────────
echo "==> Loading into launchd"
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true   # idempotent reinstall
launchctl bootstrap "$DOMAIN" "$TARGET"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

echo
echo "Installed: $TARGET"
echo
echo "  Status : ./scripts/macos/agentctl.sh status"
echo "  Logs   : tail -f logs/agentfactory.log"
echo "  Restart: launchctl kickstart -k $DOMAIN/$LABEL"
echo "  Remove : ./scripts/macos/install-service.sh --uninstall"
echo
echo "The stack now starts at login and restarts if it crashes."
echo "Docker Desktop must be set to start at login too:"
echo "  Docker Desktop > Settings > General > Start Docker Desktop when you sign in"
