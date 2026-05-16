# Security Audit Report

Smart Spending Analyzer defensive audit for the FastAPI backend, React frontend, PostgreSQL data model, smart import pipeline, and AI assistant.

## Critical Issues

### 1. Production secrets and reset links need strict handling

- Files: `backend/app/auth.py`, `backend/app/routes/auth_routes.py`, `.env.example`
- Why it matters: weak JWT secrets or reset links returned in production can let attackers guess tokens or take over accounts.
- Free fix: require `SECRET_KEY` in all environments, require a 32+ character secret in production, keep JWT payload minimal, and only return reset URLs outside production unless `EXPOSE_RESET_LINK_IN_RESPONSE=true`.
- Test to prove the fix: `backend/tests/test_security_hardening.py::AuthSecurityTest::test_forgot_password_does_not_expose_reset_url_in_production`

### 2. File import could exhaust memory or accept spoofed uploads

- Files: `backend/app/security.py`, `backend/app/routes/transaction_routes.py`, `backend/app/services/transaction_service.py`
- Why it matters: `await file.read()` on arbitrary files can consume server memory, and trusting filename/content-type alone lets hostile files reach PDF/image/CSV parsers.
- Free fix: stream uploads in chunks, enforce size limits, validate extension and file signatures, limit CSV rows, sanitize imported text, and return generic parser failures.
- Test to prove the fix: `backend/tests/test_security_hardening.py::SecurityRouteTest::test_upload_rejects_wrong_extension` and `test_upload_rejects_file_over_size_limit`

### 3. AI assistant must refuse secrets and cross-user requests

- Files: `backend/app/services/assistant_service.py`, `backend/app/services/llm_service.py`, `backend/app/routes/assistant_routes.py`
- Why it matters: prompt injection can ask the assistant to ignore instructions, reveal hidden prompts, leak secrets, or use another account.
- Free fix: add deterministic pre-model refusal for sensitive requests, strengthen the LLM system prompt, treat all user/history/import text as untrusted, and redact sensitive markers from model output.
- Test to prove the fix: `backend/tests/test_security_hardening.py::AssistantSecurityTest::test_assistant_refuses_prompt_injection_and_secret_requests`

## High Issues

### 1. Password hashing needed a stronger default

- Files: `backend/app/auth.py`, `backend/app/schemas.py`, `backend/app/routes/user_routes.py`
- Why it matters: the legacy PBKDF2 hash is acceptable but harder to tune and not the best modern default for new passwords.
- Free fix: use direct `bcrypt` hashing for new passwords while keeping legacy PBKDF2 verification so old users can still log in.
- Test to prove the fix: `backend/tests/test_security_hardening.py::AuthSecurityTest::test_weak_password_registration_is_rejected`

### 2. Login and import endpoints need abuse throttling

- Files: `backend/app/security.py`, `backend/app/main.py`
- Why it matters: auth, reset, assistant, and import endpoints are expensive or attack-prone.
- Free fix: add simple in-process rate limiting for login, register, forgot/reset password, assistant, and import routes. This is free and beginner-readable, but production can later move to Redis-backed limits if needed.
- Test to prove the fix: `backend/tests/test_security_hardening.py::AuthSecurityTest::test_login_rate_limit_blocks_repeated_attempts`

### 3. CORS was too permissive for production

- Files: `backend/app/main.py`, `backend/app/security.py`, `.env.example`
- Why it matters: wildcard or localhost origins in production weaken browser isolation, especially with credentials enabled.
- Free fix: use `ALLOWED_ORIGINS`/`FRONTEND_URL`, strip wildcard origins, and only allow localhost in development.
- Test to prove the fix: `backend/tests/test_security_hardening.py::CorsSecurityTest::test_production_cors_rejects_unknown_origin`

### 4. Ownership checks must stay covered by tests

