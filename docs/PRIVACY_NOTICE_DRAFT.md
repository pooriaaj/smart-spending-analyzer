# Privacy Notice Draft

Status: draft for product planning. This is not legal advice and should not be published as a final privacy policy without review.

Last reviewed: 2026-05-28

## Plain-Language Summary

Smart Spending Analyzer helps people track spending, import transaction data, review budgets, and ask finance-related questions about their own data. The app handles sensitive financial information, so the product should collect only what it needs, protect what it keeps, and make export/deletion behavior easy to understand.

## Information The App Collects

The current app may collect or create:

- Account identity: email address, password hash, password change timestamp, password reset token hash, and reset token expiry.
- Financial account records: user-created account names, account types, and active/inactive status.
- Transaction records: amounts, dates, descriptions, categories, transaction type, account association, import metadata, and categorization confidence/source details.
- Import review data: CSV/PDF parsing results and transaction rows confirmed into the app.
- Budget and planning data: budget plans and saved simulator scenarios.
- Learning data: personal category memories, merchant category profiles, category learning events, and community learning preference.
- Assistant data: assistant chat messages, usage events, learning examples, scope labels, and model/provider metadata.
- Technical data: security, application, provider, deployment, and diagnostic logs maintained by hosting or third-party services.

The current database models do not show storage for original uploaded CSV or PDF statement files. Confirm this again before publishing a public statement.

## How The App Uses Information

The app uses user data to:

- Authenticate the user and protect account access.
- Display transactions, dashboards, analytics, budgets, and simulator views.
- Import and categorize transaction rows.
- Improve personal category suggestions for the same account.
- Optionally improve shared merchant/category intelligence when community learning is enabled.
- Provide assistant answers based on the user's own app data.
- Maintain security, diagnose errors, run backups, and verify service health.

## Sharing And Third-Party Services

Depending on environment configuration, data may be processed by:

- Render for backend hosting, logs, and PostgreSQL database hosting.
- Vercel for frontend hosting, deployment logs, and browser delivery.
- Email or SMTP providers for password reset delivery.
- OpenAI or an OpenAI-compatible provider for assistant responses and optional vision OCR when enabled.
- Google Places API for merchant enrichment when enabled.
- GitHub Actions for CI and public smoke checks.

Do not add a new vendor that receives user data unless `docs/PRIVACY_DATA.md` and `docs/SECURITY_CHECKLIST.md` are updated first.

## User Choices

Current user-facing controls:

- Users can update their email address.
- Users can change their password.
- Users can toggle community learning from the profile page.
- Users can download a JSON export of app-owned data from the profile page after entering their current password.
- Users can delete their account from the profile page after entering their current password and confirmation text.

Account deletion removes user-owned app database rows through the backend and database/model cascades. Deletion does not instantly remove historical copies from backups, provider logs, email provider logs, third-party AI/provider logs, or local exports.

## Data Export

Self-serve export is available through the profile page and `POST /users/me/export`.

The export:

- Requires the current password.
- Returns JSON for the authenticated current user only.
- Includes app-owned user rows such as profile, accounts, transactions, learning rows, assistant rows, budgets, and saved scenarios.
- Excludes password hashes, reset token hashes, reset token expiry timestamps, shared merchant lookup cache rows, provider logs, backups, and third-party records.

## Data Retention

Retention is documented in `docs/RETENTION.md`.

Short version:

- Active account data is kept while the account exists unless the user deletes specific rows or deletes the account.
- Deleted account data may remain in backups or provider logs until those systems age out.
- Manual exports and backups are sensitive and must stay outside git.
- Retention periods are operational targets until the project has legal review and provider-specific confirmation.

## Security Practices

The app currently includes:

- HttpOnly cookie authentication.
- Password hashing.
- Password reset token hashing.
- CORS controls.
- Trusted host checks.
- CSRF origin checks.
- Request body limits.
- Security headers.
- Rate limiting.
- Sanitized backend errors.
- Backup/restore and monitoring runbooks.

Security limitations and future work remain documented in `docs/CODEX_CONTEXT.md`, `docs/SECURITY_CHECKLIST.md`, and `docs/PRIVACY_DATA.md`.

## Draft Publication Checklist

Before publishing a final privacy notice:

- [ ] Replace this draft with public-facing language that matches the production app.
- [ ] Confirm whether original uploaded files are ever stored.
- [ ] Confirm all enabled vendors and provider settings.
- [ ] Confirm production log retention in Render, Vercel, GitHub, email provider, and AI/provider dashboards.
- [ ] Confirm backup retention and restore behavior.
- [ ] Confirm community learning wording exactly matches implementation.
- [ ] Add a contact method for privacy requests.
- [ ] Get legal review if the app will serve real users beyond a small private beta.

## References Checked

- FTC: Protecting Personal Information, A Guide for Business: https://www.ftc.gov/business-guidance/resources/protecting-personal-information-guide-business
- FTC: Start with Security, A Guide for Business: https://www.ftc.gov/tips-advice/business-center/guidance/start-security-guide-business
- California Attorney General: CCPA overview for notice-at-collection concepts: https://oag.ca.gov/privacy/ccpa
