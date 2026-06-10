# Smart Spending Analyzer — Claude Context

## Project Overview

**Product:** Smart Spending Analyzer / Zero2Asset  
**Domain:** zero2asset.com / www.zero2asset.com  
**Type:** Full-stack personal finance SaaS  

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite + Mantine UI + react-router-dom |
| Backend | FastAPI + SQLAlchemy |
| Database | PostgreSQL (prod), SQLite (tests) |
| Auth | JWT-backed HttpOnly cookies, bcrypt, CSRF origin checks |
| Frontend deploy | Vercel |
| Backend deploy | Render (Docker) |
| DB deploy | Render PostgreSQL |

## Repo Layout

```
frontend/          React app (Vite)
  src/
    pages/         One file per route page
    components/    Shared UI components
    services/      api.js (axios), accountStorage.js
    i18n/          LanguageContext.jsx (en + fr)
    utils/         Utility helpers
backend/
  app/
    routes/        FastAPI routers (7 modules)
    services/      Business logic (24 modules)
    models.py      All 13 SQLAlchemy models
    main.py        App factory, middleware stack
    security.py    CSRF, rate limit, headers, CORS
    database.py    Engine + session factory
  tests/           pytest tests
  alembic/         Migrations (baseline only)
  requirements.txt All pinned deps
  Dockerfile       python:3.12-slim
docs/              Operations, deployment, security docs
scripts/           production_smoke_check.py
.github/workflows/ security-ci.yml, production-smoke.yml
```

## Routing

- `/analytics` — primary dashboard (not `/dashboard`)
- `/dashboard` and `/money-map` redirect to `/analytics`
- `/` — login (or redirect to `/analytics` if authenticated)
- All protected routes are lazy-loaded via React.lazy + Suspense
- 404 catch-all route renders `NotFoundPage`

## Key Files

| Purpose | Path |
|---|---|
| Frontend entry / routing | `frontend/src/App.jsx` |
| Axios client | `frontend/src/services/api.js` |
| All DB models | `backend/app/models.py` |
| Backend entry | `backend/app/main.py` |
| Security middleware | `backend/app/security.py` |
| Env var reference | `docs/ENVIRONMENT.md` |
| Deployment guide | `docs/DEPLOYMENT.md` |
| Project status | `docs/PHASE_STATUS.md` |

## Safety Rules (non-negotiable)

1. Never expose, print, or commit secret values (keys, tokens, DB URLs, JWT secrets)
2. Never modify `.env` files without explicit user instruction
3. Never run production migrations
4. Never drop tables or make destructive DB changes without explaining risk first
5. Never change auth, security, DB models, or API contracts without explaining risk first
6. Work incrementally — no broad rewrites
7. Inspect current state before editing — do not assume this file is up to date
8. Mention env variable **names** only, never values

## Design System

- **Palette:** navy (#1a2b4a) / emerald / white / soft gray
- **Theme:** Professional fintech SaaS — clean light theme, no childish elements
- **UI library:** Mantine — use Mantine components, not raw HTML where possible
- **Global styles:** `frontend/src/index.css` (9k lines, CSS custom properties)
- No fake financial data, no internal/admin tools on normal user pages

## Backend Conventions

- All HTTP exceptions use `HTTPException(status_code=..., detail=...)`
- All error responses include `request_id` for traceability
- Validation errors are normalized via `build_validation_error_response()`
- Services own business logic; routes own HTTP contract
- Logging: structured text (`%(asctime)s | %(levelname)s | %(name)s | %(message)s`)

## Frontend Conventions

- All user-facing strings go through `t()` from `useLanguage()` (i18n)
- Protected pages wrap with `<ProtectedRoute>` + `<AuthenticatedLayout>`
- API calls go through `src/services/api.js` (axios with 30s timeout)
- Auth errors handled via `handleApiAuthError(error, navigate)`
- Mantine `notifications` for user feedback toasts

## CI/CD

- `security-ci.yml` — runs on PR + push to main: pytest, pip-audit, bandit, npm audit, npm test, npm run build
- `production-smoke.yml` — daily cron: checks /live, /ready, /health on production
- Push and deploy only when user explicitly asks

## Known Open Risks

- Alembic production migration workflow not yet automated
- Frontend test coverage intentionally small
- Staging environment not deployed
- `AnalyticsPage` bundle ~411kB (expected for Recharts, not a blocker)
