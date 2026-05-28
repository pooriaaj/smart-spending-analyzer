# Operations Calendar

Status: solo-maintainer routine for beta/early production. Adjust as the app gets more users.

Last reviewed: 2026-05-28

## Purpose

This calendar turns the runbooks into a simple routine. It is designed for a solo developer using free or feasible tools, without over-building a company process too early.

Use this to keep Smart Spending Analyzer healthy across:

- CI and dependency checks.
- Production smoke tests.
- Render/Vercel logs.
- Backups and restore readiness.
- Security and privacy hygiene.
- Staging and release quality.
- Incident response practice.

## Ground Rules

- Do not inspect or print real secret values.
- Do not edit `.env` files from Codex.
- Do not export production user data unless explicitly approved.
- Do not run production migrations as routine maintenance.
- Do not restore over production.
- Use test accounts for manual QA.
- Keep private operational notes outside git if they involve real incidents, users, vendors, or secrets.

## Daily During Active Development

Time estimate: 5 to 10 minutes.

- [ ] Check `git status --short` before starting work.
- [ ] Check the latest GitHub Actions result after pushing.
- [ ] Check whether Vercel and Render deployed the expected commit.
- [ ] If production was touched, verify frontend, `/live`, and `/ready`.
- [ ] If a smoke check failed, follow `docs/INCIDENT_RESPONSE.md`.
- [ ] Keep any real user data out of prompts, screenshots, commits, and logs.

## Weekly Beta Routine

Time estimate: 20 to 40 minutes.

- [ ] Review GitHub Actions for failed or flaky runs.
- [ ] Run or confirm the `Production Smoke Check`.
- [ ] Check Render logs for repeated 4xx/5xx patterns, boot failures, database connection errors, or worker crashes.
- [ ] Check Vercel deployment/build logs for warnings or failed deploys.
- [ ] Review `docs/QA_CHECKLIST.md` and run the highest-risk manual flows with a test account:
  - register/login/logout,
  - add/edit/delete transaction,
  - dashboard/analytics sanity,
  - data export with a test account,
  - account deletion only with disposable test data.
- [ ] Confirm no `.env` files or generated exports are staged.
- [ ] Delete local exports, logs, or backups that are no longer needed.
- [ ] Add a short note outside git for anything operationally important.

## Monthly Routine

Time estimate: 45 to 90 minutes.

- [ ] Run backend tests.
- [ ] Run frontend tests.
- [ ] Run frontend lint and build.
- [ ] Run dependency audits.
- [ ] Review `docs/SECURITY_CHECKLIST.md`.
- [ ] Review `docs/RETENTION.md` open decisions.
- [ ] Review `docs/PRIVACY_NOTICE_DRAFT.md` for drift from actual behavior.
- [ ] Review `docs/BACKUP_RESTORE.md` and confirm the backup plan is still realistic.
- [ ] If production data or schema work is planned, create and verify a backup first.
- [ ] Confirm staging, if configured, still uses separate provider settings and a separate database.
- [ ] Review recent incidents or near-misses and update docs/tests.

## Before Every Meaningful Release

Use this before a release that touches auth, data, imports, exports, analytics, migrations, deployment, or security.

- [ ] Confirm the working tree contains only intended changes.
- [ ] Run the relevant backend tests.
- [ ] Run frontend tests if frontend behavior changed.
- [ ] Run frontend lint/build if frontend code changed.
- [ ] Run audit/security checks if dependencies or security-sensitive areas changed.
- [ ] Run `git diff --check`.
- [ ] Review `docs/QA_CHECKLIST.md`.
- [ ] Use a test account for manual smoke testing.
- [ ] Verify no secrets, real exports, screenshots with financial data, or backup files are staged.
- [ ] Push only after checks pass or failures are clearly understood.

## Before Any Database Migration

Database changes need a higher bar than normal releases.

- [ ] Read `docs/MIGRATIONS.md`.
- [ ] Read `docs/BACKUP_RESTORE.md`.
- [ ] Confirm the migration was tested locally.
- [ ] Create a fresh backup or provider export.
- [ ] Verify the backup can be listed or restored in local/staging.
- [ ] Confirm rollback plan.
- [ ] Confirm production migration approval.
- [ ] Do not run destructive SQL.
- [ ] Do not drop tables.

## Before Any Backup Or Restore Work

- [ ] Confirm the target environment: local, staging, or production.
- [ ] Keep backup files outside git.
- [ ] Store local backups under ignored paths such as `local-backups/` or `backups/`.
- [ ] Verify backup readability.
- [ ] Restore only to local or staging unless explicit production restore approval exists.
- [ ] Delete local backups when they are no longer needed.

## Quarterly Or Pre-Beta Review

Time estimate: 1 to 2 hours.

- [ ] Run a simulated incident drill from `docs/INCIDENT_RESPONSE.md`.
- [ ] Review and update `docs/CODEX_CONTEXT.md`.
- [ ] Review Render, Vercel, GitHub, email, and AI/provider settings.
- [ ] Confirm enabled vendors match `docs/PRIVACY_NOTICE_DRAFT.md`.
- [ ] Confirm provider retention behavior matches `docs/RETENTION.md`.
- [ ] Confirm the self-serve export still excludes sensitive fields and other users' data.
- [ ] Confirm account deletion cleanup tests still cover all user-owned models.
- [ ] Review whether frontend test coverage should expand to transactions, auth gates, import, or analytics.
- [ ] Review whether staging should be promoted from documentation to actual provider resources.

## After An Incident Or Near Miss

- [ ] Follow `docs/INCIDENT_RESPONSE.md`.
- [ ] Add a regression test when practical.
- [ ] Update docs if the runbook was unclear.
- [ ] Rotate secrets if exposure was possible.
- [ ] Review backups if data integrity was involved.
- [ ] Review privacy and retention docs if user data was involved.
- [ ] Record a private summary outside git if real users, secrets, or providers were involved.

## Suggested Calendar Cadence

For a solo beta:

- Daily: quick deploy and smoke awareness.
- Weekly: logs, smoke, manual critical-flow QA.
- Monthly: full local verification and docs/security review.
- Quarterly: incident drill and privacy/retention review.
- Before any database migration: backup and restore verification.
- After any incident: post-incident review and regression prevention.

## What Not To Automate Yet

Avoid adding complexity until there is real need:

- Paid monitoring vendors.
- Complex on-call systems.
- Automated production migrations.
- Automated production restores.
- Automated production data exports.
- Broad admin dashboards for user data.

Prefer simple checklists, tests, free platform alerts, and safe manual approval steps while the app is still solo-operated.
