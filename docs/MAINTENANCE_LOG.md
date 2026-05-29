# Maintenance Log

Use this file for safe, non-secret maintenance summaries. Do not record real user data, real secrets, database URLs, access tokens, reset links, private provider logs, or raw exports here.

## 2026-05-28 Profile Safety Test Expansion

Scope: expanded profile frontend tests for email update, anonymous community learning toggle, password change, delete confirmation guarding, and existing data export behavior.

Commit checked before expansion: `e69617971313409db188f0156337896f738056be`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.
- No real account was deleted; tests use mocked frontend service responses only.

### Verification

- Profile page focused test: `1 file passed`, `5 tests passed`.
- Frontend tests: `16 files passed`, `48 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.

### Notes

- Tests use fake profile, password, export, learning, and deletion responses only.
- Manual QA is still required for live backend validation, real account deletion lifecycle, session cleanup, duplicate email behavior, and production data export contents.

## 2026-05-28 Assistant Test Expansion

Scope: added focused frontend tests for assistant provider status, saved history, scoped question payloads, response details/actions/follow-ups, and clearing saved conversation history.

Commit checked before expansion: `ee953d1ab62a573a158b59d166797b96bd6026a6`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.
- No real AI provider calls were made; tests use mocked frontend service responses only.

### Verification

- Assistant page focused test: `1 file passed`, `3 tests passed`.
- Frontend tests: `16 files passed`, `44 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.

### Notes

- Tests use fake assistant status, history, and response data only.
- Manual QA is still required for live provider behavior, prompt-injection refusal behavior, real financial-data grounding, and production assistant history.

## 2026-05-28 Import Review Test Expansion

Scope: added focused frontend tests for import account-required guarding, statement table review, duplicate removal, category approval, and confirm-preview import behavior.

Commit checked before expansion: `1f97003d4fe9fa9944594108b2ca20fff16ddd46`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.
- No real bank statement files were read; tests use fake in-memory `File` objects only.

### Verification

- Import page focused test: `1 file passed`, `2 tests passed`.
- Frontend tests: `15 files passed`, `41 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.

### Notes

- Tests use mocked frontend services, fake preview rows, and fake upload files only.
- Manual QA is still required for real CSV/PDF parsing, OCR/receipt drafts, multi-file batches, large statements, duplicate matching accuracy, and production backend behavior.

## 2026-05-28 Analytics Test Expansion

Scope: added focused frontend tests for analytics summary display, trends/insights/alerts/account comparison display, filter request behavior, date presets, and category drilldown navigation.

Commit checked before expansion: `639b554fb87742888529d800cdf7be7ccd619008`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.

### Verification

- Analytics page focused test: `1 file passed`, `3 tests passed`.
- Frontend tests: `14 files passed`, `39 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.

### Notes

- Tests use mocked frontend services, mocked chart components, and fake analytics/transaction data only.
- Manual QA is still required for real chart rendering, mobile layout, backend-derived analytics correctness, account-scoped analytics, and production data behavior.

## 2026-05-28 Transaction Ledger Test Expansion

Scope: added focused frontend tests for transaction ledger loading, server-side filter request behavior, table edit/save, and delete refresh behavior.

Commit checked before expansion: `bf4225266e3d22cdd685b4fbb4a836cd29b662bb`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.

### Verification

- Transactions page focused test: `1 file passed`, `3 tests passed`.
- Frontend tests: `13 files passed`, `36 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.

### Notes

- Tests use mocked frontend services and fake transaction data only.
- Manual QA is still required for real backend pagination, account-scoped filtering, bulk category actions, fresh-start safety, import reconciliation, and mobile layout.

## 2026-05-28 Dashboard Test Expansion

Scope: added focused frontend tests for dashboard summary display, budget/future outlook display, recent transaction filters, and manual transaction add behavior.

Commit checked before expansion: `13d72640af9e258633a278872c5d6b6e43e4bef4`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.

### Verification

- Dashboard focused test: `1 file passed`, `3 tests passed`.
- Frontend tests: `12 files passed`, `33 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.

### Notes

- Tests use mocked frontend services and fake account, transaction, budget, and simulator data only.
- Manual QA is still required for full dashboard confidence with real accounts, imported data, mobile layout, and production backend behavior.

## 2026-05-28 Account Selector Test Expansion

Scope: added focused frontend tests for account selector loading, persistence, all-account behavior, and single-account fallback.

Commit checked before expansion: `c89f82899029408b582ceb5e4d136bba1293f014`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.

### Verification

- Frontend tests: `11 files passed`, `30 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.
- `git diff --check`: passed before staging.

### Notes

- Tests use mocked frontend services and fake account data only.
- Manual QA is still required for full account-scoped dashboard, analytics, transaction, assistant, and budget confidence.

## 2026-05-28 Transaction Form Test Expansion

Scope: added focused frontend tests for transaction form create, edit, and category suggestion behavior.

Commit checked before expansion: `b2ff5c148cc0478a7460b46322c7fc7232ea3faa`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No backend code was changed.
- No database migrations were run.
- No production user data was exported.

### Verification

- Frontend tests: `10 files passed`, `26 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- `git diff --check`: passed before staging.

### Notes

- Tests use mocked frontend services and fake transaction data only.
- Manual QA is still required for full transaction-page create/edit/delete confidence.

## 2026-05-28 Checklist And README Refresh

