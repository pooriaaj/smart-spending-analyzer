# Smart Spending Analyzer Codex Context

This file is persistent context for future Codex sessions. Keep it factual, current, and free of secret values.

## 1. Project Name And Purpose

Smart Spending Analyzer is a full-stack personal finance web app. It helps users register, log in, track transactions, import statement data, analyze spending, manage budgets, and use a guarded assistant for finance-related questions and guidance.

## 2. Current Stack

- Frontend: React, Vite, React Router, Axios, Recharts.
- Backend: FastAPI, SQLAlchemy, Pydantic, Uvicorn.
- Database: PostgreSQL-ready through `DATABASE_URL`; tests use SQLite.
- Auth: JWT-backed HttpOnly cookies with bcrypt password hashing and legacy PBKDF2 verification.
- Imports/OCR: CSV and PDF import paths, pypdf, optional local Tesseract OCR, optional OpenAI vision OCR.
- AI assistant: OpenAI SDK or OpenAI-compatible local provider when enabled; rule-based fallback paths when disabled.
- Deployment: frontend on Vercel, backend on Render, database on Render PostgreSQL.
- Staging: `docs/STAGING.md` proposes a safe manual staging path using a `staging` branch, Vercel Preview, a separate Render backend service, and a separate staging database.
- Monitoring: `docs/MONITORING.md` and `.github/workflows/production-smoke.yml` provide a free-first smoke-check and incident runbook.
- Incident response: `docs/INCIDENT_RESPONSE.md` documents outage, leaked-secret, data-exposure, database, dependency, and AI/Codex incident handling.
- Runbooks: `docs/RUNBOOK_INDEX.md` is the starting map for operational docs and safety rules.
- Operations: `docs/OPERATIONS_CALENDAR.md` provides daily, weekly, monthly, pre-release, pre-migration, and incident-follow-up routines for solo maintenance; `docs/MAINTENANCE_LOG.md` records safe non-secret maintenance summaries.
- Privacy/data lifecycle: `docs/PRIVACY_DATA.md` documents deletion/export behavior and data handling rules; `docs/PRIVACY_NOTICE_DRAFT.md` and `docs/RETENTION.md` provide non-legal draft privacy/retention language.
- Migrations: Alembic config and an initial schema baseline now exist under `backend/alembic/`; production migrations are not automatic and are not approved by default.
- CI/security: GitHub Actions with backend tests, pip-audit, bandit, frontend npm audit, frontend tests, and frontend build.

Observed note: the README mentions PyMuPDF for rendering scanned PDFs before OCR, and `pdf_statement_service.py` imports `fitz` dynamically, but `backend/requirements.txt` did not list PyMuPDF during this inspection. Verify this before relying on rendered scanned-PDF OCR in production.

## 3. Current Deployment Structure

- `frontend/vercel.json` defines frontend security headers and SPA rewrites to `index.html`.
- `render.yaml` defines a Docker web service named `smart-spending-analyzer` with `backend/Dockerfile`, Docker context `backend`, automatic deploys, and health check path `/ready`.
- `backend/Dockerfile` installs Python dependencies and the Tesseract system package, then runs `python run.py`.
- `backend/run.py` reads host, port, worker, proxy, and timeout settings from environment variable names.
- Backend health endpoints in `backend/app/main.py` include `/live`, `/ready`, and `/health`; `/ready` checks database connectivity.

## 4. Current Backend Structure

- `backend/app/main.py`: FastAPI app, middleware registration, routers, health endpoints, startup maintenance.
- `backend/app/database.py`: SQLAlchemy engine/session setup from `DATABASE_URL`.
- `backend/app/models.py`: SQLAlchemy models for users, accounts, transactions, category memory, assistant data, merchant lookup cache, budgets, and saved scenarios.
- `backend/app/schemas.py`: request/response schemas and validation.
- `backend/app/auth.py`: password hashing, JWT creation/decoding, auth cookie helpers.
- `backend/app/security.py`: CORS helpers, trusted host helpers, CSRF Origin middleware, body size middleware, security headers, rate limiting, import validation helpers, redaction helpers.
- `backend/app/dependencies.py`: shared request dependencies such as current user and database session.
- `backend/app/routes/`: route layer for auth, users, accounts, budgets, transactions/imports, analytics, and assistant.
- `backend/app/services/`: business logic for analytics, transactions, imports, budgets, assistant, OCR, email, merchant enrichment, database maintenance, and related helpers.
- `backend/tests/`: backend regression tests for routes, imports, analytics, budgets, security hardening, PDF parsing, users, and database maintenance.

