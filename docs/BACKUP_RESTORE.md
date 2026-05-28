# Backup And Restore Guide

This runbook is for Smart Spending Analyzer database safety before migrations, bulk repairs, imports, and production releases.

It contains commands and process only. Do not put real database URLs, passwords, tokens, or backup files in git.

## Current Hosting Reality

The backend is designed for PostgreSQL and is currently documented for Render PostgreSQL.

Render's current Postgres backup docs say paid databases support point-in-time recovery and logical exports. Render's Free Postgres instance type does not provide Render-managed recovery or logical backups, so free instances need either an upgrade or a manual `pg_dump` backup from your local machine.

Render links:

- Render Postgres recovery and backups: https://render.com/docs/postgresql-backups
- Render Postgres overview: https://render.com/docs/postgresql

## Non-Negotiable Rules

- Never restore over production directly.
- Never drop production tables from Codex.
- Never run production migrations until a backup exists and has been verified.
- Never commit backup files.
- Never paste real `DATABASE_URL` values into docs, commits, issues, screenshots, or AI prompts.
- Treat backup files as sensitive user data.
- Restore drills should target local or staging databases first.

## What Counts As A Backup

Good enough before local development:

- Fresh local SQLite or PostgreSQL test database that can be recreated.
- Git commit for code changes.

Good enough before a production migration:

- Render logical export, if your Render database plan supports it.
- Or a manual `pg_dump` custom-format backup from your machine.
- Plus a restore verification step, at least `pg_restore --list`, and ideally a restore into local or staging.

Best recovery path after production data loss:

- Prefer Render point-in-time recovery to a new database instance if your plan supports it.
- Validate the recovery instance.
- Switch the backend `DATABASE_URL` to the recovered database only after validation.

## Manual Backup With `pg_dump`

Use this when Render-managed backups are unavailable or when you want your own pre-migration backup.

Prerequisites:

- Install PostgreSQL client tools that match the database major version when possible.
- Make sure `pg_dump` is available in your terminal.
- Set `DATABASE_URL` in your shell without printing it.

PowerShell example:

```powershell
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Force -Path local-backups | Out-Null
pg_dump --format=custom --no-owner --no-acl --file "local-backups\smart-spending-$timestamp.dump" $env:DATABASE_URL
```

Do not paste the actual database URL into the command. Use an environment variable or a local connection profile.

## Verify A Backup File

At minimum, confirm the backup can be read:

```powershell
pg_restore --list "local-backups\smart-spending-YYYYMMDD-HHMMSS.dump"
```

Better verification is a local restore drill into an empty local PostgreSQL database.

## Local Restore Drill

Only do this against a local empty restore database.

1. Create an empty local PostgreSQL database.
2. Set a local-only restore URL in your shell.
3. Restore the dump into that local database.
4. Start the backend against the restored local database.
5. Check `/ready`, login with a safe test user if available, and verify core tables/data exist.

PowerShell example:

```powershell
pg_restore --no-owner --no-acl --dbname $env:LOCAL_RESTORE_DATABASE_URL "local-backups\smart-spending-YYYYMMDD-HHMMSS.dump"
```

If the local restore database is not empty, stop and create a new empty local database instead. Avoid `--clean` unless you are absolutely sure the target is disposable.

## Render Logical Export Path

Use this when the Render database plan supports logical exports.

1. Open the Render dashboard.
2. Select the PostgreSQL database.
3. Go to the Recovery page.
4. Create an export.
5. Download the export when it is ready.
6. Store it outside the repository.
7. Verify it with the matching PostgreSQL restore tools.

Render retains logical exports for a limited time, so download anything needed for longer retention.

## Render Point-In-Time Recovery Path

Use this when the Render database plan supports point-in-time recovery and the problem happened recently.

1. Open the Render database Recovery page.
2. Start recovery to a new database instance.
3. Validate the recovered database in isolation.
4. Update backend environment variables only after confirming the recovered data is correct.
5. Keep the old database until the app is verified against the recovered one.

This is safer than restoring over the original production database.

## Pre-Migration Backup Checklist

- [ ] Confirm which database will be migrated.
- [ ] Confirm the migration has been tested locally.
- [ ] Create a backup or Render export.
- [ ] Verify the backup can be listed or restored.
- [ ] Save the backup outside git.
- [ ] Confirm rollback means "restore/switch database", not only "revert code".
- [ ] Get explicit approval before running any production migration.

## Storage And Retention

- Keep local backups in `local-backups/` or `backups/`; both are ignored by git.
- Delete old local backups that are no longer needed.
- Do not email backup files casually.
- If storing longer-term backups, use encrypted storage.
- Keep a short private note with backup date, database name, and reason. Do not include credentials.

## Codex Rules For Backup Work

Codex may:

- Create or edit backup documentation.
- Create local-only helper scripts after approval.
- Run `pg_restore --list` on a local backup file if the user provides the path.

Codex must not:

- Print real database URLs.
- Download production data without explicit approval.
- Restore into production.
- Drop production tables.
- Run production migrations before a verified backup exists.
