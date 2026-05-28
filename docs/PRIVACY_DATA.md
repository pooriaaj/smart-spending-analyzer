# Privacy And Data Lifecycle Runbook

Use this runbook before handling user data, account deletion, future data export work, or any AI/Codex task that might involve real financial records. It is intentionally policy and process only. It does not approve production database writes, production exports, migrations, or destructive actions.

## Current State

- Account deletion exists through the profile page and `DELETE /users/me`.
- Account deletion requires the current password.
- The backend deletes the current `User` row and relies on SQLAlchemy/database cascades for user-owned rows.
- A self-serve full user data export endpoint does not exist yet.
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

- No self-serve full data export endpoint exists.
- No formal privacy policy document exists.
- No written retention schedule exists for logs, backups, or exported data.
- No admin/user support workflow exists for data subject requests.
- No automated test proves that account deletion removes every user-owned row.
- Shared merchant lookup cache behavior should be documented before promising deletion semantics for learned community data.

## Manual Data Request Rules

Until a full export/delete workflow is implemented:

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
- [ ] Add a self-serve user data export endpoint or a documented support workflow.
- [ ] Add tests for account deletion cascades.
- [ ] Decide and document backup retention.
- [ ] Decide and document log retention.
- [ ] Decide and document third-party AI/provider data use.
- [ ] Verify community learning language matches implementation.
- [ ] Verify account deletion and data export behavior in staging before advertising it.

## Future Self-Serve Export Plan

Proposed implementation, not approved yet:

- Files likely changed: `backend/app/routes/user_routes.py`, `backend/app/schemas.py`, `backend/app/services/user_export_service.py`, backend tests, frontend profile page, i18n copy, and docs.
- Risk level: medium, because it handles sensitive user financial data.
- Touches database: read-only queries for the authenticated current user.
- Free tools: yes.
- Guardrails: authenticated current user only, password confirmation or recent auth check, JSON download, no secrets, no password hashes, no reset token hashes, tests for cross-user isolation.
- Exact approval question: "Do you approve adding a self-serve user data export endpoint and frontend download flow for the authenticated current user only, with tests, no production export by Codex, and no deletion behavior changes?"