## 5. Current Frontend Structure

- `frontend/src/App.jsx`: React Router setup, protected routes, lazy-loaded pages, auth gate based on `/users/me`.
- `frontend/src/main.jsx`: React root and `ErrorBoundary`.
- `frontend/src/services/api.js`: Axios client using `VITE_API_BASE_URL` and `withCredentials: true`.
- `frontend/src/pages/`: login, register, forgot/reset password, transactions, analytics, assistant, profile, import, budgets, and legacy/redirected pages.
- `frontend/src/components/`: shared controls and form components.
- `frontend/src/utils/`: display and error helpers.
- `frontend/src/i18n/`: language context.
- Frontend tests now use Vitest, jsdom, and Testing Library for focused component/service/unit coverage.

## 6. Current Database Approach

- The app uses SQLAlchemy models and `Base.metadata.create_all(bind=engine)` at backend startup.
- Production is expected to use PostgreSQL through `DATABASE_URL`.
- Backend tests create SQLite databases for isolated test runs.
- `backend/app/services/database_maintenance_service.py` runs idempotent startup maintenance for selected columns and indexes. This is helpful for early deployment drift but should be replaced over time by reviewed migrations.
- `backend/sql/add_indexes.sql` contains manual index SQL.
- `backend/alembic/versions/20260528_0001_initial_schema.py` is the first Alembic baseline for fresh databases.
- `backend/tests/test_alembic_baseline.py` verifies that the baseline can create the expected schema on a temporary SQLite database.

## 7. Current Auth And Security Approach

- Auth uses HttpOnly cookies containing signed JWTs.
- New passwords are hashed with bcrypt; legacy PBKDF2 hashes remain verifiable.
- Password reset tokens are hashed before storage; reset URLs are not exposed in production responses.
- CORS is origin-based and credentials-aware.
- Trusted host middleware is enabled.
- Unsafe requests are checked with CSRF Origin middleware.
- Request body limits and import upload validation are implemented.
- Backend security headers and Vercel frontend security headers are present.
- Simple in-process rate limiting covers auth, assistant, and import-heavy paths.
- Backend error handling returns sanitized generic server errors and frontend-safe validation shapes.
- Assistant logic includes prompt-injection and secret-request guardrails.

Known limitation: the in-process rate limiter is fine for a small single-instance app but should move to a shared store if the backend scales horizontally.

## 8. Existing Test And CI Setup

- Backend tests exist in `backend/tests/`.
- Dev security/test dependencies are listed in `backend/requirements-dev.txt`.
- `.github/workflows/security-ci.yml` runs:
  - backend dependency install,
  - backend pytest,
  - Python dependency audit with pip-audit,
  - Bandit scan,
  - frontend npm install,
  - frontend npm audit,
  - frontend tests,
  - frontend build.
- Frontend currently has build, lint, test, and watch-test scripts. End-to-end tests are not present yet.

## 9. Known Risks And Missing Company-Readiness Pieces

- Alembic exists, but production migration workflow is not complete yet.
- `docs/BACKUP_RESTORE.md` now documents backup and restore safety, including Render export/PITR paths and local `pg_dump` fallback.
- Frontend automated tests exist, but coverage is still intentionally small.
- `docs/STAGING.md` documents the staging workflow, but the actual staging provider resources have not been created.
- Monitoring now includes platform logs, health endpoints, and a scheduled/manual GitHub Actions smoke check. It is still not a commercial uptime SLA.
- `docs/INCIDENT_RESPONSE.md` documents a solo-developer incident response process, but no real incident drill has been performed yet.
- `docs/OPERATIONS_CALENDAR.md` documents recurring solo-maintainer routines, and `docs/MAINTENANCE_LOG.md` has the first test-only weekly maintenance pass. The cadence still has not been practiced over multiple weeks yet.
- Deployment/QA documentation was missing before this docs pass.
- `docs/PRIVACY_DATA.md`, `docs/PRIVACY_NOTICE_DRAFT.md`, and `docs/RETENTION.md` document the current privacy/data lifecycle, draft public-facing privacy language, and draft retention targets. Self-serve JSON data export exists for the authenticated current user with password confirmation. Backend tests cover account deletion cleanup, export scoping, and sensitive field exclusion for core user-owned rows.
- Runtime schema maintenance should be replaced by controlled migrations before many real users depend on production data.
- Production migrations should still wait for an actual fresh backup and restore verification for the target database.
- Optional scanned-PDF rendering should be verified because PyMuPDF was not listed in `backend/requirements.txt` during this inspection.

