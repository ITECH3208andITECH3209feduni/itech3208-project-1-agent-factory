<!-- ITECH3208 Agent Factory — PR template (PROJ-452) -->

## Jira ticket

<!-- e.g. PROJ-418. Put the key in the PR title too, so the board links up. -->
PROJ-

## What changed

<!-- What a reviewer needs to know to review this, not a restatement of the diff. -->

## Why

<!-- If the ticket already explains it, one line is enough. If you deviated from
     what the ticket asked for, say so here and why — that is the most useful
     thing in this template. -->

## Type of change

- [ ] Feature — new functionality
- [ ] Fix — bug or security fix
- [ ] Refactor / simplification — no behaviour change
- [ ] Infrastructure — Docker, CI, deployment, scripts
- [ ] Documentation only
- [ ] Tests only

## How this was verified

<!-- Be specific. "Tested locally" tells a reviewer nothing.
     Good: "./run.sh test — 208 checks pass. Hit POST /query with a literature
     query, got 10 results in 8s."
     If you could not verify something, say which part and why. -->

- [ ] `./run.sh test` passes locally
- [ ] I ran the affected feature and confirmed the actual behaviour
- [ ] CI is green (or the failures are explained below)

## Checklist

- [ ] No secrets, tokens, or credentials in the diff — `./scripts/audit_secrets.sh --staged`
- [ ] New environment variables are documented in `.env.example` **and** read in `config/settings.py`
- [ ] New or changed behaviour has a test
- [ ] Docs updated if setup, deployment, or architecture changed
- [ ] Depends on another ticket? Named below, and it has landed

## Dependencies / blocked by

<!-- Sprint 4 has real cross-owner dependencies. If this needs Dhiman's data
     contract (PROJ-404) or Dilraj's reminders store (PROJ-422), say so — do not
     build against a guessed schema and leave the reviewer to discover it. -->

None

## Anything a reviewer should look at closely

<!-- Known rough edges, decisions you were unsure about, things you want pushed
     back on. Cheaper to raise here than to discover in production. -->
