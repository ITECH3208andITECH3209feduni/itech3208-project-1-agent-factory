# ADR-001: Authentication Consolidation

- **Ticket:** PROJ-461 (epic PROJ-455)
- **Status:** Proposed — awaiting team sign-off
- **Date:** 2026-10-09
- **Author:** Dhiman Roy
- **Supersedes:** open item from PR #20 and both sprint retrospectives

## Context

Two authentication models exist in the repository, built in different
sprints and never reconciled. Neither is merged into `main`.

**Model A — API key** (`origin/proj-113-api-auth`, 594 lines)

- `api/` package: own FastAPI app, routes for `/api/literature` and
  `/api/amazon`
- One shared key read from `API_KEY` in the environment
- Accepted via `X-API-Key` header or `?api_key=` query parameter
- Fails closed when `API_KEY` is unset
- Tests in `tests/api/` — 3 files

**Model B — JWT** (`origin/proj-170-source-fallback`, ~3000 lines)

- `auth/` package mounted on the existing web app
- Per-user accounts, bcrypt password hashing
- 15-minute access tokens, 7-day refresh tokens with rotation
- Organisations and tenant isolation (PROJ-405, PROJ-410)
- Password recovery, per-user encrypted API keys, consent model
- 146 passing tests including org isolation and consent edge cases

## Decision

**Model B (JWT) survives. Model A is retired.**

## Why

**Model A cannot express a user.** It authenticates a caller, not a
person. There is one key for the whole server, so there is no user id
to scope by. Everything built in PROJ-392 and PROJ-393 — organisations,
tenant isolation, consent per contact, audit trails naming the acting
user — depends on knowing *who* is calling. Model A has nowhere to put
that. Keeping it would mean rebuilding all of it.

**Model A cannot revoke one user.** The key is shared, so removing
access for one person means rotating the key for everyone. Model B
revokes a single refresh token, and a password reset kills every
session for that user alone.

**The query-parameter option is a liability.** `?api_key=...` puts a
live credential into server logs, browser history, and the Referer
header of any outbound link. That is convenient for curl and wrong for
a credential.

**Volume of dependent work.** Twelve tickets across two epics are built
on Model B. Model A has two endpoints. Migrating the other way is not
a realistic amount of work before the deadline.

## What Model A does better

This is not a one-sided comparison, and the record should say so.

**Machine-to-machine access.** A script or a scheduled job has no
browser and no human to log in. Model A handles that in one header;
Model B requires a user account and a token refresh cycle. We have no
replacement for this today.

**Simplicity.** 68 lines versus roughly 3000. Model A is auditable in
one sitting.

**Fail-closed by default.** An unset `API_KEY` rejects every request.
Model B's `JWT_SECRET_KEY` does raise at startup, which is equivalent,
but Model A got there first and more simply.

If service accounts are needed later, the right answer is a
*scoped, per-org, revocable* key issued through Model B — not a return
to one shared secret. The `auth/api_keys.py` work from PROJ-344 is
already most of the way there.

## Consequences

- `api/` and `tests/api/` are removed (PROJ-463)
- `/api/literature` and `/api/amazon` are retired; equivalent
  functionality exists at `/literature` and `/query` on the web app
- Any caller using `X-API-Key` breaks and must move to JWT (PROJ-462)
- Machine-to-machine access is unsupported until service-account keys
  are built — **this is a known gap, not an oversight**
- A regression suite must exist before the deletion lands (PROJ-464)

## Open questions for the team

1. **Does anything outside the repo call `/api/*`?** If a teammate's
   script or a marking rubric uses those endpoints, deleting them
   breaks something we can't see from here.
2. **Is a service account needed this sprint?** If yes, scope it now
   rather than discovering the gap after deletion.
3. **Ordering of PROJ-463 and PROJ-464.** The tickets are numbered
   delete-then-test. Writing the regression suite first gives a safety
   net during deletion. Recommend swapping them.
4. **Neither model is on `main`.** Both branches are unmerged.
   Consolidation should end with the surviving model merged, or the
   decision only exists on paper.

## Sign-off

| Name | Role | Agreed | Date |
|---|---|---|---|
| Dhiman Roy | Author | Yes | 2026-10-09 |
| Dilraj Singh | | | |
| | | | |