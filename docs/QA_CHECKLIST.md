# QA Checklist

Use this checklist before important releases and after production deploys. Prefer a dedicated test account and safe sample data.

For recurring weekly/monthly maintenance, use `docs/OPERATIONS_CALENDAR.md`.

## Automated Checks

- [ ] For frontend changes, run `npm test` from `frontend`.
- [ ] For frontend changes, run `npm run lint` from `frontend`.
- [ ] For frontend changes, run `npm run build` from `frontend`.
- [ ] For backend changes, run focused backend tests for the changed area.
- [ ] Before risky backend releases, run the full backend test suite.
- [ ] Run `git diff --check` before committing.
- [ ] Confirm GitHub Actions `Security CI` passes for the pushed commit.
- [ ] Confirm Vercel deployment status is successful for the pushed commit.

Current focused frontend automated coverage includes API auth handling, protected-route auth gates, account selector/account-scope behavior, dashboard summary/recent-filter/manual-add behavior, transaction ledger filter/edit/delete behavior, analytics summary/filter/drilldown behavior, import account-gate/table-review/confirm behavior, assistant status/history/scoped-question behavior, login, registration, forgot/reset password, transaction form create/edit/category suggestion behavior, profile export/update/password/learning/delete-guard behavior, password visibility, and error helpers. Manual QA is still required for full product confidence.

## Auth

- [ ] Register with a new email and strong password.
- [ ] Registration sets the logged-in session.
- [ ] Duplicate registration is rejected safely.
- [ ] Login works with the registered account.
- [ ] Login rejects the wrong password.
- [ ] Logout clears the session.
- [ ] Protected routes redirect when logged out.
- [ ] Password reset request shows a safe generic message.
- [ ] Reset password works in the intended environment.
- [ ] Auth-gated routes redirect logged-out users to login.
- [ ] Logged-in users are routed away from the public login page to analytics.

## Protected Navigation

- [ ] `/transactions` requires login.
- [ ] `/analytics` requires login.
- [ ] `/assistant` requires login.
- [ ] `/profile` requires login.
- [ ] `/import` requires login.
- [ ] `/budgets` requires login.
- [ ] Account selector loads account options and preserves the intended account scope.

## Transactions

- [ ] Add an income transaction.
- [ ] Add an expense transaction.
- [ ] Edit amount, category, description, date, type, and account when available.
- [ ] Category suggestion fills a sensible category for a transaction description.
- [ ] Delete a transaction.
- [ ] Confirm totals update after create/edit/delete.
- [ ] Confirm another user's data is not visible from the current account.

## Dashboard And Analytics

- [ ] Dashboard or analytics summary loads.
- [ ] Monthly summary values are reasonable.
- [ ] Category breakdown renders.
- [ ] Recent transactions render.
- [ ] Filters change the displayed results.
- [ ] Account-scoped views show the expected account data.
- [ ] Switching between all accounts and one account changes the scope as expected.
- [ ] Budget and simulator surfaces load if present in the current UI.

## Import Flow

- [ ] Manual transaction flow still works.
- [ ] CSV import accepts a valid file.
- [ ] CSV import rejects invalid or oversized files safely.
- [ ] PDF statement import accepts a valid text-based PDF when available.
- [ ] Import preview rows can be reviewed before confirmation.
- [ ] Duplicate detection or warnings are visible when expected.
- [ ] Confirmed import creates transactions with sensible categories and amounts.

## Assistant

- [ ] Assistant status loads.
- [ ] A finance question returns an answer based on the user's data.
- [ ] An account-scoped question respects the selected account.
- [ ] A secret-seeking or prompt-injection request is refused safely.
- [ ] Assistant history loads and can be cleared if available.

## Profile And Account Safety

- [ ] Profile page loads.
- [ ] Email update validates duplicates.
- [ ] Password change requires current password.
- [ ] Account deletion requires password confirmation.
- [ ] Community learning preference can be toggled if present.

## Privacy And Data Lifecycle

- [ ] `docs/PRIVACY_DATA.md` still matches the implemented account deletion, data export, and learning preference behavior.
- [ ] Account deletion with a wrong password is rejected safely.
- [ ] Account deletion with the required confirmation removes the session and redirects away from protected pages.
- [ ] A deleted test account cannot log back in.
- [ ] Data export with a wrong password is rejected safely.
- [ ] Data export with the current password downloads a JSON file for the current account.
- [ ] Data export does not include password hashes, reset token hashes, or another user's data.
- [ ] Draft privacy notice still matches the production app behavior and enabled vendors.
- [ ] Retention draft still matches provider settings, backups, logs, and export behavior.
- [ ] Test data and screenshots do not include real bank transactions or statement content.

## Mobile And Responsive Check

- [ ] Login/register screens work on mobile width.
- [ ] Navigation remains usable on mobile width.
- [ ] Transaction forms fit on mobile width.
- [ ] Analytics charts do not overflow the screen.
- [ ] Import review tables remain usable or scrollable.

## Backend Unavailable And Error Handling

- [ ] Frontend shows a useful error when the backend is unavailable.
- [ ] Forms do not crash when the API returns validation errors.
- [ ] Global error boundary catches unexpected frontend crashes.
- [ ] Browser console has no repeated uncaught errors in normal flows.

## Production Smoke Test

- [ ] Vercel frontend loads.
- [ ] Render `/live` responds.
- [ ] Render `/ready` responds with database readiness.
- [ ] Vercel deploy status is successful for the commit under test.
- [ ] GitHub Actions `Production Smoke Check` passes or has a clear known reason for failure.
- [ ] GitHub Actions `Security CI` passes or has a clear known reason for failure.
- [ ] If production smoke fails unexpectedly, follow `docs/INCIDENT_RESPONSE.md`.
- [ ] Register/login works on the production domain.
- [ ] Create/edit/delete transaction works.
- [ ] Analytics update after a transaction change.
- [ ] Logout works.
- [ ] Render logs show no unexpected errors during the smoke test.

## Staging Smoke Test

- [ ] Vercel staging preview loads.
- [ ] Render staging `/live` responds.
- [ ] Render staging `/ready` uses the staging database.
- [ ] Register/login works with a staging-only test account.
- [ ] Create/edit/delete transaction works with staging data.
- [ ] Import flow uses safe test files only.
- [ ] Staging does not point at production data.

## Incident Drill

- [ ] Read `docs/INCIDENT_RESPONSE.md` before broad launch.
- [ ] Confirm `docs/OPERATIONS_CALENDAR.md` has a cadence for the next drill.
- [ ] Simulate a failed deploy or broken health check using staging/test-only context.
- [ ] Simulate a leaked-secret response using fake variable names and no real values.
- [ ] Confirm rollback, evidence capture, and post-incident notes are understandable.
