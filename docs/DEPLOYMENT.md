# Deployment Guide

Smart Spending Analyzer currently deploys the frontend to Vercel, the backend to Render, and the database to Render PostgreSQL.

For pre-production testing, see `docs/STAGING.md`.

## Frontend On Vercel

- Project root should be `frontend`.
- Build command should run the Vite build script.
- Build output is `dist`.
- `frontend/vercel.json` provides SPA rewrites and security headers.
- Configure `VITE_API_BASE_URL` in Vercel environment settings.
- Remember: `VITE_` variables are visible in browser builds and must not contain secrets.

## Backend On Render

- `render.yaml` defines a Docker web service named `smart-spending-analyzer`.
- Dockerfile path is `backend/Dockerfile`.
- Docker context is `backend`.
- Render health check path is `/ready`.
- Runtime settings and secrets should be configured in Render environment variables.
- `backend/run.py` reads Render's `PORT` and production runtime settings from environment variable names.

## Database On Render PostgreSQL

- The backend expects a PostgreSQL-compatible `DATABASE_URL`.
- Production database credentials belong only in Render environment variables.
- Do not paste database URLs into docs, commits, AI prompts, or frontend environment variables.
- Do not run destructive database commands against production.

## Deployment Checklist

Before deploying:

1. Confirm `git status --short` only shows intentional changes.
2. Run backend tests when backend code or database behavior changed.
3. Run frontend build when frontend code changed.
4. Run frontend tests when frontend code changed.
5. Confirm `.env` files are not staged.
6. Confirm Render has the required backend variable names configured.
7. Confirm Vercel has the required frontend variable names configured.
8. Confirm `FRONTEND_URL`, `BACKEND_URL`, `ALLOWED_ORIGINS`, and `ALLOWED_HOSTS` match the deployed domains.
9. Confirm `AUTH_COOKIE_SECURE` and `AUTH_COOKIE_SAMESITE` are production-safe.
10. Confirm no production migration or destructive database change is part of the deploy unless separately approved.
11. If a production migration is approved, follow `docs/BACKUP_RESTORE.md` first.

## Health And Smoke Tests

Backend:

- `GET /live` should return a healthy process response.
- `GET /ready` should return healthy only when the database is reachable.
- `GET /health` mirrors readiness for compatibility.
- GitHub Actions also includes `Production Smoke Check`, which can be run manually after deploys.

Frontend:

- The Vercel URL should load without a blank screen.
- Login/register pages should render.
- Protected pages should redirect unauthenticated users.
- Authenticated pages should load after login.

Production smoke test after deploy:

1. Open the Vercel frontend.
2. Register or log in with a safe test account.
3. Create a small test transaction.
4. Confirm analytics update.
5. Log out.
6. Confirm protected routes redirect.
7. Check Render logs for unexpected server errors.
8. Check browser console/network for obvious frontend errors.
9. Optionally run the `Production Smoke Check` workflow from GitHub Actions.

## Rollback Basics

- Frontend: use Vercel deployment history to promote or roll back to a previous known-good deployment.
- Backend: use Render deploy history or redeploy a previous known-good commit.
- Database: rollback is not the same as code rollback. Restore requires a backup and explicit approval.

Never use rollback as a substitute for database backups. Do not run destructive database changes in production without a tested backup and a clear restore plan. For database-specific preparation, use `docs/BACKUP_RESTORE.md`.
