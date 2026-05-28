# Smart Spending Analyzer

[![Security CI](https://github.com/pooriaaj/smart-spending-analyzer/actions/workflows/security-ci.yml/badge.svg?branch=main)](https://github.com/pooriaaj/smart-spending-analyzer/actions/workflows/security-ci.yml)
[![Production Smoke Check](https://github.com/pooriaaj/smart-spending-analyzer/actions/workflows/production-smoke.yml/badge.svg)](https://github.com/pooriaaj/smart-spending-analyzer/actions/workflows/production-smoke.yml)

A full-stack financial intelligence web application that helps users track, analyze, and improve their spending behavior.

Live Demo:
Frontend: https://smart-spending-analyzer.vercel.app  
Backend API: https://smart-spending-analyzer.onrender.com

GitHub:
Repository: https://github.com/pooriaaj/smart-spending-analyzer
Default branch: `main`

---

## Overview

Smart Spending Analyzer is more than a transaction tracker.  
It is designed as a foundation for an intelligent financial assistant that:

- Tracks income and expenses
- Automatically imports transaction data
- Detects spending patterns
- Identifies overspending risks
- Provides personalized financial insights
- Acts as an AI-powered financial assistant

---

## Features

### Core System
- User authentication with HttpOnly session cookies
- Secure PostgreSQL database
- FastAPI backend with structured services
- React frontend with modern UI

### Transactions
- Manual transaction creation/edit/delete
- CSV import with:
  - encoding handling
  - duplicate detection
  - validation system
- PDF statement import with:
  - text-based PDF parsing
  - screenshot/scanned PDF page rendering
  - optional free local Tesseract OCR fallback
  - optional OpenAI vision OCR fallback

### Analytics
- Monthly financial summaries
- Category breakdown
- Top expense category detection
- Trend analysis (month-over-month)
- Overspending alerts
- Recent transactions tracking

### Smart Assistant
- Natural-language financial queries
- Context-aware responses
- Spending insights and recommendations
- Finance questions use the user's filtered transaction, budget, account, recurring-charge, and simulator data
- Non-finance learning/link questions can use the AI provider when enabled, otherwise they fall back to safe public-resource links
- Off-topic questions are answered by the AI provider when available or politely redirected when the app is in rule-based mode
- Actionable suggestions:
  - navigate to analytics
  - filter transactions
  - review categories
  - open relevant external learning resources

### Smart Categorization
- Rule-based transaction classification
- Learned merchant/category memory from confirmed edits
- Optional merchant enrichment for unknown statement names
- Bulk categorization suggestions
- Confidence scoring
- Apply suggestions automatically

### Data Simulation
- Realistic financial data generator:
  - salary
  - groceries
  - transport
  - subscriptions
  - spikes (travel, shopping)
- Used for testing analytics and assistant logic

---

## Tech Stack

### Backend
- FastAPI
- SQLAlchemy
- PostgreSQL (Render)
- HttpOnly cookie authentication backed by signed JWTs

### Frontend
- React (Vite)
- Recharts (data visualization)
- Axios

### Testing And CI
- Backend tests run through GitHub Actions.
- Frontend tests use Vitest, jsdom, and Testing Library.
- Current focused frontend coverage includes API auth handling, protected route gates, login, registration, forgot/reset password, transaction form create/edit/category suggestion behavior, profile export, password visibility, and error helpers.
- GitHub workflows:
  - `.github/workflows/security-ci.yml`
  - `.github/workflows/production-smoke.yml`

### Deployment
- Backend: Render
- Frontend: Vercel

### Runtime Health Checks
- `/live` returns 200 when the API process is running.
- `/ready` returns 200 only when the API can reach the database.
- `/health` mirrors readiness for backward compatibility.
- Render is configured to use `/ready` so bad database connectivity blocks unhealthy deploys.

Runtime scaling knobs:
- `WEB_CONCURRENCY` controls Uvicorn workers in production. Start with `1` on small Render instances, then raise it when CPU and database pool size can support it.
- `UVICORN_TIMEOUT_KEEP_ALIVE` controls idle HTTP keep-alive seconds.
- `UVICORN_GRACEFUL_TIMEOUT` controls graceful shutdown time during deploys.

### Free Scanned PDF OCR
- Text-based statement PDFs work without OCR.
- Scanned or screenshot-style PDFs are rendered with PyMuPDF, then read with Tesseract OCR when available.
- For Render, deploy the backend with Docker so the service can install the Tesseract system package from `backend/Dockerfile`.
- OpenAI vision OCR remains optional as a stronger paid fallback.

Render setup for free OCR:
- The repository includes `render.yaml` with `runtime: docker`, `dockerfilePath: backend/Dockerfile`, and `dockerContext: backend`.
- If your existing Render service still says Tesseract was not found, the service is still using the native Python runtime.
- In Render, switch/sync the backend service to Docker using the repository blueprint, or create a new Docker web service from this repo with Root Directory set to `backend`.
- Keep your existing backend environment variables, especially `DATABASE_URL`, `SECRET_KEY`, `FRONTEND_URL`, and auth settings.

---

## Architecture

The backend follows a service-based architecture:
routes -> services -> database

This structure improves:
- maintainability
- scalability
- separation of concerns

---

## Key Engineering Highlights

### Performance Optimization
- SQL aggregation instead of Python loops
- Database indexing for:
  - owner_id
  - date
  - category
- bulk insert for CSV imports

### Clean Backend Refactor
- Reduced 1000+ line route files into service layer
- Modular analytics system
- Reusable query builder

### Smart Assistant Logic
- Intent classification for finance, merchant, budget, simulator, education, and off-topic prompts
- Context-aware responses with saved assistant history per account scope
- Multi-source reasoning:
  - summary
  - trends
  - alerts
  - recent data
  - budgets
  - recurring charges
  - merchant/category learning
- Guardrails for prompt injection, secret redaction, daily AI usage limits, and safe rule-based fallback
- Optional model-backed answers through OpenAI or an OpenAI-compatible local provider

---

## Security

- Bcrypt password hashing with legacy PBKDF2 verification for older accounts
- HttpOnly, Secure production auth cookies backed by signed JWTs
- CSRF Origin checks for unsafe cookie-authenticated requests
- Strict CORS origins with credentials support
- Request size limits and upload file signature checks
- Rate limits on auth, assistant, and import endpoints
- Security headers on backend and Vercel frontend responses
- Environment-based configuration with `.env` excluded from repository

---

## Operational Docs

Start with `docs/RUNBOOK_INDEX.md` for the current operations map.

Key docs:
- `docs/ENVIRONMENT.md` for local, Render, and Vercel environment setup.
- `docs/DEPLOYMENT.md` for deployment, smoke tests, and rollback basics.
- `docs/RELEASE_PROCESS.md` for release checks and push flow.
- `docs/CI_REVIEW.md` for GitHub Actions review from the browser or optional GitHub CLI.
- `docs/SECURITY_CHECKLIST.md` for secret, GitHub, provider, user data, backup, and Codex safety.
- `docs/QA_CHECKLIST.md` for manual product checks.

---

## How to Run Locally

### Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

To enable the model-backed assistant locally, copy `.env.example` to `backend/.env`, set `USE_LLM_ASSISTANT=true`, and add either:
- `OPENAI_API_KEY` for OpenAI, or
- `USE_LOCAL_LLM=true` with a local OpenAI-compatible endpoint such as Ollama.

Without those settings, the assistant still works through the safe rule-based backend paths.


### Frontend
```powershell
cd frontend
npm install
npm run dev
```

Useful frontend checks:

```powershell
npm test
npm run lint
npm run build
```


---

## Environment Variables

Use `.env.example` and `docs/ENVIRONMENT.md` for environment variable names and setup guidance.

Do not commit real database URLs, JWT secrets, API keys, passwords, tokens, or production credentials. Frontend `VITE_` variables are visible in browser builds and must not contain secrets.

---

## Future Roadmap

- AI/LLM-powered assistant (OpenAI / local model)
- Bank API integration (Plaid or similar)
- Automatic transaction syncing
- Advanced anomaly detection
- Budget planning system
- Mobile app version

---

## Author

Mohammadreza Alijani  
Toronto, Canada  

GitHub: https://github.com/pooriaaj

---

## Final Note

This project demonstrates:

- Full-stack development
- Data engineering & analytics
- Backend architecture design
- Product thinking
- AI system design foundations
