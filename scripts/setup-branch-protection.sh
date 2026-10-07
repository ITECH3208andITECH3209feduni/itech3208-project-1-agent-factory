#!/usr/bin/env bash
# scripts/setup-branch-protection.sh — apply branch protection (PROJ-452)
#
#   ./scripts/setup-branch-protection.sh            # apply to master
#   ./scripts/setup-branch-protection.sh main       # apply to another branch
#   ./scripts/setup-branch-protection.sh --show     # print current rules
#
# Branch protection lives in GitHub's settings, not in the repo, so it cannot
# be committed. This script applies it via the API so the configuration is at
# least reviewable and repeatable instead of a description of some clicks.
#
# Requires: gh CLI, authenticated, with admin rights on the repo.
#   brew install gh    (or: winget install GitHub.cli)
#   gh auth login
#
# If you do not have admin, docs/WORKFLOW.md has the equivalent UI checklist.

set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"
cd "$PROJECT_ROOT"

SHOW_ONLY=0
BRANCH="master"
case "${1:-}" in
  --show) SHOW_ONLY=1 ;;
  "")     ;;
  -*)     echo "usage: $0 [branch|--show]" >&2; exit 2 ;;
  *)      BRANCH="$1" ;;
esac

# ── Preflight ─────────────────────────────────────────────────
if ! command -v gh >/dev/null 2>&1; then
  cat >&2 <<'EOF'
ERROR: gh CLI not found.

  macOS:    brew install gh
  Windows:  winget install GitHub.cli
  then:     gh auth login

Or apply the rules by hand — see docs/WORKFLOW.md.
EOF
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated. Run: gh auth login" >&2
  exit 1
fi

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)"
if [ -z "$REPO" ]; then
  echo "ERROR: could not determine the repo. Is origin a GitHub remote?" >&2
  exit 1
fi

echo "Repo:   $REPO"
echo "Branch: $BRANCH"
echo

if [ "$SHOW_ONLY" -eq 1 ]; then
  gh api "repos/$REPO/branches/$BRANCH/protection" 2>/dev/null \
    || echo "(no protection configured, or you lack admin rights to read it)"
  exit 0
fi

# ── Confirm ───────────────────────────────────────────────────
# Outward-facing and affects everyone's ability to push, so never silent.
cat <<EOF
About to apply to $REPO ($BRANCH):

  - Require a pull request before merging
  - Require 1 approving review
  - Dismiss stale approvals when new commits are pushed
  - Require status checks to pass: "Python tests", "Secrets audit"
  - Require branches to be up to date before merging
  - Require conversation resolution before merging
  - Block force pushes
  - Block branch deletion
  - Enforce all of the above for admins too

NOT enabled: "Require review from Code Owners".
.github/CODEOWNERS still has TODO placeholders for three teammates, and
GitHub silently ignores rules naming unknown users — so the setting would
look active while enforcing nothing. Turn it on once the handles are filled.

EOF
read -r -p "Proceed? [y/N] " reply < /dev/tty || reply="n"
case "$reply" in
  y|Y|yes|YES) ;;
  *) echo "Aborted."; exit 0 ;;
esac

# ── Apply ─────────────────────────────────────────────────────
# The contexts must match the `name:` of the CI jobs exactly, or the check
# never reports and every PR waits forever on something that cannot arrive.
PAYLOAD=$(cat <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Python tests", "Secrets audit"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true,
  "required_linear_history": false,
  "block_creations": false
}
JSON
)

echo
echo "Applying..."
if echo "$PAYLOAD" | gh api -X PUT "repos/$REPO/branches/$BRANCH/protection" \
     -H "Accept: application/vnd.github+json" --input - >/dev/null; then
  echo "Applied to $BRANCH."
  echo
  echo "Verify: $0 --show"
  echo "Note: 'Node checks' is deliberately not required — it is"
  echo "      continue-on-error until confirmed green. See docs/WORKFLOW.md."
else
  echo >&2
  echo "FAILED. Most likely causes:" >&2
  echo "  - you are not an admin on $REPO" >&2
  echo "  - branch '$BRANCH' does not exist on the remote" >&2
  echo "  - the repo is on a plan without protection for private repos" >&2
  echo >&2
  echo "Apply by hand instead — docs/WORKFLOW.md has the checklist." >&2
  exit 1
fi
