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
- [ ] GitHub Actions secrets are stored in GitHub settings only.
- [ ] Dependency audit and Bandit checks pass or have documented exceptions.
- [ ] Security-sensitive changes include tests when practical.

## Render And Vercel Safety

- [ ] Render backend secrets are configured in Render, not in git.
- [ ] Vercel frontend variables are configured in Vercel, not in git.
- [ ] Production `FRONTEND_URL`, `BACKEND_URL`, `ALLOWED_ORIGINS`, and `ALLOWED_HOSTS` match real domains.
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
- [ ] If production data must be exported, get explicit approval and store it outside git.
- [ ] Keep backups private and encrypted when possible.
- [ ] Test restore steps on local or staging before relying on them.
- [ ] Keep account deletion behavior covered by tests.
- [ ] Add a formal data export process before many real users depend on the app.

## Database Backup Reminder

- [ ] Take a backup before any schema migration.
- [ ] Take a backup before any bulk data repair.
- [ ] Verify the backup can be restored in local or staging.
- [ ] Never test restore steps against production without explicit approval.
- [ ] Never drop production tables from Codex.

## AI And Codex Safety Rules

- [ ] Do not paste secrets into Codex.
- [ ] Ask Codex to list variable names only, never values.
- [ ] Require approval before auth, security, database model, migration, backup, restore, or deployment-config changes.
- [ ] Require approval before adding any new vendor that receives user data.
- [ ] Do not let Codex run production migrations.
- [ ] Do not let Codex run destructive database commands.
- [ ] Review generated docs for accidental secret values before committing.
