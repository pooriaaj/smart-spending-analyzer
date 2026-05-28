# Release Process

Use this process before pushing a meaningful change to production. It is intentionally simple for a solo developer using GitHub, Vercel, Render, and free or feasible checks.

This process does not approve production migrations, restores, destructive database work, new vendors, or secret changes. Those require separate explicit approval.

## Release Types

### Docs-Only Release

Examples: runbooks, checklists, README updates, planning docs.

Minimum checks:

- `git status --short --branch`
- `git diff --check`
- Secret-oriented review of changed docs.

### Frontend Release

Examples: pages, components, API client behavior, UI copy, styles.

Minimum checks:

- Frontend tests for changed behavior.
- Frontend lint.
- Frontend build.
- Manual QA for changed flows when practical.

### Backend Release

Examples: routes, services, auth, imports, exports, analytics, database access.

Minimum checks:

- Focused backend tests for changed behavior.
- Full backend tests before broad beta releases or risky backend changes.
- Manual API or browser smoke test for changed user workflows.

### Database Or Migration Release

Examples: Alembic migration, model changes, startup schema maintenance changes, bulk data repair.

Minimum checks:

- Read `docs/MIGRATIONS.md`.
- Read `docs/BACKUP_RESTORE.md`.
- Test locally first.
- Create and verify a fresh backup before production work.
- Get explicit production migration approval.
- Do not drop tables or run destructive SQL.

## Pre-Release Checklist

1. Confirm the branch and target:
   - `git status --short --branch`
   - `git log -5 --oneline`
2. Review the actual diff:
   - `git diff`
   - `git diff --check`
3. Confirm no sensitive files are staged:
   - `.env`
   - `backend/.env`
   - `.env.*`
   - local backups or exports
   - screenshots or logs with real user data
4. Run checks based on the release type.
5. Review `docs/QA_CHECKLIST.md` for user-facing flows affected by the change.
6. Review `docs/SECURITY_CHECKLIST.md` if the change touches auth, security, imports, exports, AI, or user data.
7. If the change touches deployment settings, review `docs/DEPLOYMENT.md`.
8. If the change touches staging or production provider settings, stop for explicit approval.

## Commit And Push

For a direct `main` release:

1. Stage only intended files.
2. Commit with a clear short message.
3. Push to `origin main`.
4. Watch GitHub Actions, Vercel, and Render for the expected commit.

For a safer branch release:

1. Create a branch such as `codex/release-topic`.
2. Push the branch.
3. Open a draft pull request.
4. Run checks and review the diff before merging.

Direct pushes are convenient for a solo project, but use branches for risky, large, database, auth, security, or provider changes.

## Production Smoke Test

After deployment:

1. Open the Vercel frontend.
2. Confirm the page loads without a blank screen.
3. Check backend `/live`.
4. Check backend `/ready`.
5. Log in with a test account when the release touches authenticated behavior.
6. Run changed user flows with disposable test data.
7. Check Render and Vercel deploy logs for obvious failures.
8. Run the GitHub Actions `Production Smoke Check` manually when useful.

Do not use real financial data for smoke testing.

## Rollback Basics

- Frontend: use Vercel deployment history to restore a previous known-good deployment.
- Backend: use Render deploy history or redeploy a previous known-good commit.
- Database: do not treat code rollback as database rollback. Database restore requires backup verification and explicit approval.

If a release creates user impact, follow `docs/INCIDENT_RESPONSE.md`.

## Post-Release Notes

For meaningful releases, add a safe summary to `docs/MAINTENANCE_LOG.md` only if it helps future context.

Do not record:

- real user data,
- secrets or credential values,
- raw provider logs,
- database URLs,
- production export contents,
- screenshots with financial details.

Use private notes outside git for anything involving real incidents, provider evidence, users, or sensitive operational details.