## 10. Safe Rules For Future Codex Sessions

- Never expose, print, summarize, or copy real secret values.
- Do not modify `.env` files unless the user explicitly asks and approves the exact change.
- Do not commit API keys, database URLs, JWT secrets, passwords, tokens, or production credentials.
- If inspecting environment files, only mention variable names, never values.
- Do not run production migrations.
- Do not drop tables.
- Do not run destructive database changes.
- Do not change auth, security, or database model behavior without first explaining the risk and asking for approval.
- Prefer narrow, documented changes over broad refactors.
- Use backend tests and frontend build/lint checks when changes touch behavior.
- For database work, default to local/test databases first and keep production as a separate explicit approval step.

## 11. Files That Should Not Be Changed Without Confirmation

- `.env`, `backend/.env`, and any `.env.*` file containing local or deployed settings.
- Render and Vercel dashboard environment variables.
- `backend/app/models.py`
- `backend/app/database.py`
- `backend/app/auth.py`
- `backend/app/security.py`
- `backend/app/dependencies.py`
- `backend/app/services/database_maintenance_service.py`
- `backend/sql/add_indexes.sql`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/*.py`
- `render.yaml`
- `frontend/vercel.json`
- `.github/workflows/security-ci.yml`
- `.github/workflows/production-smoke.yml`
- `docs/STAGING.md`
- `docs/MONITORING.md`
- `docs/RUNBOOK_INDEX.md`
- `docs/INCIDENT_RESPONSE.md`
- `docs/OPERATIONS_CALENDAR.md`
- `docs/MAINTENANCE_LOG.md`
- `docs/PRIVACY_DATA.md`
- `docs/PRIVACY_NOTICE_DRAFT.md`
- `docs/RETENTION.md`
- Dependency lock/manifests when the change installs, removes, or upgrades packages: `backend/requirements.txt`, `backend/requirements-dev.txt`, `frontend/package.json`, `frontend/package-lock.json`.
- Future migration files, backup scripts, and restore scripts.
- `docs/BACKUP_RESTORE.md`

## 12. Recommended Phase Roadmap

### Phase 2: Alembic Migration Setup

- Status: initial local Alembic baseline is complete.
- Goal: add controlled database migration discipline without changing production data.
- Likely files changed: `backend/requirements.txt` or `backend/requirements-dev.txt`, `alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/*.py`, possibly docs.
- Risk level: medium.
- Touches database: yes, but setup should start with local/test inspection only. Do not run production migrations.
- Free/feasible tools: yes, Alembic is free.
- Approval question: "Do you approve Phase 2 to add Alembic configuration and a local baseline migration only, without running production migrations or changing auth/security/model behavior?"

### Phase 3: Backup And Restore Process

- Status: backup/restore runbook and ignored local backup paths are complete; no production backup has been taken by Codex.
- Goal: document safe backups before production schema changes.
- Likely files changed: `docs/BACKUP_RESTORE.md`, optional `scripts/` or `backend/scripts/` backup helpers, `.gitignore` entries for local backup artifacts if needed.
- Risk level: medium for backup, high for restore.
- Touches database: backup is read-only; restore writes data and must only target local/staging unless explicitly approved.
- Free/feasible tools: yes, PostgreSQL tools such as `pg_dump` and `pg_restore` are free; provider limits should be checked before relying on free tiers.
- Approval question: "Do you approve Phase 3 to create backup/restore documentation and local-safe scripts, with no production restore and no destructive database action?"

### Phase 4: Frontend Testing

- Status: initial Vitest and Testing Library setup is complete with focused tests for error parsing, API auth handling, and password visibility.
- Goal: add beginner-friendly frontend confidence around auth, protected routes, transactions, analytics, and imports.
- Likely files changed: `frontend/package.json`, `frontend/package-lock.json`, `frontend/vitest.config.*` or similar, `frontend/src/**/*.test.jsx`, optional testing setup file.
- Risk level: low to medium.
- Touches database: no, unless later end-to-end tests call a backend.
- Free/feasible tools: yes, Vitest and React Testing Library are free; Playwright can be added later if wanted.
- Approval question: "Do you approve Phase 4 to add a free frontend test setup and focused tests, without changing production app behavior?"

### Phase 5: Staging Setup

- Status: staging workflow documentation is complete; provider resources are not created yet.
- Goal: create a safer pre-production deployment path.
- Likely files changed: `docs/STAGING.md`, deployment docs, possibly Render/Vercel project settings, possibly `render.yaml` only after a careful plan.
- Risk level: medium.
- Touches database: yes if a staging PostgreSQL database is created; it must be separate from production.
- Free/feasible tools: feasible, but provider free-tier limits and current pricing should be checked before committing to a staging design.
- Approval question: "Do you approve Phase 5 to design a separate staging environment using separate environment variables and a separate database, without changing production settings yet?"

### Phase 6: Optional Monitoring

- Status: free-first monitoring documentation and a GitHub Actions production smoke check are complete.
- Goal: add low-cost visibility into uptime, deploy health, and application errors.
- Likely files changed: `docs/MONITORING.md`, optional GitHub Actions scheduled smoke check, optional logging/error-reporting setup if approved.
- Risk level: low for documentation and health checks, medium if adding an error-reporting SDK.
- Touches database: normally no.
- Free/feasible tools: yes for Render/Vercel logs and GitHub Actions checks; third-party free tiers should be checked before adoption.
- Approval question: "Do you approve Phase 6 to add a free or free-tier monitoring plan and optional health-check automation, without adding paid services or sending user data to a new vendor?"

### Phase 7: Privacy And Data Lifecycle

- Status: privacy/data lifecycle runbook, backend account deletion cleanup tests, self-serve user data export, draft privacy notice, and draft retention plan are implemented.
- Goal: make user data handling, deletion expectations, export planning, retention caveats, and AI/Codex safety rules explicit before many real users depend on the app.
- Likely files changed: `docs/PRIVACY_DATA.md`, `docs/PRIVACY_NOTICE_DRAFT.md`, `docs/RETENTION.md`, `docs/SECURITY_CHECKLIST.md`, `docs/QA_CHECKLIST.md`, `backend/app/routes/user_routes.py`, `backend/app/schemas.py`, `backend/app/services/user_export_service.py`, backend tests, frontend profile page, and i18n copy.
- Risk level: low for draft docs, medium for export implementation, high for any production manual export.
- Touches database: export uses read-only current-user queries; no production export by Codex.
- Free/feasible tools: yes.
- Approval question for future hardening: "Do you approve tightening the user data export coverage with additional tests and documentation only, without changing production data or deletion behavior?"

### Phase 8: Privacy Launch Review

- Status: draft privacy notice and draft retention plan exist, but they are not legal-approved public policies.
- Goal: convert draft privacy/retention language into publishable user-facing docs after verifying provider settings, enabled vendors, and production behavior.
- Likely files changed: final public privacy page/document, `docs/PRIVACY_NOTICE_DRAFT.md`, `docs/RETENTION.md`, `docs/PRIVACY_DATA.md`, and possibly frontend route/page copy if a privacy page is added.
- Risk level: medium because privacy language can create legal or user-trust obligations.
- Touches database: no.
- Free/feasible tools: yes, but legal review may not be free.
- Approval question: "Do you approve reviewing provider settings and turning the draft privacy notice into a publishable privacy page, without changing app data behavior or exporting production data?"

### Phase 9: Incident Response Drill

- Status: incident response runbook exists; no live drill has been performed.
- Goal: practice a harmless simulated outage or leaked-secret scenario so rollback, communication, and evidence capture are familiar before a real incident.
- Likely files changed: `docs/INCIDENT_RESPONSE.md`, `docs/MONITORING.md`, `docs/QA_CHECKLIST.md`, and possibly a private local note outside git for drill observations.
- Risk level: low if simulated only, medium if provider dashboards are touched.
- Touches database: no.
- Free/feasible tools: yes.
- Approval question: "Do you approve running a simulated incident drill using only test data and documentation, without changing production settings, secrets, or database state?"

### Phase 10: Operations Cadence

- Status: operations calendar exists; the routine has not been practiced over multiple weeks.
- Goal: turn release, smoke-test, backup, logs, privacy, dependency, and incident-review tasks into a manageable solo-maintainer rhythm.
- Likely files changed: `docs/OPERATIONS_CALENDAR.md`, `docs/QA_CHECKLIST.md`, `docs/MONITORING.md`, and possibly docs for lessons learned.
- Risk level: low for documentation, medium if provider dashboards or production checks are involved.
- Touches database: no routine database writes; backup verification should follow `docs/BACKUP_RESTORE.md`.
- Free/feasible tools: yes.
- Approval question: "Do you approve using the operations calendar for a test-only weekly maintenance pass, without changing production settings, secrets, or database state?"