- Files: `backend/app/routes/account_routes.py`, `backend/app/routes/transaction_routes.py`, `backend/app/routes/budget_routes.py`, `backend/app/routes/analytics_routes.py`
- Why it matters: a broken object-level authorization bug would let User A read, edit, or delete User B data by guessing ids.
- Free fix: routes already mostly filter by `current_user.id`; added regression tests for account, transaction, and budget ownership.
- Test to prove the fix: `backend/tests/test_security_hardening.py::SecurityRouteTest::test_user_a_cannot_use_user_b_account_for_transaction`, `test_user_a_cannot_update_user_b_account`, and `test_user_a_cannot_delete_user_b_budget`

## Medium Issues

### 1. Input validation needed tighter bounds

- Files: `backend/app/schemas.py`
- Why it matters: unbounded strings and unrealistic values can cause bad analytics, weird UI behavior, and avoidable database noise.
- Free fix: add stronger password policy, positive transaction amounts, max lengths for assistant messages/import previews, and list limits for import preview confirmation.
- Test to prove the fix: `backend/tests/test_security_hardening.py::AuthSecurityTest::test_weak_password_registration_is_rejected`

### 2. Production error details should stay generic

- Files: `backend/app/main.py`, `backend/app/routes/transaction_routes.py`
- Why it matters: returning raw exception text can reveal stack traces, parser internals, or implementation details.
- Free fix: log unexpected errors server-side and return generic user-facing messages.
- Test to prove the fix: covered by import rejection tests and manual malformed-file testing.

### 3. Security headers were missing

- Files: `backend/app/security.py`, `backend/app/main.py`
- Why it matters: browser security headers reduce MIME sniffing, clickjacking, referrer leakage, and accidental framing.
- Free fix: add `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, a conservative API CSP, and HSTS only in production HTTPS.
- Test to prove the fix: manual `curl -I` or browser network inspection after deploy.

## Low Issues

### 1. Frontend token storage is convenient but not ideal

- Files: `frontend/src/App.jsx`, `frontend/src/services/api.js`, `frontend/src/pages/LoginPage.jsx`, `frontend/src/pages/RegisterPage.jsx`
- Why it matters: JWT in `localStorage` is vulnerable if an XSS bug ever appears.
- Free fix: keep React escaping user-controlled text, avoid `dangerouslySetInnerHTML`, and plan a future move to secure HTTP-only cookies when backend/frontend deployment is ready.
- Test to prove the fix: `rg -n "dangerouslySetInnerHTML" frontend` should remain empty.

### 2. Free dependency/security checks were not automated

- Files: `.github/workflows/security-ci.yml`, `backend/requirements-dev.txt`, `backend/requirements.txt`, `backend/bandit.yaml`
- Why it matters: vulnerable packages and unsafe Python patterns can slip in quietly.
- Free fix: add GitHub Actions for backend tests, frontend build, `pip-audit`, `npm audit`, and `bandit`; upgrade vulnerable `pypdf` and `python-multipart` versions.
- Test to prove the fix: `python -m pip_audit -r requirements.txt --cache-dir .pip-audit-cache` reports no known vulnerabilities.

### 3. Secrets should be scanned locally before public sharing

- Files: `.gitignore`, `.env.example`, repository history
- Why it matters: database URLs, API keys, and JWT secrets must never be committed.
- Free fix: keep `.env` ignored, use placeholders in `.env.example`, and run free local `gitleaks detect --source .` before major releases.
- Test to prove the fix: `git status --ignored` should show `.env` ignored; `gitleaks` should return no committed secrets.

## Notes On Remaining Work

- The in-process rate limiter is good free protection for a single Render worker. If the backend later scales horizontally, use a shared store such as Redis or database-backed counters.
- Password reset currently generates a token but does not send email. For production, use a transactional email provider or your own SMTP and keep reset URLs out of API responses.
- The AI assistant is hardened so it cannot access the database directly and only receives already-filtered context. Keep that pattern when adding future assistant actions.
- Continue adding ownership tests for every new id-based route before launch.
