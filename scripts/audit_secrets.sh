#!/usr/bin/env bash
# scripts/audit_secrets.sh — Secrets audit (PROJ-381, PROJ-319..323)
#
# Confirms no plaintext secret has ever been committed, and that the files
# holding secrets today are ignored and locked down.
#
# Usage:
#   ./scripts/audit_secrets.sh              # audit full history
#   ./scripts/audit_secrets.sh --staged     # pre-commit: staged changes only
#
# Exits non-zero if anything is found, so it can gate CI or a git hook.

set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
cd "$PROJECT_ROOT"

STAGED_ONLY=0
[ "${1:-}" = "--staged" ] && STAGED_ONLY=1

FINDINGS=0

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

# Live credential shapes. Deliberately specific — matching on the word
# "token" or "key" alone produces so much noise the check gets ignored,
# which is worse than not having it.
PATTERNS='sk-ant-api[0-9]{2}-[A-Za-z0-9_-]{20,}'      # Anthropic
PATTERNS+='|sk-[A-Za-z0-9]{40,}'                       # generic OpenAI-style
PATTERNS+='|AKIA[0-9A-Z]{16}'                          # AWS access key id
PATTERNS+='|ghp_[A-Za-z0-9]{30,}'                      # GitHub PAT (classic)
PATTERNS+='|github_pat_[A-Za-z0-9_]{30,}'              # GitHub PAT (fine-grained)
PATTERNS+='|xox[baprs]-[A-Za-z0-9-]{10,}'              # Slack
PATTERNS+='|[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}'          # Telegram bot token
PATTERNS+='|-----BEGIN [A-Z ]*PRIVATE KEY-----'        # PEM private key
PATTERNS+='|"private_key_id"[[:space:]]*:'             # GCP service account JSON

# Placeholders in templates, docs, and test fixtures match the shapes above
# but are not secrets. Filtering them is what keeps this check credible —
# an audit that reports .env.example every run is an audit nobody reads.
PLACEHOLDERS='your-|your_|-here|<[a-z_]*>|example|EXAMPLE|placeholder|PLACEHOLDER'
PLACEHOLDERS+='|dummy|DUMMY|fake|FAKE|test-token|test_token|TEST_TOKEN|sample|SAMPLE'
PLACEHOLDERS+='|changeme|CHANGEME|xxxx|XXXX|\.\.\.|redacted|REDACTED|TODO'

drop_placeholders() { grep -Ev "$PLACEHOLDERS" || true; }

bold "Secrets audit — $PROJECT_ROOT"
echo

# ── 1. Secret-bearing files must not be tracked ───────────────
bold "1. Secret files not tracked"
for f in .env .env.local secrets.json credentials.json; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    red "   FAIL  $f is tracked by git"
    FINDINGS=$((FINDINGS + 1))
  fi
done
[ "$FINDINGS" -eq 0 ] && green "   OK    no secret-bearing files tracked"
echo

# ── 2. ...and never were ──────────────────────────────────────
if [ "$STAGED_ONLY" -eq 0 ]; then
  bold "2. Secret files never committed historically"
  # .env.example / .env.sample / .env.template are templates and belong in git.
  EVER=$(git log --all --pretty=format: --name-only --diff-filter=A 2>/dev/null \
         | sort -u \
         | grep -Ex '\.env|\.env\..*|secrets\.json|credentials\.json' \
         | grep -Ev '\.env\.(example|sample|template)$' || true)
  if [ -n "$EVER" ]; then
    red "   FAIL  these were committed at some point:"
    echo "$EVER" | sed 's/^/         /'
    FINDINGS=$((FINDINGS + 1))
  else
    green "   OK    never committed"
  fi
  echo
fi

# ── 3. No live credentials in the diff history ────────────────
if [ "$STAGED_ONLY" -eq 1 ]; then
  bold "3. No live credentials in staged changes"
  HITS=$(git diff --cached -U0 --no-color | grep -E '^\+' | grep -EI "$PATTERNS" | drop_placeholders)
else
  COUNT=$(git rev-list --all --count)
  bold "3. No live credentials across all $COUNT commits"
  HITS=$(git log --all -p --no-color 2>/dev/null | grep -E '^\+' | grep -EI "$PATTERNS" | drop_placeholders)
fi

if [ -n "$HITS" ]; then
  red "   FAIL  possible credentials found:"
  # Truncate each hit — never print a full secret into a CI log.
  echo "$HITS" | head -20 | cut -c1-60 | sed 's/^/         /;s/$/.../'
  FINDINGS=$((FINDINGS + 1))
else
  green "   OK    none found"
fi
echo

# ── 4. .gitignore actually covers .env ────────────────────────
bold "4. .gitignore covers .env"
if git check-ignore -q .env 2>/dev/null || grep -qE '^\.env$|^\*\.env$' .gitignore; then
  green "   OK    .env is ignored"
else
  red "   FAIL  .env is not ignored by .gitignore"
  FINDINGS=$((FINDINGS + 1))
fi
echo

# ── 5. Local .env permissions (POSIX only) ────────────────────
bold "5. Local .env permissions"
if [ ! -f .env ]; then
  echo "   SKIP  no .env in this checkout"
elif [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
  echo "   SKIP  Windows — POSIX mode bits are not enforced here"
else
  MODE=$(stat -f '%Lp' .env 2>/dev/null || stat -c '%a' .env 2>/dev/null)
  if [ "$MODE" = "600" ]; then
    green "   OK    .env is 0600"
  else
    red "   WARN  .env is 0$MODE, expected 0600 — run: chmod 600 .env"
    FINDINGS=$((FINDINGS + 1))
  fi
fi
echo

# ── Result ────────────────────────────────────────────────────
if [ "$FINDINGS" -eq 0 ]; then
  green "PASS — no secrets exposure found"
  exit 0
fi
red "FAIL — $FINDINGS issue(s) found"
echo
echo "If a real secret was committed, rotating it is the only fix that counts."
echo "Removing it from history does not help once it has been pushed."
exit 1
