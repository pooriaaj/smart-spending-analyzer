# Import Compatibility

Last updated: 2026-06-10.

This page tracks what Smart Import is intentionally tested to understand. Do not store private statement text, account numbers, tokens, cookies, or full user file contents here.

## Supported Upload Types

- CSV bank statements and tracker-style CSV exports.
- Text-readable PDF bank statements.
- Receipt images as one-at-a-time draft imports when receipt scanning is configured.
- Batch imports for CSV and PDF statement files. One bad file in a batch is isolated and skipped with a note — it no longer aborts the entire batch.

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
- 2-digit year values use a pivot: ≤30 → 2000s, >30 → 1900s.

## PDF Bank Profiles (Named + Detected)

The parser auto-detects the bank from statement text and applies a bank-specific profile for noise filtering. 25 profiles are registered (including the generic fallback):

### Canadian Banks
| Profile | Display Name | Detection |
| --- | --- | --- |
| rbc | Royal Bank of Canada | "royal bank" or "rbc.com" |
| rbc_visa | RBC Visa | "rbc avion", "rbc rewards" plus "rbc" |
| td | TD Canada Trust | "td canada trust" |
| cibc | CIBC | "canadian imperial bank of commerce" |
| scotiabank | Scotiabank | "scotiabank" or "bank of nova scotia" |
| tangerine | Tangerine | "tangerine bank" or "tangerine.ca" |
| simplii | Simplii Financial | "simplii financial" |
| desjardins | Desjardins | "desjardins" (balance-delta inference) |
| national_bank | National Bank of Canada | "national bank of canada" (balance-delta inference) |
| bmo | BMO (Bank of Montreal) | "bank of montreal" (balance-delta inference) |
| bmo_french | BMO French | "banque de montreal" + French column headers (all required) |
| laurentian | Laurentian Bank | "banque laurentienne" or "laurentian bank" |
| atb | ATB Financial | "atb financial" or "alberta treasury branches" |

### US Banks
| Profile | Display Name | Detection |
| --- | --- | --- |
| chase | Chase Bank | "jpmorgan chase bank" or "chase bank" |
| bofa | Bank of America | "bank of america" |
| wells_fargo | Wells Fargo | "wells fargo bank" or "wells fargo" |
| capital_one | Capital One | "capital one" |
| citibank | Citibank / Citi | "citibank" or "citi.com" |
| us_bank | U.S. Bank | "u.s. bank national association" or "usbank.com" |
| td_bank_us | TD Bank (US) | "td bank, n.a." or "america's most convenient bank" |
| amex | American Express | "american express" or "americanexpress.com" |
| discover | Discover | "discover bank" or "discover.com" |
| pnc | PNC Bank | "pnc bank" or "pnc.com" |
| navy_federal | Navy Federal Credit Union | "navy federal credit union" or "navyfederal.org" |

### Fallback
- **generic** — used when no named profile is detected. Accuracy varies; "Used generic PDF parser" note is shown.

## PDF Amount Formats Supported

- Dollar amounts: `$1,234.56`, `1234.56`, `1,234.56`
- Negative in parentheses: `($89.10)`
- Signed: `-$15.75`
- CR/DR suffix: `$1,500.00CR`, `$15.99DR`, `2,100.00CR`, `84.21DR`
- Trailing negative: `12.34-`
- French/European space-thousands: `1 320,00`, `6,21`
- Three-column debit/credit/balance: `0.00  1,500.00  1,700.00`
- Dash placeholder column: `- 1,500.00 1,700.00`

## Balance Line Filtering

Lines matching any of these markers are treated as summary/balance lines and not parsed as transactions:

- opening balance, closing balance
- beginning balance, ending balance, daily ending balance
- balance brought forward, balance carried forward
- daily closing balance, total account balance
- French equivalents: solde d'ouverture, solde de fermeture, solde de cloture, etc.

Bank profiles add their own extra balance markers on top of this list.

## PDF Layouts Covered By Tests

- RBC chequing (cross-year, multiline rows, no-activity period)
- RBC Visa (balance/explainer section filtering, purchase interest)
- TD Canada Trust (debit/credit/balance columns, placeholder dashes, transaction+posted dates)
- CIBC (CR/DR suffix amounts)
- Tangerine (CR/DR suffix amounts)
- Desjardins (ISO period, French comma-decimal, balance-delta inference)
- National Bank (running balance inference)
- BMO French (normalized French PDF encoding, balance-delta inference)
- BMO English (debit/credit/balance columns, Opening/Closing Balance filtering)
- Chase (Beginning Balance/Ending Balance filtering, debit/credit/balance columns)
- Generic (statement period, month-first dates, numeric dates, 2-digit years)
- Scanned/image-only PDF fallback via local Tesseract OCR
- Scanned/image-only PDF fallback via OpenAI vision OCR
- Partially-readable PDF (mixed text and image pages)
- Unrecognized layout error (text present but no transaction rows found)
- Category lookup failure (row kept with fallback category)
- Row conversion failure (row skipped, other rows still returned)

## Known Limits

- A completely new bank PDF layout can still need parser tuning.
- Image-only PDFs depend on OCR dependencies being available in the deployed backend (Tesseract is installed in the Docker image).
- A CSV must still include a recognizable date, description/details, and amount or debit/credit information.
- The app skips and reports bad rows instead of crashing when only some rows are malformed.
- Statements with more than 200 rows show only the first 200 in preview, with a note to split the file.

## Future File Bug Rule

When a real file fails, capture only safe facts: file type, approximate size, request ID, import stage, and sanitized row diagnostics. Then add a synthetic regression test that represents the layout without copying private statement contents.