Scope: refreshed README, GitHub/CI docs, QA checklist, security checklist, release process, runbook index, and Codex context after the frontend auth test expansion.

Commit checked before refresh: `d03cb19848a75f7ef2920d651ef4725f548face6`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No database migrations were run.
- No backup or restore commands were run.
- No production user data was exported.
- No GitHub Actions secrets or provider dashboard settings were changed.

### Updates

- README now includes GitHub workflow badges, repository/default-branch details, testing/CI summary, and safer fenced local commands.
- `docs/QA_CHECKLIST.md` now includes automated checks and current frontend automated coverage.
- `docs/SECURITY_CHECKLIST.md` now includes automated regression safety items.
- `docs/CI_REVIEW.md` now includes repository/default-branch details and the current frontend test surface.
- `docs/RELEASE_PROCESS.md` now reminds future sessions to update README, Codex context, and relevant checklists when readiness changes.
- `docs/RUNBOOK_INDEX.md` now points to the README as a public overview and docs entry point.
- `docs/CODEX_CONTEXT.md` now reflects the latest GitHub and frontend test state.

### Verification

- Frontend tests: `9 files passed`, `23 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.
- `git diff --check`: passed.

### Not Done In This Pass

- Backend tests were not rerun because no backend code changed.
- GitHub Actions browser review was not completed from Codex.
- Provider dashboard settings and logs were not reviewed.

## 2026-05-28 Release Dry-Run Review

Scope: safe dry run of `docs/RELEASE_PROCESS.md` and `docs/RUNBOOK_INDEX.md` after the operations documentation commits.

Commit checked: `94d1570be598bdfdcd71bb17170786c66ec35828`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No database migrations were run.
- No backup or restore commands were run.
- No production user data was exported.
- No provider dashboard settings were changed.

### Release Dry-Run Result

- Working tree was clean at the start.
- Latest local branch matched `origin/main`.
- `docs/RELEASE_PROCESS.md` and `docs/RUNBOOK_INDEX.md` were reviewed as the release entry points.
- `git diff --check` passed.
- This was treated as a docs-only release dry run; backend and frontend behavior tests were not required for this pass.

### GitHub And Deploy Status

- GitHub connector combined status for the checked commit reported Vercel success.
- GitHub connector returned no workflow runs for the checked commit.
- `gh` CLI was not installed, so full GitHub Actions history review was not completed from the terminal.

### Public Smoke Checks

- Vercel frontend: HTTP 200.
- Render `/live`: HTTP 200.
- Render `/ready`: HTTP 200.
- Note: Render health checks again took about one minute, consistent with a free-tier/cold-start style delay.

### Not Done In This Pass

- Full backend test suite was not rerun.
- Frontend tests, lint, and build were not rerun because no application code changed.
- Provider dashboard logs were not reviewed.
- Manual browser QA with a live test account was not performed.
- Backup creation and restore verification were not performed.

### Follow-Ups

- Install and authenticate GitHub CLI or use the GitHub Actions UI for fuller release review.
- Keep watching repeated Render cold-start latency during future smoke checks.
- Use `docs/RELEASE_PROCESS.md` before the next non-docs release.

## 2026-05-28 Weekly Test-Only Maintenance Pass

Scope: first pass through `docs/OPERATIONS_CALENDAR.md` using local checks and public health endpoints only.

Commit checked: `37524a63a0274e7af45214087383990867be5e46`

### Safety Boundaries

- No `.env` values were read or printed.
- No production settings were changed.
- No database migrations were run.
- No backup or restore commands were run.
- No production user data was exported.
- No provider dashboard settings were changed.

### Repo And Hygiene

- Working tree was clean at the start.
- Root environment files found by name only: `.env.example`.
- Backend local environment file found by name only: `backend/.env`.
- Frontend environment files found by name only: none.
- Local backup directories found at repo root: none.
- `gh` CLI was not installed, so full GitHub Actions history review was not completed from the terminal.

### GitHub And Deploy Status

- GitHub connector combined status for the checked commit reported Vercel success.
- GitHub connector returned no workflow runs for the checked commit.
- Follow-up: use the GitHub Actions UI or install/authenticate `gh` for fuller weekly Actions review.

### Public Smoke Checks

- Vercel frontend: HTTP 200.
- Render `/live`: HTTP 200.
- Render `/ready`: HTTP 200.
- Note: Render health checks took about one minute, consistent with a free-tier/cold-start style delay. Treat repeated slow warm responses as a monitoring item, not an incident by itself.

### Local Verification

- Backend focused user/privacy route tests: `10 tests OK`.
- Frontend tests: `4 files passed`, `10 tests passed`.
- Frontend lint: passed.
- Frontend build: passed.
- Frontend high-severity audit: `0 vulnerabilities`.
- `git diff --check`: passed.

### Not Done In This Pass

- Full backend test suite was not rerun; reserve it for monthly checks, backend behavior changes, or pre-release verification.
- Provider dashboard logs were not reviewed because that requires dashboard access and should not expose secrets or user data.
- Manual browser QA with a live test account was not performed.
- Backup creation and restore verification were not performed because no migration or production database work was planned.

### Follow-Ups

- Decide whether to install and authenticate GitHub CLI for smoother weekly Actions review.
- Keep watching Render health-check latency during weekly smoke checks.
- Run full backend tests in the next monthly maintenance pass or before any backend behavior release.
- Perform manual browser QA with a disposable test account before broad beta testing.
