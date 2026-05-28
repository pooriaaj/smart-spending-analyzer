# Incident Response Runbook

Status: operational draft for a solo developer. This is not legal advice and does not replace provider support, legal counsel, or law enforcement guidance.

Last reviewed: 2026-05-28

## Purpose

Use this runbook when something may harm availability, security, privacy, data integrity, or user trust in Smart Spending Analyzer.

Examples:

- Production frontend or backend is down.
- `/ready` reports database failure.
- A deploy breaks login, transactions, import, export, deletion, or analytics.
- A secret may have been exposed.
- User data may have leaked or been exported incorrectly.
- A database migration, backup, or restore appears unsafe.
- A dependency vulnerability affects production.
- AI/Codex was given sensitive data by mistake.

## Golden Rules

- Do not panic-delete evidence.
- Do not print, paste, summarize, or copy real secrets.
- Do not edit `.env` files from Codex.
- Do not run production migrations during an incident unless a separate explicit approval is given.
- Do not drop tables.
- Do not restore over production without an approved restore plan.
- Prefer rollback, disablement, or provider dashboard controls over risky live code changes.
- Keep a short private incident note outside git if real user data or secrets are involved.
- Use test accounts and redacted examples in GitHub issues, commits, docs, screenshots, and AI prompts.

## Severity Levels

| Severity | Meaning | Examples |
| --- | --- | --- |
| SEV0 | Confirmed or likely user data exposure, credential compromise, unauthorized database access, or destructive production data action. | Real secret committed, export endpoint leaks another user's data, production database modified unexpectedly. |
| SEV1 | Production app is unavailable or a core user workflow is broken. | Vercel site down, Render backend down, login broken, `/ready` failing, deploy broke transactions. |
| SEV2 | Important feature is degraded but core account access still works. | Import broken, assistant unavailable, analytics wrong for some filters, monitoring check failing. |
| SEV3 | Low-risk issue or non-production issue. | Staging broken, docs wrong, flaky test, minor UI issue. |

When unsure, start one level higher, then downgrade after evidence is clear.

## First 15 Minutes

1. Pause risky work.
2. Write down the exact time, current git commit, deployment, and symptom.
3. Decide severity using the table above.
4. Preserve evidence: logs, status codes, screenshots, and timestamps, but redact secrets and user data.
5. Stop active harm:
   - Roll back a bad deploy if the latest deploy caused the issue.
   - Disable a risky optional feature if a safe toggle exists.
   - Rotate a leaked secret in the provider dashboard.
   - Temporarily block public access only if necessary and feasible.
6. Do not make database changes until the failure mode is understood.
7. If SEV0, treat it as privacy/security-sensitive and avoid public GitHub details.

## Triage Checklist

- [ ] What changed most recently?
- [ ] Is the issue reproducible with a test account?
- [ ] Is frontend reachable?
- [ ] Is backend `/live` reachable?
- [ ] Is backend `/ready` reachable?
- [ ] Did GitHub CI pass?
- [ ] Did Vercel deploy the expected commit?
- [ ] Did Render deploy the expected commit?
- [ ] Are provider logs showing app errors, boot failures, database errors, or rate limits?
- [ ] Is the database reachable?
- [ ] Is the issue limited to one feature, one user, one account, or all users?
- [ ] Is any secret or real user data visible in logs, commits, screenshots, or prompts?

## Production Outage Or Failed Deploy

Use this when the app is down or a core flow is broken.

1. Check the latest commit and deployment.
2. Check GitHub Actions.
3. Check Vercel deployment status and frontend logs.
4. Check Render service status and backend logs.
5. Check `/live` and `/ready`.
6. If the issue started with the latest deploy, roll back to the last known good deploy through Vercel/Render dashboards.
7. If rollback is not enough, stop and inspect backend logs before changing code.
8. Do not run migrations or restore production data as an outage shortcut.
9. After recovery, add a regression test or checklist item for the broken flow.

## Suspected Secret Leak

Use this when an API key, database URL, JWT secret, password, token, reset link, or provider credential may have been exposed.

1. Do not paste the secret into Codex, GitHub, docs, or chat.
2. Identify the secret by variable name and provider only.
3. Rotate or revoke the secret in the provider dashboard.
4. Update the provider environment variable.
5. Redeploy the affected service.
6. Verify the old secret no longer works if the provider supports that check.
7. Search git history and current files for the leaked value only if you can do it without printing the value.
8. If a secret reached git history, plan a history cleanup separately and rotate first.
9. Document the date, provider, variable name, and action taken without recording the secret value.

