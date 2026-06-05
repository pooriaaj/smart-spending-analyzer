# Import Compatibility

Last updated: 2026-06-05.

This page tracks what Smart Import is intentionally tested to understand. Do not store private statement text, account numbers, tokens, cookies, or full user file contents here.

## Supported Upload Types

- CSV bank statements and tracker-style CSV exports.
- Text-readable PDF bank statements.
- Receipt images as one-at-a-time draft imports when receipt scanning is configured.
- Batch imports for CSV and PDF statement files.

## CSV Layouts Covered By Tests

- Standard columns: `Date`, `Description`, `Amount`, `Type`.
- Debit/credit columns: `Debit` and `Credit`.
- Plural debit/credit exports: `Withdrawals` and `Deposits`.
- Signed amount exports where negative amounts become expenses and positive amounts become income.
- Extra blank columns before, between, or after real fields.
- Quoted descriptions containing commas.
- Semicolon-delimited files.
- Repeated monthly tracker headers.
- Month section headings such as `May 2026` with day-only rows below them.
- Mixed valid and invalid rows, with skipped-row diagnostics returned to the UI.

## Date Handling

- ISO dates such as `2026-05-01` are safest.
- Month section headings can supply the year/month for day-only rows.
- Slash dates are inferred when the file contains evidence, for example `13/05/2026` proves day/month/year.
- Fully ambiguous slash dates such as `01/05/2026` are flagged for review because they can mean different dates in different countries.

## PDF Layouts Covered By Tests

- RBC-style text statements.
- Generic text-readable statements with a statement period.
- Desjardins-style examples.
- Multi-column amount examples.
- Encrypted/AES PDF dependency checks.
- Scanned or image-only PDF fallback/error paths.

## Known Limits

- A completely new bank PDF layout can still need parser tuning.
- Image-only PDFs depend on OCR dependencies being available in the deployed backend.
- A CSV must still include a recognizable date, description/details, and amount or debit/credit information.
- The app should skip and report bad rows instead of crashing when only some rows are malformed.

## Future File Bug Rule

When a real file fails, capture only safe facts: file type, approximate size, request ID, import stage, and sanitized row diagnostics. Then add a synthetic regression test that represents the layout without copying private statement contents.
