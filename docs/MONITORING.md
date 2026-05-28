# Monitoring Guide

This guide adds a free-first monitoring layer for Smart Spending Analyzer. It uses existing platform health checks, platform logs, and a lightweight GitHub Actions smoke check.

No paid monitoring vendor is required.

## Current Monitoring Layers

Backend health endpoints:

- `/live`: confirms the API process is running.
- `/ready`: confirms the API can reach the database.
- `/health`: mirrors readiness for compatibility.

Render:

- `render.yaml` sets `healthCheckPath: /ready`.
- Render uses health checks to decide whether new deploys are ready and whether running instances need recovery.
- Render dashboard logs are the first place to inspect backend errors.

Vercel:

- Vercel build logs show frontend deployment problems.
- Vercel runtime logs are available from the dashboard.

GitHub:

- `.github/workflows/security-ci.yml` protects pushes and pull requests.
- `.github/workflows/production-smoke.yml` runs a daily and manually-triggered smoke check against the deployed frontend and backend health endpoints.

Official docs:

- Render health checks: https://render.com/docs/health-checks
- Render logs: https://render.com/docs/logging
- Vercel logs: https://vercel.com/docs/logs
- GitHub Actions scheduled workflows: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions

## Production Smoke Check

The production smoke workflow checks:

- frontend URL loads,
- backend `/live` responds,
- backend `/ready` confirms database readiness.

The workflow can be run manually from GitHub Actions and also runs once per day.

This is not a full uptime service. GitHub scheduled workflows can run late or be skipped under some platform conditions, so treat this as a free safety net, not a commercial SLA.

## What To Do When The Smoke Check Fails

1. Open the failed GitHub Actions run.
2. Identify which step failed: frontend, `/live`, or `/ready`.
3. If frontend failed, check Vercel deployment status and build logs.
4. If `/live` failed, check Render service status and backend logs.
5. If `/ready` failed but `/live` passed, check Render PostgreSQL status, `DATABASE_URL` configuration, and database connection errors in logs.
6. Do not change production environment variables until the cause is understood.
7. If database readiness is the problem, do not run migrations or restore steps until `docs/BACKUP_RESTORE.md` has been followed.
8. Follow `docs/INCIDENT_RESPONSE.md` for severity, evidence capture, rollback, and communication steps.

## Logs To Check

Frontend:

- Vercel deployment build logs.
- Vercel runtime logs.
- Browser console during manual QA.

Backend:

- Render deploy logs.
- Render runtime logs.
- `X-Request-ID` response header when tracing a specific request.

GitHub:

- `Security CI`
- `Production Smoke Check`

## Alerting Policy

Free-first alerting:

- GitHub Actions failure notifications.
- Render dashboard notifications.
- Vercel dashboard/email notifications.

Optional later:

- UptimeRobot or another free-tier uptime checker.
- Sentry or another error tracker, but only after deciding whether user data could leave the app and documenting privacy impact.
- Provider log drains, if paid plans become worthwhile.

## Logging Safety

- Never log passwords.
- Never log JWTs or cookies.
- Never log reset tokens.
- Never log full database URLs.
- Never paste logs containing secrets into Codex.
- Keep API errors sanitized for users and detailed only in server-side logs.
- If logs may contain real secrets or user data, handle them through `docs/INCIDENT_RESPONSE.md`.

## Manual Weekly Review

Once per week during beta:

- Check GitHub Actions failures.
- Check Render logs for repeated 5xx errors.
- Check Vercel deployments for build warnings.
- Run a production smoke test from `docs/QA_CHECKLIST.md`.
- Confirm backups are still understood before any database changes.