## Suspected User Data Exposure

Use this when another user's data may be visible, a user export may include wrong data, logs may contain real financial data, or screenshots/prompts may expose private data.

1. Treat as SEV0 until scoped.
2. Preserve evidence privately with redaction.
3. Identify the affected route, feature, account scope, deployment, and commit.
4. Stop the exposure:
   - Roll back if caused by the latest deploy.
   - Disable the affected feature if a safe toggle exists.
   - Remove public screenshots or logs if possible.
5. Confirm whether the issue affects production, staging, or local only.
6. Do not run bulk deletes or database repairs without a reviewed plan.
7. Review `docs/PRIVACY_DATA.md`, `docs/PRIVACY_NOTICE_DRAFT.md`, and `docs/RETENTION.md`.
8. Consider legal/provider guidance before notifying users.
9. Add regression tests for cross-user isolation or sensitive field exclusion.

## Database Incident

Use this for `/ready` failures, broken migrations, suspected corruption, accidental writes, or restore concerns.

1. Do not drop tables.
2. Do not run production migrations.
3. Do not restore over production.
4. Identify whether the problem is connection, credentials, schema, data, provider outage, or app code.
5. Check Render Postgres status and backend logs.
6. Take a backup before any approved repair if the database is reachable.
7. Test repair or restore steps locally or in staging first.
8. Follow `docs/BACKUP_RESTORE.md` and `docs/MIGRATIONS.md`.

## Dependency Or Vulnerability Incident

Use this when `pip-audit`, `npm audit`, Bandit, GitHub Dependabot, or provider alerts report a vulnerability.

1. Confirm package, severity, affected path, and whether production uses it.
2. If actively exploited or critical, prioritize a hotfix branch.
3. Update only the needed dependency when possible.
4. Run backend tests, frontend tests, lint/build, and audits.
5. Deploy after checks pass.
6. Document any accepted risk or temporary workaround.

## AI/Codex Data Handling Incident

Use this when sensitive data was pasted into Codex, another AI tool, a public issue, or generated docs.

1. Stop sharing additional sensitive data.
2. Identify what was shared without repeating the value.
3. If it was a secret, rotate it.
4. If it was user data, treat as a privacy incident and scope exposure.
5. Remove generated files that contain sensitive data before committing.
6. Add or update checklist guidance to prevent repeat mistakes.

## Communication Templates

Use these only after facts are known. Keep public messages short and honest.

### Internal Note

```text
Time detected:
Severity:
Detected by:
Affected environment:
Affected commit/deployment:
Symptoms:
Known user impact:
Actions taken:
Current status:
Next check time:
```

### User-Facing Holding Message

```text
We are investigating an issue affecting Smart Spending Analyzer. We have paused risky changes while we verify impact and restore normal service. We will update this message when we know more.
```

### User-Facing Recovery Message

```text
The issue has been resolved. We identified the affected service, restored normal operation, and are reviewing what happened so we can reduce the chance of a repeat.
```

Do not promise user data impact, notification timelines, or legal conclusions until reviewed.

## Post-Incident Review

Complete this after SEV0, SEV1, or repeated SEV2 issues.

```text
Incident title:
Date:
Severity:
Duration:
Detected by:
Root cause:
What went well:
What went poorly:
User impact:
Data impact:
Rollback or fix:
Tests added:
Docs updated:
Preventive actions:
Owner:
Due date:
```

## Follow-Up Checklist

- [ ] Add or update tests.
- [ ] Add or update monitoring.
- [ ] Add or update docs.
- [ ] Rotate exposed credentials if needed.
- [ ] Review backup/restore readiness if data was involved.
- [ ] Review privacy/retention language if user data was involved.
- [ ] Confirm GitHub, Vercel, Render, and email/AI/provider logs do not contain secrets.
- [ ] Keep final notes free of secret values and raw user financial data.

## References

- NIST SP 800-61 incident response guidance: https://www.nist.gov/publications/computer-security-incident-handling-guide
- NIST Incident Response project page: https://csrc.nist.gov/projects/incident-response
- FTC Data Breach Response, A Guide for Business: https://www.ftc.gov/tips-advice/business-center/guidance/data-breach-response-guide-business
- CISA Planning, Response, and Recovery: https://www.cisa.gov/planning-response-recovery
