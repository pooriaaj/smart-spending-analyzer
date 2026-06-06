# Runbook Index

Use this page as the starting point for operating Smart Spending Analyzer safely. It is a map to existing docs, not a replacement for them.

Keep this file free of secrets, real user data, provider logs, database URLs, access tokens, screenshots with financial data, and raw exports.

## Start Here

- `docs/CODEX_CONTEXT.md`: persistent project context for future Codex sessions.
- `README.md`: public project overview, live URLs, GitHub workflow badges, testing summary, and docs entry points.
- `docs/ENVIRONMENT.md`: local, Render, and Vercel environment variable guidance by variable name only.
- `docs/DEPLOYMENT.md`: deploy, smoke-test, rollback, and production database warnings.
- `docs/SECURITY_CHECKLIST.md`: recurring security checks before sharing, deploying, rotating keys, or using Codex on sensitive areas.
- `docs/QA_CHECKLIST.md`: manual product checks for auth, transactions, dashboard, analytics, imports, mobile, errors, and production smoke testing.
- `docs/LEGAL_PROTECTION.md`: proprietary license, public GitHub, copyright, trademark, and copycat-response guidance.

## Release And Operations

- `docs/RELEASE_PROCESS.md`: release types, pre-release checks, push flow, production smoke testing, rollback basics, and post-release notes.
- `docs/CI_REVIEW.md`: browser-first and optional GitHub CLI workflow review steps.
- `docs/OPERATIONS_CALENDAR.md`: daily, weekly, monthly, release, migration, backup, and incident-follow-up cadence.
- `docs/MAINTENANCE_LOG.md`: safe non-secret summaries of maintenance passes that are useful for future context.
- `docs/MONITORING.md`: free-first monitoring plan and production smoke workflow notes.
- `.github/workflows/production-smoke.yml`: manual and scheduled public health checks.
- `.github/workflows/security-ci.yml`: backend tests, Python audit/security checks, frontend audit/tests/build.

## Database Work

- `docs/MIGRATIONS.md`: Alembic workflow and migration safety rules.
- `docs/BACKUP_RESTORE.md`: backup and restore process, including production approval boundaries.
- `backend/alembic/`: local Alembic configuration and baseline migration.

Database rule of thumb: local/test inspection is normal; production migrations, restores, destructive SQL, and table drops require explicit approval.

## Privacy And User Data

- `docs/PRIVACY_DATA.md`: current account deletion, export, and data handling behavior.
- `docs/PRIVACY_NOTICE_DRAFT.md`: draft public-facing privacy language, not legal-approved.
- `docs/RETENTION.md`: draft retention expectations and open decisions.

User data rule of thumb: use disposable test accounts for QA, keep exports outside git, and never paste real financial data into AI prompts or issue threads.

## Legal And Ownership

- `LICENSE`: proprietary all-rights-reserved source license.
- `NOTICE`: ownership, trademark, and third-party dependency notice.
- `docs/LEGAL_PROTECTION.md`: practical legal protection checklist and copycat-response steps.

Legal rule of thumb: use `(TM)` or `™` for claimed marks, and use `(R)` or `®` only after an actual trademark registration is confirmed.

## Incidents

- `docs/INCIDENT_RESPONSE.md`: response steps for outage, bad deploy, leaked secret, data exposure, database issue, dependency issue, AI/Codex issue, and rollback coordination.

Incident rule of thumb: real incidents, provider evidence, user-impact notes, and raw logs belong in private notes outside git.

## Staging

- `docs/STAGING.md`: safe manual staging workflow using separate provider settings and a separate database.

Staging rule of thumb: never point staging at the production database.

## Future Codex Session Checklist

Before changing code or docs, ask:

1. Does this touch secrets, `.env`, provider settings, auth, security, database models, migrations, backups, restores, account deletion, user export, or retention?
2. If yes, has the user explicitly approved that exact risk?
3. Can the work be done with docs, local tests, or test data instead of production changes?
4. Are the changed files intentionally scoped?
5. Are secret scans, tests, lint/build, or smoke checks appropriate for this change?

If a task is ambiguous, prefer a safe audit or documentation update before changing behavior.
