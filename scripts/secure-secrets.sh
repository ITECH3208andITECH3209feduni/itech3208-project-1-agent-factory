#!/usr/bin/env bash
# scripts/secure-secrets.sh — lock down local secret files (PROJ-319..323)
#
#   ./scripts/secure-secrets.sh            fix permissions, then audit
#   ./scripts/secure-secrets.sh --verify   check only, change nothing
#
# Run after creating or editing .env. Exits non-zero if anything is wrong,
# so it can gate CI.

set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
cd "$PROJECT_ROOT"

VERIFY_ONLY=0
[ "${1:-}" = "--verify" ] && VERIFY_ONLY=1

PROBLEMS=0
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

# Files that hold live credentials on this machine.
SECRET_FILES=(.env .env.local)

IS_WINDOWS=0
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 ;;
esac

bold "Securing local secrets — $PROJECT_ROOT"
echo

# ── 1. Permissions ────────────────────────────────────────────
bold "1. File permissions (0600)"
if [ "$IS_WINDOWS" -eq 1 ]; then
  echo "   SKIP  Windows — POSIX mode bits are not enforced. On this machine,"
  echo "         rely on the user profile ACL instead. The Mac deployment is"
  echo "         where 0600 actually matters."
else
  for f in "${SECRET_FILES[@]}"; do
    [ -f "$f" ] || continue
    MODE=$(stat -f '%Lp' "$f" 2>/dev/null || stat -c '%a' "$f" 2>/dev/null)
    if [ "$MODE" = "600" ]; then
      green "   OK    $f is 0600"
    elif [ "$VERIFY_ONLY" -eq 1 ]; then
      red   "   FAIL  $f is 0$MODE, expected 0600"
      PROBLEMS=$((PROBLEMS + 1))
    else
      chmod 600 "$f"
      green "   FIXED $f 0$MODE -> 0600"
    fi
  done
fi
echo

# ── 2. Git must not be tracking them ──────────────────────────
bold "2. Not tracked by git"
for f in "${SECRET_FILES[@]}"; do
  [ -f "$f" ] || continue
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    red "   FAIL  $f is tracked. Remove it from the index:"
    red "           git rm --cached $f"
    PROBLEMS=$((PROBLEMS + 1))
  elif git check-ignore -q "$f"; then
    green "   OK    $f is ignored"
  else
    red "   FAIL  $f is neither tracked nor ignored — one `git add .` from disaster"
    PROBLEMS=$((PROBLEMS + 1))
  fi
done
echo

# ── 3. Required values present ────────────────────────────────
bold "3. Secrets populated"
if [ -f .env ]; then
  for key in ANTHROPIC_API_KEY BOT_TOKEN GOOGLE_CALENDAR_CREDENTIALS; do
    value="$(grep -E "^${key}=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
    if [ -z "$value" ]; then
      echo "   ----  $key is empty (feature disabled)"
    elif [[ "$value" == *"your-"* || "$value" == *"..."* || "$value" == "sk-ant-..." ]]; then
      red "   FAIL  $key still holds a placeholder"
      PROBLEMS=$((PROBLEMS + 1))
    else
      green "   OK    $key is set"
    fi
  done
else
  red "   FAIL  no .env — cp .env.example .env"
  PROBLEMS=$((PROBLEMS + 1))
fi
echo

# ── 4. History audit ──────────────────────────────────────────
bold "4. Repository history"
if [ -x ./scripts/audit_secrets.sh ]; then
  if ./scripts/audit_secrets.sh >/dev/null 2>&1; then
    green "   OK    audit_secrets.sh passed"
  else
    red   "   FAIL  audit_secrets.sh reported issues — run it directly for detail"
    PROBLEMS=$((PROBLEMS + 1))
  fi
else
  red "   FAIL  scripts/audit_secrets.sh missing or not executable"
  PROBLEMS=$((PROBLEMS + 1))
fi
echo

# ── Result ────────────────────────────────────────────────────
if [ "$PROBLEMS" -eq 0 ]; then
  green "PASS — local secrets are secured"
  exit 0
fi
red "FAIL — $PROBLEMS issue(s). See docs/SECRETS.md"
exit 1
