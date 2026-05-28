# CI Review

Use this guide to review GitHub Actions after pushes, before releases, and during weekly maintenance.

Do not paste GitHub logs containing secrets, tokens, user data, or private provider details into docs, issues, screenshots, or AI prompts.

## Current Workflows

- Repository: `pooriaaj/smart-spending-analyzer`.
- Default branch: `main`.
- `Security CI`: runs on pull requests and pushes to `main`.
- `Production Smoke Check`: runs on a schedule and can be triggered manually.

`Security CI` is the main code-quality gate. It covers backend tests, Python dependency audit, Bandit static scan, frontend dependency audit, frontend tests, and frontend build.

`Production Smoke Check` verifies the deployed frontend and backend health endpoints using public URLs only.

## Current Frontend Test Surface

As of the current docs refresh, frontend tests cover:

- API base URL and 401 logout handling.
- Protected-route auth gates.
- Account selector loading, persistence, and all-account/single-account behavior.
- Dashboard summary, budget/future outlook display, recent filters, and manual add flow.
- Transaction ledger loading, server-filter requests, table edit/save, and delete refresh behavior.
- Analytics summary, trends/insights/alerts display, filter requests, and category drilldown navigation.
- Login success and failure behavior.
- Registration success, mismatch validation, and failure behavior.
- Forgot-password request success and failure behavior.
- Reset-password token, mismatch, success, and redirect behavior.
- Transaction form create, edit, and category suggestion behavior.
- Profile data export download behavior.
- Password visibility controls.
- API error/success message formatting.

Keep expanding this list toward transactions, import review, analytics filters, assistant flows, budgets, and responsive UI checks.

## Browser Review

Use this path when GitHub CLI is not installed or authenticated.

1. Open the GitHub repository.
2. Go to the `Actions` tab.
3. Open the latest workflow run for the commit you pushed.
4. Confirm the workflow conclusion is success.
5. If a run failed, open the failed job and identify the first failing step.
6. Copy only safe error summaries into issue notes or Codex prompts.
7. Do not copy secret values, full logs, production data, screenshots with real data, or provider tokens.

For release checks, review both:

- the latest `Security CI` run for the pushed commit,
- the latest `Production Smoke Check` run after deploy.

## Optional GitHub CLI Review

GitHub CLI is optional. It is useful because it can show workflow status from the terminal, but it must be installed and authenticated first.

Safe commands after installation:

```powershell
gh --version
gh auth status
gh run list --limit 10
gh run view --log-failed
```

Use `gh run view --log-failed` carefully. Failed logs can include sensitive context from commands or environment names. Do not paste raw logs into public places or AI prompts without reviewing them first.

## Failure Triage

If `Security CI` fails:

1. Identify whether the failed job is backend or frontend.
2. Reproduce locally with the closest matching command.
3. Fix the smallest relevant issue.
4. Rerun local checks.
5. Commit and push.
6. Confirm the next Actions run passes.

If `Production Smoke Check` fails:

1. Check whether Vercel frontend is reachable.
2. Check backend `/live`.
3. Check backend `/ready`.
4. If `/live` fails, suspect backend deploy/runtime outage.
5. If `/ready` fails while `/live` works, suspect database connectivity or readiness.
6. Follow `docs/INCIDENT_RESPONSE.md` if the failure affects users.

## What To Record

Safe to record in `docs/MAINTENANCE_LOG.md`:

- workflow names,
- pass/fail status,
- commit hash,
- public endpoint status codes,
- high-level failure category,
- follow-up action.

Do not record:

- secrets or credentials,
- raw logs,
- production user data,
- private provider details,
- database URLs,
- access tokens,
- reset links.

## When To Escalate

Stop and get explicit approval before:

- rotating real secrets,
- changing GitHub Actions secrets,
- changing Render or Vercel environment variables,
- changing deployment settings,
- running production migrations,
- restoring databases,
- adding new vendors that receive user data.
