# Privacy And Data Lifecycle Runbook

Use this runbook before handling user data, account deletion, future data export work, or any AI/Codex task that might involve real financial records. It is intentionally policy and process only. It does not approve production database writes, production exports, migrations, or destructive actions.

## Current State

- Account deletion exists through the profile page and `DELETE /users/me`.
- Account deletion requires the current password.
- The backend deletes the current `User` row and relies on SQLAlchemy/database cascades for user-owned rows.
- Self-serve user data export exists through the profile page and `POST /users/me/export`.
- Data export requires the current password and returns a JSON download for the authenticated current user only.
- Data export omits password hashes, reset token hashes, reset token expiry timestamps, shared merchant lookup cache rows, provider logs, and backups.
- Assistant training export exists for assistant learning examples only; it is not a full account export.
- Backups and provider logs may retain deleted data for a limited retention window.

## Data Inventory

The current SQLAlchemy models show these main data groups:

- User identity: email, password hash, password change timestamp, reset token hash, reset token expiry.
- Accounts: account name, type, active state, owner.
- Transactions: amount, category, description, date, type, account, import metadata, categorization confidence/source/reason.
- Category learning: personal category memories, merchant category profiles, category learning events, user learning preferences.
- Assistant data: chat messages, usage events, learning examples, model/provider usage metadata.
- Merchant enrichment cache: shared merchant lookup cache keyed by merchant and transaction type.
- Budgets and planning: budget plans and saved simulator scenarios.

The transaction model stores import metadata such as file name, file type, and import time. This inspection did not find a database model for storing original uploaded CSV or PDF files.

## Third-Party Data Paths

Depending on environment settings, these services can receive some user or app data:

- Render: backend runtime, logs, and PostgreSQL database.
- Vercel: frontend hosting, browser delivery, and deployment logs.
- Email provider or SMTP server: password reset delivery metadata and email content.
- OpenAI or OpenAI-compatible provider: assistant requests and optional vision OCR when enabled.
- Google Places API: merchant enrichment requests when enabled.
- GitHub Actions: public smoke checks and CI logs.

Before adding any new vendor that can receive user data, document what is sent, why it is needed, and how to disable it.

## Account Deletion Expectations

Current behavior:

- The user must be authenticated.
- The user must provide the current password.
- The backend deletes the current user and commits the change.
- The auth cookie is cleared after the delete succeeds.
- User-owned tables are expected to cascade through model relationships and foreign keys.

Do not promise instant deletion from:

- Database backups.
- Provider logs.
- Email provider logs.
- Third-party AI/provider logs.
- Local developer exports or screenshots.

Those locations must age out through their own retention policies or be handled through provider-specific deletion processes.

## Current Privacy Gaps

- `docs/PRIVACY_NOTICE_DRAFT.md` exists, but it is not legal-approved public policy.
- `docs/RETENTION.md` exists, but provider-specific production retention values still need confirmation.
- No admin/user support workflow exists for data subject requests.
- Self-serve data export covers app-owned database rows, but does not cover provider logs, backups, email provider records, or third-party AI/provider records.
- Backend tests cover account deletion cleanup for core user-owned models; keep this coverage updated when new user-owned tables are added.
- Backend tests cover export password validation, current-user row scoping, and sensitive field exclusion; keep this coverage updated when new user-owned tables are added.
- Shared merchant lookup cache behavior should be documented before promising deletion semantics for learned community data.

## Manual Data Request Rules

For any manual data request beyond the self-serve export:

- Do not export production user data from Codex without explicit approval.
- Do not paste real transactions, statements, emails, passwords, reset links, tokens, or API responses into AI prompts.
- Do not email raw exports.
- Do not commit exports to git.
- Do not store exports inside the repo.
- Prefer a test account or staging account for support and QA.
- If a production export is unavoidable, document who approved it, what was exported, where it was stored, and when it was deleted.
- Use encrypted storage for temporary exports whenever possible.

## Community Learning Notes

The profile page includes a community learning preference. Treat this carefully:

- Personal learning can still exist when community learning is disabled.
- Disabling community learning should stop future contribution to shared learning.
- Do not describe community learning as anonymous unless the exact data path has been reviewed.
- Do not use real user transaction descriptions in docs, examples, screenshots, or tests.

## Backup And Restore Privacy

- Backups are sensitive user data.
- Keep backup files out of git.
- Store local backups under ignored paths such as `local-backups/` or `backups/`.
- Test restores on local or staging only unless production restore is explicitly approved.
- If an account was deleted after a backup was taken, restoring that backup can reintroduce deleted data.
- Before restoring any production backup, create a specific restore plan that addresses deleted accounts and newer user activity.

See `docs/BACKUP_RESTORE.md` for backup and restore mechanics.

## AI And Codex Handling

- Never ask Codex to inspect real `.env` values.
- Never paste production database URLs, JWT secrets, API keys, tokens, or passwords.
- Never paste real bank statement content unless the user explicitly approves a sanitized excerpt.
- Prefer synthetic examples in docs and tests.
- Ask for approval before changing auth, security, database models, migrations, deletion behavior, or export behavior.

## Pre-Launch Privacy Checklist

- [ ] Publish a plain-language privacy policy.
- [ ] Turn `docs/PRIVACY_NOTICE_DRAFT.md` into a reviewed public privacy policy before broad launch.
- [ ] Confirm `docs/RETENTION.md` against actual provider settings before broad launch.
- [ ] Verify self-serve user data export in staging before advertising it broadly.
- [ ] Keep account deletion cascade tests current when new user-owned models are added.
- [ ] Keep data export tests current when new user-owned models are added.
- [ ] Decide and document backup retention.
- [ ] Decide and document log retention.
- [ ] Decide and document third-party AI/provider data use.
- [ ] Verify community learning language matches implementation.
- [ ] Verify account deletion and data export behavior in staging before advertising it.

## Future Export Hardening Plan

Proposed follow-up, not approved yet:

- Files likely changed: backend tests, frontend tests, `docs/PRIVACY_DATA.md`, and possibly the export service if new user-owned models are added.
- Risk level: low to medium, because it verifies sensitive user financial data handling.
- Touches database: local/test databases only.
- Free tools: yes.
- Guardrails: authenticated current user only, password confirmation, JSON download, no secrets, no password hashes, no reset token hashes, tests for cross-user isolation.
- Exact approval question: "Do you approve tightening the user data export coverage with additional tests and documentation only, without changing production data or deletion behavior?"
