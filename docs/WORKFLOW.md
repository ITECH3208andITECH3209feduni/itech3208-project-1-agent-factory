# Development Workflow & Quality Standards

Branching, review, and CI for the team (PROJ-452 — client's item #8).

---

## 1. Branching

```
master                    integration branch — all team work lands here
  └─ feat/PROJ-418-contacts-crud
  └─ fix/PROJ-441-consent-check
  └─ docs/PROJ-452-workflow
```

Name branches `<type>/PROJ-<n>-<short-slug>`. The ticket key in the branch and
the PR title is what links the work to the board.

Types: `feat`, `fix`, `refactor`, `infra`, `docs`, `test`.

### A note on `master` vs `main`

The remote has **both**, and `origin/HEAD` points at `main` while every commit
the team has made is on `master`. That split is why CI never ran before
PROJ-452 — `ci.yml` only listened for PRs to `main`.

CI now listens to both. Longer term the team should pick one and delete the
other; until then, **target `master`**.

---

## 2. Pull requests

One ticket, one PR, where practical. A PR spanning five tickets cannot be
reviewed meaningfully or reverted cleanly.

`.github/PULL_REQUEST_TEMPLATE.md` fills in automatically. Two sections earn
their keep:

- **How this was verified** — "tested locally" tells a reviewer nothing. Say
  what you ran and what you saw. If you could not verify part of it, say which
  part and why. Sprint 3 shipped a Dockerfile that was never successfully
  built; that was fine *because it was stated*, and would have been a problem
  silently.
- **Dependencies / blocked by** — Sprint 4 has real cross-owner dependencies
  (contacts needs Dhiman's data contract PROJ-404; the reminders list needs
  Dilraj's store PROJ-422). Name them rather than building against a guessed
  schema.

### Review expectations

- **1 approval** to merge.
- Reviewer looks for: does it do what the ticket asked; is it tested; does it
  leak secrets; does it break someone else's contract.
- Approving without running anything is not a review. If you cannot verify it,
  say so in the review.
- Author does not merge their own PR without an approval, including the lead.

---

## 3. CI

`.github/workflows/ci.yml` runs on PRs and pushes to `master` and `main`.

| Job | Blocking | What it does |
|---|---|---|
| **Python tests** | yes | Every `scripts/test_*.py` suite (208 checks) plus the MCP stdio smoke test |
| **Secrets audit** | yes | `scripts/audit_secrets.sh` over full history |
| **Node checks** | **no** | `format:check`, `tsc --noEmit`, `vitest` |

### Why Node is non-blocking

It has never actually run against this branch, so its true state is unknown.
Making it blocking today could wedge every PR on a pre-existing failure nobody
has seen. Once someone confirms it green, remove `continue-on-error` from the
`node` job and add `"Node checks"` to the required contexts.

### Local equivalents

```bash
./run.sh test                       # the Python suites CI runs
./scripts/audit_secrets.sh          # full history audit
./scripts/audit_secrets.sh --staged # what the pre-commit hook runs
./scripts/secure-secrets.sh         # .env permissions + placeholder check
```

The Husky `pre-commit` hook already runs the staged secrets audit, so a
credential is blocked before it becomes a history problem. `--no-verify`
bypasses it; use that only when you are certain it is a false positive.

---

## 4. Branch protection

Protection lives in GitHub settings, not in the repo, so it cannot be
committed. Apply it once:

```bash
./scripts/setup-branch-protection.sh          # master
./scripts/setup-branch-protection.sh --show   # inspect current rules
```

Needs `gh` installed, authenticated, and **admin on the repo**.

### Applying by hand

Settings → Branches → Add branch protection rule, pattern `master`:

- [x] Require a pull request before merging
  - [x] Require approvals: **1**
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [ ] Require review from Code Owners — **leave off for now**, see below
- [x] Require status checks to pass before merging
  - [x] Require branches to be up to date before merging
  - Add: **`Python tests`**, **`Secrets audit`**
- [x] Require conversation resolution before merging
- [x] Do not allow bypassing the above settings *(applies to admins too)*
- [ ] Allow force pushes — **off**
- [ ] Allow deletions — **off**

Repeat for `main` if it stays.

> The status check names must match the CI jobs' `name:` values **exactly**.
> A typo means the check never reports and every PR waits forever on something
> that can never arrive.

### Why Code Owner review is off

`.github/CODEOWNERS` still has `TODO: @handle` placeholders for three
teammates. GitHub **silently ignores** rules naming an unknown user or someone
without repo access — so the setting would appear active while enforcing
nothing. `Require approvals: 1` works regardless.

Fill in the handles, then turn it on.

This also fixed a live hazard: CODEOWNERS previously contained upstream
NanoClaw's maintainers (`@gavrielc`, `@gabi-simons`) on `/src/`, `/container/`,
`/groups/`, `/launchd/`, and `package.json`. With code-owner review enabled,
every PR touching those paths would have required approval from two people
outside this project — locking the team out of its own repo.

---

## 5. Definition of done

A ticket is Done when:

1. Code is merged to `master` via an approved PR
2. CI is green on the merge commit
3. New behaviour has a test, and the suite passes
4. New config is in `.env.example` *and* read in `config/settings.py`
5. Docs reflect any setup, deployment, or architecture change
6. The Jira ticket has a comment naming the commit and stating what was
   verified — **and what was not**
7. The ticket is transitioned in Jira

Point 6 matters. Sprint 3 closed tickets whose Docker image had never been
built; recording that on the ticket is the difference between a known gap and
a nasty surprise on someone else's machine.

---

## 6. Things that bit us before

Kept here so they bite once, not twice.

| Problem | Why it happened | Guard now in place |
|---|---|---|
| CI never ran | `ci.yml` watched `main`, team works on `master` | Watches both |
| 208 Python tests not in CI | CI only ran the Node side | `Python tests` job, blocking |
| `test_web_api` / `test_skills_endpoint` skipped silently | `httpx` missing, suites self-skip on ImportError | `httpx` pinned in `requirements.txt` |
| CODEOWNERS named outsiders | Inherited from the NanoClaw fork | Rewritten; code-owner review off until handles are real |
| Secrets audit flagged our own template | Placeholder filter was case-sensitive | Filter is case-insensitive |
| Compose broke for everyone | `${VAR:?err}` on a profiled service — Compose interpolates the whole file before applying profiles | Use `${VAR:-}`; validate in `agentctl.sh` when the profile is on |
| Windows `python3` "found" but unusable | Microsoft Store stub satisfies `command -v` | `run.sh` test-executes candidates |
| Docker build OOM | 7.3 GB dev machine, Chromium layer | Build on the Mac; Docker Desktop ≥4 GB |
