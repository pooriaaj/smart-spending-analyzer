# Staging Guide

This guide proposes a safe staging workflow for Smart Spending Analyzer. It is documentation only: no Render, Vercel, database, or DNS settings are changed by this file.

## Goal

Staging should let you test the real deployed app before production without risking production users or production data.

The safest solo-developer version is:

- Production branch: `main`
- Optional staging branch: `staging`
- Frontend staging: Vercel Preview deployment for the `staging` branch
- Backend staging: separate Render web service
- Database staging: separate PostgreSQL database

Never point staging at the production database.

## Current Platform Reality

Vercel creates Preview deployments for branches that are not the production branch. Preview environment variables can be branch-specific, so a `staging` branch can have its own `VITE_API_BASE_URL`.

Render has automated Preview Environments for pull requests, but Render's current docs say those require a Pro plan or higher and preview resources are billed. The free/feasible path is a manual staging service and staging database if your account limits allow it.

Official docs:

- Vercel Git deployments and preview branches: https://vercel.com/docs/deployments/git
- Vercel environment variables and Preview variables: https://vercel.com/docs/projects/environment-variables
- Render Preview Environments: https://render.com/docs/preview-environments

## Recommended Staging Shape

Production:

- Git branch: `main`
- Frontend: existing Vercel production deployment
- Backend: existing Render production service
- Database: existing Render PostgreSQL database

Staging:

- Git branch: `staging`
- Frontend: Vercel Preview deployment from `staging`
- Backend: separate Render web service, for example `smart-spending-analyzer-staging`
- Database: separate Render PostgreSQL database, for example `smart-spending-staging`

Feature work:

- Feature branch -> pull request -> CI and Vercel preview
- Merge to `staging` -> staging deployment
- Manual QA on staging
- Merge `staging` to `main` -> production deployment

## Staging Environment Variable Names

Use the same variable names as production, but different values in the provider dashboards.

Backend staging should configure names such as:

- `DATABASE_URL`
- `SECRET_KEY`
- `ENVIRONMENT`
- `FRONTEND_URL`
- `BACKEND_URL`
- `ALLOWED_ORIGINS`
- `ALLOWED_HOSTS`
- `AUTH_COOKIE_SECURE`
- `AUTH_COOKIE_SAMESITE`
- optional email, OCR, merchant, and assistant variables only if intentionally enabled

Frontend staging should configure:

- `VITE_API_BASE_URL`

Remember: `VITE_` variables are visible in browser builds and must not contain secrets.

## Suggested Safety Settings

Staging should be production-like enough to catch deployment issues:

- Use HTTPS URLs.
- Use secure cookies.
- Use strict allowed origins and hosts.
- Use a strong staging-only `SECRET_KEY`.
- Use a staging-only database.
- Keep optional paid APIs disabled until needed.
- Use test accounts and fake data.

Do not reuse production credentials, production API keys, or production database URLs in staging.

## Manual Setup Checklist

Do these in provider dashboards, not in git:

1. Create a `staging` Git branch from `main`.
2. Create or configure Vercel Preview variables for the `staging` branch.
3. Create a separate Render staging database.
4. Create a separate Render staging backend service from the same repo.
5. Configure backend staging environment variables using staging-only values.
6. Point Vercel staging `VITE_API_BASE_URL` at the staging backend URL.
7. Deploy the staging backend.
8. Deploy the Vercel staging preview.
9. Run the staging smoke checklist.
10. Only then merge to `main` for production.

## Staging Smoke Checklist

- [ ] Vercel staging frontend loads.
- [ ] Render staging `/live` responds.
- [ ] Render staging `/ready` confirms staging database connectivity.
- [ ] Register a staging-only test user.
- [ ] Login and logout work.
- [ ] Protected routes redirect after logout.
- [ ] Add/edit/delete a transaction.
- [ ] Analytics update after transaction changes.
- [ ] Import flow works with safe test files.
- [ ] Assistant refuses secret-seeking requests.
- [ ] Browser console has no unexpected errors.
- [ ] Render logs have no unexpected server errors.

## Database Rules

- Staging must use its own database.
- Do not copy production data into staging unless explicitly approved and anonymized.
- Do not run production migrations from staging validation.
- Test migrations on staging only after a staging backup exists.
- Follow `docs/BACKUP_RESTORE.md` before any production migration.

## Cost-Aware Options

Lowest cost:

- Use Vercel Preview deployments for frontend checks.
- Keep backend/database testing local until a release candidate is ready.
- Use production deploy only after backend tests, frontend tests, build, and manual QA pass.

Better solo beta path:

- Keep a long-lived manual staging backend and staging database.
- Use small/free provider plans only if current provider limits allow it.
- Seed fake data instead of copying production data.

Paid convenience path:

- Use Render Preview Environments for pull requests if you later move to a Render plan that supports them.

## What Codex May Do Next

Codex may safely:

- Create a `staging` branch locally after approval.
- Add a staging checklist or deployment checklist.
- Draft provider-dashboard steps using variable names only.
- Add fake-data seed guidance for staging.

Codex must not:

- Create production credentials.
- Print secret values.
- Change provider settings without explicit approval.
- Point staging at production data.
- Run production migrations.
