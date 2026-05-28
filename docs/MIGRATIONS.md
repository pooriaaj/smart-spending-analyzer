# Migration Guide

Smart Spending Analyzer now has a local Alembic setup in `backend/`.

This is Phase 2 foundation work only. It does not mean production migrations are automatic or approved.

## Current Status

- Alembic config: `backend/alembic.ini`
- Migration environment: `backend/alembic/env.py`
- Baseline revision: `backend/alembic/versions/20260528_0001_initial_schema.py`
- Test coverage: `backend/tests/test_alembic_baseline.py`
- Alembic dependency: `backend/requirements-dev.txt`

The baseline migration creates the current SQLAlchemy schema for a fresh database. It does not inspect or modify production.

## Safety Rules

- Do not run Alembic against production without explicit approval.
- Take and verify a backup before any production migration.
- Do not run `downgrade` against production.
- Do not edit migration files after they have been applied to a shared database.
- Do not use Alembic to drop tables unless the user explicitly approves the exact destructive operation.
- Keep `DATABASE_URL` values out of docs, commits, terminal output, and AI prompts.

The baseline downgrade is intentionally disabled because reversing it would drop every application table. Use a verified backup/restore plan instead.

## Local Commands

Run these from the repository root unless noted.

Install development dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
```

Run the Alembic baseline test:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m pytest backend\tests\test_alembic_baseline.py -q
```

Check the current migration head without touching production:

```powershell
cd backend
..\.venv\Scripts\alembic.exe -c alembic.ini heads
```

Use a local or temporary database URL before any upgrade command. Never paste the value into docs or commits.

## Future Migration Workflow

1. Make or approve the SQLAlchemy model change.
2. Generate a draft migration locally.
3. Read the generated migration line by line.
4. Remove accidental destructive operations unless explicitly approved.
5. Run the migration on a local or test database.
6. Run backend tests.
7. Back up production before any production migration.
8. Apply production migration only after explicit approval.

## Phase 3 Dependency

Before any production schema migration, create a backup/restore runbook and test restore locally or in staging.
