# Agent Factory changelog

Release notes for the Agent Factory application (ITECH3208). The root
`CHANGELOG.md` tracks the upstream NanoClaw project and is separate.

## [0.4.0] - Sprint 4: Reminder & Communication Service

### Added
- **Delivery channels** (PROJ-396): SMS, voice and email behind one interface, with exponential backoff and retriable / non-retriable failure classification.
- **Reminders engine** (PROJ-395): SQLite-backed scheduler with atomic claiming (no double sends), stale-claim recovery, DST-safe recurrence, and edit / pause / resume / cancel.
- **Booking tie-in** (PROJ-402): a confirmed receptionist booking schedules a reminder automatically.
- **Accounts and multi-tenancy** (PROJ-392): org and user schema, registration, login, password recovery, and org scoping on every query.
- **Consent and privacy** (PROJ-393): per-contact consent state, append-only audit trail, automatic STOP handling, and a hard send block for contacts who have not opted in.
- **Contacts CRM** (PROJ-394): CRUD and CSV bulk import on the org-scoped contacts table.
- **Dashboard and notification preferences** (PROJ-399, PROJ-400): reminder list and create / edit views, per-contact channel preferences.
- **Delivery status, history and analytics** (PROJ-397, PROJ-398): Twilio status callbacks, email bounce handling, per-reminder history, delivery and response rate charts.
- **Interface personalisation** (PROJ-401): per-user theme, colour and widget layout.
- **Information website** (PROJ-403): static site and FAQ, deployed via GitHub Pages.
- **Web reminder bridge**: reminders created in the dashboard are now actually sent by the reminders engine.
- **Process tooling** (PROJ-452): CI triggers, CODEOWNERS and PR template.

### Changed
- The live Twilio SMS and voice webhooks now route to the Receptionist, so real callers reach FAQ lookup, escalation and booking.
- Contacts moved from a JSON store to the org-scoped SQLite table; the organisation-profile endpoints (PROJ-409) run on the live session login.
- The web Docker image now includes `auth/`, `contracts/` and `integrations/`.

### Fixed
- `/status` health check was returning 401 because its handler had been dropped; it is public again, with a regression test.
- Live-Claude tests skip when only the test placeholder API key is present.

### Known issues
- Two login models (session and token) still coexist; consolidation is tracked in PROJ-455.
- Production hosting is not yet in place; webhooks still rely on a tunnel (PROJ-456).
