# Legal Protection Notes

This document is practical project guidance, not legal advice. For formal
copyright, trademark, licensing, or enforcement decisions, talk to a qualified
lawyer or the relevant intellectual property office.

## Current Position

- The repository is publicly visible for portfolio, review, and evaluation.
- The code is not open-source.
- The project uses an all-rights-reserved proprietary `LICENSE`.
- `Smart Spending Analyzer(TM)` and `Zero2Asset(TM)` are claimed project marks.
- Do not use the registered trademark symbol `(R)` or `®` unless the mark is
  actually registered in the relevant jurisdiction.

## What Public GitHub Means

A public GitHub repository lets people view the code and may allow platform
actions such as forking inside GitHub. That is different from granting a broad
license to copy, commercialize, rebrand, host, or claim ownership of the app.

Keeping the repo public is useful for recruiting and portfolio review, but it
does increase copying risk. If the business value becomes sensitive, move the
full repository private and publish a smaller portfolio-safe version instead.

## Practical Protection Checklist

1. Keep `LICENSE` and `NOTICE` in the repo root.
2. Keep the README legal notice near the top of the public project page.
3. Keep a visible footer notice in the deployed app.
4. Keep dated commits, screenshots, release notes, and deployment records as
   ownership evidence.
5. Do not publish real secrets, private user data, provider logs, or real bank
   statements.
6. Avoid adding a permissive open-source license unless you truly want people to
   reuse the code.
7. If the name matters commercially, file a trademark application through the
   proper authority before using `(R)` or `®`.
8. If only part of the project should stay public, create a separate portfolio
   repository with sanitized screenshots, architecture notes, selected frontend
   examples, and non-sensitive docs.

## If Someone Copies The App

1. Save evidence first: URLs, screenshots, dates, copied files, and commit links.
2. Compare copied code or UI against this repository and deployment history.
3. Contact the site owner or platform with a calm written notice.
4. Use platform reporting or takedown processes only with accurate evidence.
5. Escalate to legal help if the copy affects money, customers, job prospects,
   or public reputation.

## Files To Keep Updated

- `LICENSE`
- `NOTICE`
- `README.md`
- `docs/LEGAL_PROTECTION.md`
- `frontend/src/i18n/LanguageContext.jsx`
- `frontend/src/App.jsx`
- Auth pages that show the public login/register/reset experience
