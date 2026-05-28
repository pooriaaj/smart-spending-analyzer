# Environment Guide

This guide explains how environment configuration should work for local development and production. It intentionally lists variable names only and never includes real values.

## Local Versus Production

Local development runs on your machine and can use local-only values, test databases, or disabled optional services. Production runs on Render and Vercel and must use production-safe settings configured in those providers' dashboards.

- Backend local: FastAPI reads environment variables for database, auth, CORS, email, imports, OCR, and assistant behavior.
- Frontend local: Vite reads frontend variables from the frontend project environment.
- Backend production: Render should store backend variables in the Render dashboard or a Render environment group.
- Frontend production: Vercel should store frontend variables in the Vercel project environment settings.

## Backend Environment Variable Names

Core runtime:

- `DATABASE_URL`
- `ENVIRONMENT`
- `APP_ENV`
- `HOST`
- `PORT`
- `WEB_CONCURRENCY`
- `FORWARDED_ALLOW_IPS`
- `UVICORN_TIMEOUT_KEEP_ALIVE`
- `UVICORN_GRACEFUL_TIMEOUT`

Database pool:

- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT_SECONDS`
- `DB_POOL_RECYCLE_SECONDS`

Auth and cookies:

- `SECRET_KEY`
- `ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `ACCESS_TOKEN_COOKIE_NAME`
- `AUTH_COOKIE_SECURE`
- `AUTH_COOKIE_SAMESITE`
- `BCRYPT_ROUNDS`
- `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`
- `EXPOSE_RESET_LINK_IN_RESPONSE`

Origins and hosts:

- `FRONTEND_URL`
- `BACKEND_URL`
- `ALLOWED_ORIGINS`
- `ALLOWED_HOSTS`

Request limits, rate limits, and imports:

- `RATE_LIMIT_MAX_TRACKED_KEYS`
- `MAX_API_REQUEST_BODY_BYTES`
- `MAX_IMPORT_FILE_BYTES`
- `MAX_IMPORT_BATCH_FILES`
- `MAX_IMPORT_BATCH_BYTES`
- `MAX_IMPORT_CSV_ROWS`
- `PDF_TEXT_MAX_PAGES`
- `PDF_OCR_RENDER_DPI`
- `MAX_TRANSACTION_REVIEW_SCAN`
- `REBUILD_MERCHANT_CACHE_ON_STARTUP`

Email and password reset delivery:

- `RESEND_API_KEY`
- `EMAIL_FROM`
- `RESEND_FROM_EMAIL`
- `EMAIL_FROM_NAME`
- `EMAIL_TIMEOUT_SECONDS`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_FROM_NAME`
- `SMTP_USE_TLS`
- `SMTP_TIMEOUT_SECONDS`

Merchant enrichment:

- `GOOGLE_PLACES_API_KEY`
- `MERCHANT_LOOKUP_REGION`
- `MERCHANT_LOOKUP_REGION_CODE`
- `MERCHANT_LOOKUP_TIMEOUT_SECONDS`

Local OCR and vision OCR:

- `LOCAL_OCR_ENABLED`
- `LOCAL_OCR_COMMAND`
- `LOCAL_OCR_LANGUAGE`
- `LOCAL_OCR_PAGE_SEGMENTATION_MODE`
- `LOCAL_OCR_TIMEOUT_SECONDS`
- `OPENAI_API_KEY`
- `OCR_VISION_MODEL`
- `OCR_TIMEOUT_SECONDS`
- `OCR_MAX_RETRIES`
- `OCR_RESPONSE_MAX_CHARS`

Assistant and LLM:

- `OPENAI_MODEL`
- `USE_LLM_ASSISTANT`
- `LLM_PROVIDER`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`
- `LLM_MAX_OUTPUT_TOKENS`
- `USE_LOCAL_LLM`
- `LOCAL_LLM_PROVIDER`
- `LOCAL_LLM_BASE_URL`
- `LOCAL_LLM_MODEL`
- `LOCAL_LLM_API_KEY`
- `ASSISTANT_DAILY_LLM_LIMIT`
- `ASSISTANT_DAILY_LLM_CHAR_LIMIT`
- `ASSISTANT_LEARNING_MAX_EXAMPLES_PER_USER`

## Frontend Environment Variable Names

- `VITE_API_BASE_URL`

Any frontend variable that starts with `VITE_` is included in browser builds and can be seen by users. Never put secrets, private API keys, JWT secrets, database URLs, or passwords in `VITE_` variables.

## `.env`, `.env.example`, Render, And Vercel

- `.env.example` is a committed template. It can list variable names and safe placeholders, but must not contain real secrets.
- Local backend secrets should live in ignored local environment files such as `backend/.env`.
- Local frontend values can live in ignored Vite environment files under `frontend/`, such as `.env.local`.
- Render environment variables belong in the Render dashboard or a Render environment group, not in git.
- Vercel environment variables belong in the Vercel dashboard, not in git.
- Do not copy production values into docs, tickets, commits, AI prompts, or screenshots.

## Local Setup Checklist

1. Confirm `.env` files are ignored by git.
2. Create or update local backend environment variables without committing values.
3. Install backend dependencies from `backend/requirements.txt`.
4. Install frontend dependencies from `frontend/package-lock.json` with `npm ci` or `npm install`.
5. Start the backend locally and check `/live` and `/ready`.
6. Start the frontend locally and confirm it points to the local backend through `VITE_API_BASE_URL`.
7. Keep optional services disabled unless you intentionally configure them.
8. Before pushing, run backend tests and the frontend build when relevant.
