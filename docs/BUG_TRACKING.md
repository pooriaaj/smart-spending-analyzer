# Bug Tracking And Diagnostics

Last updated: 2026-06-05.

Use this file to control past, current, and future bugs without storing secrets, passwords, tokens, cookies, database URLs, or private statement contents.

## What To Capture

- Date and environment: local, Vercel production, Render production, or staging.
- Page and action: for example `Import > Upload CSV`.
- Browser/device: desktop Chrome, iPhone Safari, Android Chrome, etc.
- API endpoint or request path when known.
- HTTP status, request ID, and import stage when shown.
- File type and rough size only. Do not paste bank statement contents.
- Expected behavior and actual behavior.
- Commit hash or PR that fixed it.

## Current Diagnostic Sources

- Backend request ID: returned in API headers as `X-Request-ID` and in sanitized server-error bodies.
- Render logs: search by request ID, route path, and import stage.
- Browser console: upload failures log a sanitized `Import upload failed` object with status, request ID, stage, file count, extensions, types, and sizes.
- Backend tests: import, PDF parser, security, analytics, users, budgets, and database maintenance regression suites.
- Frontend tests: auth, protected routes, import, analytics, transactions, budgets, assistant, profile, and utility tests.

## Known Past Bugs

| Date | Area | Symptom | Cause | Fix Status |
| --- | --- | --- | --- | --- |
| 2026-06-04 | PDF import | RBC PDF failed with `pdf_statement_parse`. | Render image/PDF stack needed dependency hardening and encrypted/AES PDF handling. | Fixed with backend dependency/import hardening and tests. |
| 2026-06-04 | CSV import | Monthly expense tracker CSV was rejected as missing date/description columns. | Parser expected a simpler statement layout and did not handle tracker-style repeated headers well enough. | Improved with tracker CSV support and tests. |
| 2026-06-04 | Custom domain auth | Phone login appeared successful, then returned to login. | Cross-site cookie behavior between `www.zero2asset.com` and Render backend. | Fixed by frontend first-party `/api` proxy rewrite. |
| 2026-06-04 | Large-history performance | Overview and transactions felt slow after adding a large account history. | Dashboard and helper endpoints repeated expensive scans. | Improved by backend aggregate reuse and cheaper helper summaries. |
| 2026-06-05 | Tracker CSV import | Later month sections could be skipped when dates were day-only values under `May 2026`/`June 2026` headings. | Parser did not carry month-section context into row date parsing. | Fixed with month-context parsing and row diagnostics. |
| 2026-06-05 | CSV import | Synthetic import audit found plural `Withdrawals`/`Deposits` headers were not accepted and fully ambiguous slash dates looked too confident. | Header aliases were narrow, and slash date parsing did not infer or flag date-order uncertainty. | Fixed with broader aliases, date-order inference, ambiguity review flags, and regression tests. |

## Open Watch Items

- Large imports may still be slow if a file is very large or contains many unusual rows.
- Browser uploads routed through Vercel `/api` should be tested with typical statement sizes after each deploy.
- PDF parsing depends on each bank layout; every new failed PDF shape should become a regression test.
- Fully ambiguous numeric dates such as `01/05/2026` still need user review unless the same file contains date-order evidence.
- Scanned image/PDF OCR needs production dependency verification after Docker/Render changes.
- Overview can still be improved with deeper query timing if large-history accounts remain slow.

## Bug Intake Template

```text
Date:
Environment:
Device/browser:
Page/action:
File type and approximate size:
HTTP status:
Request ID:
Import stage:
Expected:
Actual:
Reproduction steps:
Fix status:
Commit:
```

## Triage Flow

1. Reproduce with a test account when possible.
2. Capture browser console diagnostics and API request ID.
3. Search Render logs by request ID.
4. Add or update a backend/frontend regression test that fails before the fix.
5. Fix narrowly.
6. Run focused tests, then broader tests/build if the blast radius is larger.
7. Update this file with the cause, status, and commit.
