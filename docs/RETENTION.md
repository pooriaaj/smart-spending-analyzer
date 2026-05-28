# Data Retention Draft

Status: draft operational plan. This is not legal advice and should not be treated as a final compliance schedule.

Last reviewed: 2026-05-28

## Purpose

This document defines beginner-friendly retention targets for Smart Spending Analyzer. The goals are:

- Keep only data the app needs.
- Protect sensitive data while it exists.
- Delete or age out data when it is no longer needed.
- Avoid surprise retention in backups, logs, exports, screenshots, and AI prompts.

## Retention Summary

These are operational targets, not legal promises.

| Data group | Proposed retention | Notes |
| --- | --- | --- |
| Active user profile | Until account deletion | Password hashes are required for login and must never be exported. |
| Password reset token hashes | Until expiry or successful reset cleanup | Tokens are hashed; reset links must not be logged or pasted into AI prompts. |
| Accounts | Until account deletion or user deletes the account row | Account deletion should cascade user-owned rows. |
| Transactions | Until account deletion or user deletes rows | Includes manually entered and imported transaction rows. |
| Import metadata | Until related transaction deletion | File names and import timestamps can be sensitive. |
| Original uploaded files | Not currently expected to be stored | Reconfirm before public launch. |
| Personal category memory | Until account deletion or feature-specific cleanup | Used for personal categorization. |
| Community learning signals | Until account deletion or learning cleanup | Shared cache behavior needs careful wording before public promises. |
| Assistant chat messages | Until account deletion or user clears history | Treat as sensitive financial context. |
| Assistant usage events | Until account deletion or future cleanup policy | Used for usage limits and diagnostics. |
| Assistant learning examples | Until account deletion or user clears training examples | Export endpoint includes user-owned rows. |
| Budgets and saved scenarios | Until account deletion or user deletion | User-owned planning data. |
| Self-serve export files | User-controlled after download | The app creates the browser download; the user controls the file afterward. |
| Manual local exports | Delete as soon as the support task ends | Must stay outside git and preferably encrypted. |
| Local backups | Keep only as long as needed for migration/restore work | Must stay under ignored paths such as `local-backups/` or `backups/`. |
| Production database backups | Provider or manual backup retention | Confirm in Render before relying on or promising a duration. |
| Render logs | Provider retention | Confirm current Render retention in the dashboard/docs before publishing. |
| Vercel logs | Provider retention | Confirm current Vercel retention in the dashboard/docs before publishing. |
| GitHub Actions logs | Provider retention | Avoid printing secrets or user data in workflow logs. |
| Email provider logs | Provider retention | Password reset email metadata may exist outside the app. |
| AI/provider logs | Provider retention | Only enabled when configured; do not paste real user data into prompts outside approved flows. |

## Deletion Events

### User Deletes A Transaction

- The transaction row should be deleted from the app database.
- Analytics should update after deletion.
- Existing backups or provider logs may retain historical traces until they expire.

### User Clears Assistant History

- Assistant chat rows for the selected scope should be deleted according to the implemented endpoint behavior.
- Assistant usage events and learning examples are separate data groups and should not be described as deleted unless explicitly cleared.

### User Clears Assistant Training Examples

- Assistant learning examples should be deleted according to the implemented endpoint behavior.
- Assistant chat history is separate and should not be described as deleted unless explicitly cleared.

### User Deletes Their Account

- The backend deletes the current user and commits the change.
- Core user-owned rows are expected to cascade and are covered by backend tests.
- The auth cookie is cleared after successful deletion.
- Deleted data can still exist in backups, provider logs, email provider logs, AI/provider logs, local exports, screenshots, or downloaded files until those systems age out or are handled separately.

## Backup Retention Rules

- Treat every backup as sensitive user data.
- Keep backups outside git.
- Store local backups only under ignored paths.
- Delete local backups after the migration, restore test, or support task is complete.
- Before a production restore, write a restore plan that handles deleted accounts and newer production activity.
- Never restore over production without explicit approval.

See `docs/BACKUP_RESTORE.md`.

## Log Retention Rules

- Do not log secrets.
- Do not log reset tokens.
- Do not log raw statement content.
- Do not log full user exports.
- Avoid logging full transaction descriptions where possible.
- Confirm provider retention before publishing a final privacy policy.

## Manual Export Rules

- Prefer self-serve export from the profile page.
- Do not use Codex to export production data without explicit approval.
- Do not email raw exports.
- Do not commit exports.
- Do not store exports in the repo.
- Delete support exports after the support task is complete.
- Record the deletion date in a private operational note if a real export was created.

## Review Schedule

Review this document:

- Before public launch.
- Before adding a new user-owned model.
- Before adding a new vendor.
- Before changing account deletion behavior.
- Before changing backup or restore workflows.
- After any privacy/security incident.

## Open Decisions

- [ ] Final production backup retention target.
- [ ] Final production log retention target.
- [ ] Final third-party AI/provider data-use statement.
- [ ] Whether community learning cache rows need their own retention/deletion workflow.
- [ ] Whether to add scheduled cleanup for expired reset token hashes.
- [ ] Whether to add scheduled cleanup for old assistant usage events.
- [ ] Whether to add user-facing deletion/export help text outside the profile page.
