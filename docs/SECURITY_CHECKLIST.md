# Security Checklist

Use this before sharing the repo, deploying, rotating keys, or asking Codex to modify sensitive areas.

## `.env` Safety

- [ ] `.env` files are ignored by git.
- [ ] `.env.example` contains names and safe placeholders only.
- [ ] No real database URL is committed.
- [ ] No real JWT secret is committed.
- [ ] No real API key is committed.
- [ ] No password, token, reset link, or private credential is copied into docs or prompts.
- [ ] Frontend `VITE_` variables contain no secrets.

## GitHub Safety

- [ ] `git status --short` has no `.env` files staged.
- [ ] Pull requests do not include secrets in code, screenshots, logs, or comments.
- [ ] If a secret is exposed in git, follow `docs/INCIDENT_RESPONSE.md` before discussing or cleaning it up.
- [ ] GitHub Actions secrets are stored in GitHub settings only.
- [ ] Dependency audit and Bandit checks pass or have documented exceptions.
- [ ] Smoke-check workflows use public URLs or GitHub secrets only, never hardcoded private credentials.
- [ ] Security-sensitive changes include tests when practical.

## Render And Vercel Safety

- [ ] Render backend secrets are configured in Render, not in git.
- [ ] Vercel frontend variables are configured in Vercel, not in git.
- [ ] Production `FRONTEND_URL`, `BACKEND_URL`, `ALLOWED_ORIGINS`, and `ALLOWED_HOSTS` match real domains.
- [ ] Staging uses separate Render/Vercel settings and a separate database.
- [ ] Production cookies are secure and same-site settings are intentional.
- [ ] Render health check uses `/ready`.
- [ ] Vercel security headers remain in place.

## API Key Rotation

- [ ] Rotate a key immediately if it was copied into chat, logs, git, screenshots, or a public issue.
- [ ] Replace the key in the provider dashboard.
- [ ] Update the provider environment variable.
- [ ] Redeploy the affected service.
- [ ] Verify the old key no longer works when the provider supports that check.
- [ ] Document the rotation date without writing the key value.

## User Data Safety

- [ ] Use a test account for QA whenever possible.
- [ ] Avoid downloading production data to local machines.
- [ ] If user data may have leaked, follow `docs/INCIDENT_RESPONSE.md` and treat it as sensitive until scoped.
- [ ] Follow `docs/PRIVACY_DATA.md` before handling account deletion, data export, or data subject requests.
- [ ] Keep `docs/PRIVACY_NOTICE_DRAFT.md` marked as draft until reviewed for publication.
- [ ] Confirm `docs/RETENTION.md` before making public retention promises.
- [ ] If production data must be exported, get explicit approval and store it outside git.
- [ ] Do not paste real user transactions, statements, emails, screenshots, or API responses into AI prompts.
- [ ] Keep backups private and encrypted when possible.
- [ ] Test restore steps on local or staging before relying on them.
- [ ] Keep account deletion behavior covered by tests.
- [ ] Keep self-serve full data export covered by tests.
- [ ] Confirm data export excludes password hashes, reset token hashes, and non-user-owned shared cache rows.
- [ ] Do not promise instant deletion from backups, provider logs, or third-party logs.

## Database Backup Reminder

- [ ] Take a backup before any schema migration.
- [ ] Take a backup before any bulk data repair.
- [ ] Verify the backup can be restored in local or staging.
- [ ] Keep backup files in ignored local paths such as `local-backups/` or `backups/`.
- [ ] Never test restore steps against production without explicit approval.
- [ ] Never drop production tables from Codex.

## AI And Codex Safety Rules

- [ ] Do not paste secrets into Codex.
- [ ] Ask Codex to list variable names only, never values.
- [ ] If sensitive data is pasted into Codex or another AI tool, follow `docs/INCIDENT_RESPONSE.md`.
- [ ] Require approval before auth, security, database model, migration, backup, restore, or deployment-config changes.
- [ ] Require approval before adding any new vendor that receives user data.
- [ ] Require approval before changing account deletion, user export, retention, or community learning behavior.
- [ ] Do not let Codex run production migrations.
- [ ] Do not let Codex run destructive database commands.
- [ ] Review generated docs for accidental secret values before committing.
