from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import MagicMock, patch

from app.services import pdf_statement_service as service
from app.services.transaction_service import CategoryDecision


class PdfStatementServiceHelpersTest(unittest.TestCase):
    def test_parse_amount_token_supports_bank_formats(self) -> None:
        self.assertAlmostEqual(service.parse_amount_token("$1,234.56") or 0.0, 1234.56)
        self.assertAlmostEqual(service.parse_amount_token("($89.10)") or 0.0, -89.10)
        self.assertAlmostEqual(service.parse_amount_token("-$15.75") or 0.0, -15.75)
        self.assertAlmostEqual(service.parse_amount_token("$1,500.00CR") or 0.0, 1500.00)
        self.assertAlmostEqual(service.parse_amount_token("$15.99DR") or 0.0, -15.99)
        self.assertAlmostEqual(service.parse_amount_token("12.34-") or 0.0, -12.34)
        self.assertAlmostEqual(service.parse_amount_token("1 320,00") or 0.0, 1320.00)
        self.assertAlmostEqual(service.parse_amount_token("6,21") or 0.0, 6.21)

    def test_parse_amount_token_rejects_reference_digit_space_dot_amounts(self) -> None:
        self.assertIsNone(service.parse_amount_token("7 100.00"))
        self.assertIsNone(service.parse_amount_token("5 200.00"))

    def test_split_line_and_trailing_amounts_extracts_multiple_tokens(self) -> None:
        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "GROCERY STORE TORONTO $45.67 $1,234.56"
        )

        self.assertEqual(body, "GROCERY STORE TORONTO")
        self.assertEqual(trailing_amounts, ["$45.67", "$1,234.56"])

    def test_split_line_and_trailing_amounts_handles_unicode_dash_placeholders(self) -> None:
        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "Jan 02 PAYROLL \u2013 1,500.00 1,700.00"
        )

        self.assertEqual(body, "Jan 02 PAYROLL")
        self.assertEqual(trailing_amounts, ["\u2013", "1,500.00", "1,700.00"])

        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "Jan 03 MONTHLY FEE 15.99 \u2014 1,684.01"
        )

        self.assertEqual(body, "Jan 03 MONTHLY FEE")
        self.assertEqual(trailing_amounts, ["15.99", "\u2014", "1,684.01"])

    def test_split_line_and_trailing_amounts_handles_comma_decimal_balance_layout(self) -> None:
        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "Achat par carte de d\u00e8bit, MCDONALD'S #400 6,21 260,05"
        )

        self.assertEqual(body, "Achat par carte de d\u00e8bit, MCDONALD'S #400")
        self.assertEqual(trailing_amounts, ["6,21", "260,05"])

    def test_split_line_and_trailing_amounts_does_not_steal_reference_code_digits(self) -> None:
        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "e-Transfer received MAHTAALIJANI CAmGNFb7 100.00 126.21"
        )

        self.assertEqual(body, "e-Transfer received MAHTAALIJANI CAmGNFb7")
        self.assertEqual(trailing_amounts, ["100.00", "126.21"])

        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "e-Transfer received MAHTAALIJANI CA3Y5xH5 200.00 211.78"
        )

        self.assertEqual(body, "e-Transfer received MAHTAALIJANI CA3Y5xH5")
        self.assertEqual(trailing_amounts, ["200.00", "211.78"])

        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "Cheque - # 7 100.00 126.21"
        )

        self.assertEqual(body, "Cheque - # 7")
        self.assertEqual(trailing_amounts, ["100.00", "126.21"])

    def test_split_line_and_trailing_amounts_keeps_supported_thousands_formats(self) -> None:
        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "Payroll Deposit Plusgrade Inc. 3,268.57"
        )

        self.assertEqual(body, "Payroll Deposit Plusgrade Inc.")
        self.assertEqual(trailing_amounts, ["3,268.57"])

        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "Virement en ligne, TF 0283#8769-816 1 320,00 1 403,84"
        )

        self.assertEqual(body, "Virement en ligne, TF 0283#8769-816")
        self.assertEqual(trailing_amounts, ["1 320,00", "1 403,84"])

    def test_normalize_extracted_pdf_text_decodes_french_statement_escapes(self) -> None:
        text = service.normalize_extracted_pdf_text(
            "/1/3 Avril /2/0/2/6 Achat par carte de d/e8bit/2c MCDONALD/27S /6/2c/2/1"
        )

        self.assertEqual(text, "13 Avril 2026 Achat par carte de d\u00e8bit, MCDONALD'S 6,21")

    def test_resolve_trailing_amount_columns_handles_debit_credit_balance_layout(self) -> None:
        amount_text, balance_text, explicit_type = service.resolve_trailing_amount_columns(
            ["0.00", "1,500.00", "1,700.00"]
        )
        self.assertEqual(amount_text, "1,500.00")
        self.assertEqual(balance_text, "1,700.00")
        self.assertEqual(explicit_type, "income")

        amount_text, balance_text, explicit_type = service.resolve_trailing_amount_columns(
            ["15.99", "0.00", "1,684.01"]
        )
        self.assertEqual(amount_text, "15.99")
        self.assertEqual(balance_text, "1,684.01")
        self.assertEqual(explicit_type, "expense")

        amount_text, balance_text, explicit_type = service.resolve_trailing_amount_columns(
            ["-", "1,500.00", "1,700.00"]
        )
        self.assertEqual(amount_text, "1,500.00")
        self.assertEqual(balance_text, "1,700.00")
        self.assertEqual(explicit_type, "income")

        amount_text, balance_text, explicit_type = service.resolve_trailing_amount_columns(
            ["15.99", "-", "1,684.01"]
        )
        self.assertEqual(amount_text, "15.99")
        self.assertEqual(balance_text, "1,684.01")
        self.assertEqual(explicit_type, "expense")

    def test_cross_year_statement_resolution_uses_month_bucket(self) -> None:
        start_year, end_year = service.extract_statement_year_range(
            "From December 15, 2024 to January 15, 2025"
        )

        self.assertEqual(start_year, 2024)
        self.assertEqual(end_year, 2025)
        self.assertEqual(
            service.resolve_statement_year_for_month(12, start_year, end_year),
            2024,
        )
        self.assertEqual(
            service.resolve_statement_year_for_month(1, start_year, end_year),
            2025,
        )

    def test_extract_statement_year_range_supports_numeric_periods(self) -> None:
        start_year, end_year = service.extract_statement_year_range(
            "Statement period 12/28/2024 - 01/10/2025"
        )

        self.assertEqual(start_year, 2024)
        self.assertEqual(end_year, 2025)

    def test_build_numeric_date_candidates_can_disambiguate_with_statement_period(self) -> None:
        candidates = service.build_numeric_date_candidates(
            "03",
            "01",
            None,
            2025,
            start_date=date(2024, 12, 28),
            end_date=date(2025, 1, 10),
        )

        self.assertIn(date(2025, 1, 3), candidates)
        self.assertIn(date(2025, 3, 1), candidates)

    def test_detect_statement_profile_identifies_td(self) -> None:
        profile = service.detect_statement_profile(
            "TD Canada Trust\nStatement period 12/28/2024 - 01/10/2025"
        )

        self.assertEqual(profile.profile_id, "td")

    def test_strip_secondary_leading_date_removes_posted_date_prefix(self) -> None:
        stripped = service.strip_secondary_leading_date(
            "Jan 03 PAYROLL DEPOSIT $1,500.00",
            start_year=2024,
            end_year=2025,
            fallback_year=2025,
            start_date=date(2024, 12, 28),
            end_date=date(2025, 1, 10),
        )

        self.assertEqual(stripped, "PAYROLL DEPOSIT $1,500.00")

    def test_clean_statement_description_removes_rbc_reference_noise(self) -> None:
        self.assertEqual(
            service.clean_statement_description("Contactless Interac purchase - 0095 ORANGE MART"),
            "ORANGE MART",
        )
        self.assertEqual(
            service.clean_statement_description("Contactless Interac Transit - 0620 PRES/R8SFN9RVZG"),
            "Transit",
        )
        self.assertEqual(
            service.clean_statement_description("ATM deposit - TZ661796"),
            "ATM deposit",
        )


class PdfStatementServicePreviewParsingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = MagicMock()

    def categorize(self, **kwargs: str) -> CategoryDecision:
        category = "income" if kwargs["tx_type"] == "income" else "other"
        return CategoryDecision(
            category=category,
            confidence=0.9,
            matched_keyword=None,
            reason="Test category decision.",
            source="test",
        )

    def extraction_result(
        self,
        text: str,
        total_pages: int = 1,
        readable_text_pages: int = 1,
        page_texts: tuple[str, ...] | None = None,
    ) -> service.PdfTextExtractionResult:
        resolved_page_texts = page_texts
        if resolved_page_texts is None:
            if total_pages == 1:
                resolved_page_texts = (text,)
            else:
                resolved_page_texts = tuple("" for _ in range(total_pages))

        return service.PdfTextExtractionResult(
            text=text,
            total_pages=total_pages,
            readable_text_pages=readable_text_pages,
            page_texts=resolved_page_texts,
        )

    def test_parse_rbc_preview_handles_cross_year_and_multiline_rows(self) -> None:
        text = """
Royal Bank of Canada
Details of your account activity
From December 15, 2024 to January 15, 2025
15 Dec COFFEE SHOP $5.25 $1,200.00
02 Jan DIRECT DEPOSIT PAYROLL $2,000.00 $3,200.00
03 Jan GROCERY STORE
TORONTO ON $45.10 $3,154.90
Closing balance $3,154.90
        """.strip()

        with patch.object(service, "categorize_transaction_details", side_effect=self.categorize):
            result = service.parse_rbc_statement_preview(
                db=self.db,
                owner_id=123,
                text=text,
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 3)

        self.assertEqual(preview_rows[0].date, "2024-12-15")
        self.assertEqual(preview_rows[0].amount, 5.25)
        self.assertEqual(preview_rows[0].type, "expense")

        self.assertEqual(preview_rows[1].date, "2025-01-02")
        self.assertEqual(preview_rows[1].type, "income")
        self.assertEqual(preview_rows[1].category, "income")

        self.assertEqual(preview_rows[2].date, "2025-01-03")
        self.assertEqual(preview_rows[2].description, "GROCERY STORE TORONTO ON")
        self.assertIn("balance=$3,154.90", preview_rows[2].source_line or "")

    def test_parse_rbc_preview_returns_empty_rows_for_no_activity_statement(self) -> None:
        text = """
Royal Bank of Canada
Details of your account activity
From March 2, 2026 to April 2, 2026
Date Description Withdrawals ($) Deposits ($) Balance ($)
- No activity for this period - - -
Closing balance $1.00
        """.strip()

        result = service.parse_rbc_statement_preview(
            db=self.db,
            owner_id=123,
            text=text,
        )

        self.assertEqual(result["preview_rows"], [])
        self.assertIn("Statement says no activity for this period.", result["notes"])

    def test_generic_credit_card_parser_skips_balance_and_explainer_sections(self) -> None:
        text = """
RBC Avion Visa Platinum
STATEMENT FROM FEB 12 TO MAR 11, 2026
TRANSACTION DATE POSTING DATE ACTIVITY DESCRIPTION AMOUNT ($)
MAR 11 MAR 11 PURCHASE INTEREST 20.99% $39.61
MAR 11 Time to Pay If you make only the Minimum Payment each month, we estimate it will take 17 years to fully repay the outstanding balance Purchases & Fees 20.99
TOTAL ACCOUNT BALANCE $2,092.07
Time to Pay
If you make only the Minimum Payment each month, we estimate it will take 17 years.
Purchases & Fees 20.99%
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 1)
        self.assertEqual(preview_rows[0].date, "2026-03-11")
        self.assertEqual(preview_rows[0].description, "PURCHASE INTEREST 20.99%")
        self.assertEqual(preview_rows[0].type, "expense")
        self.assertEqual(preview_rows[0].amount, 39.61)

    def test_parse_pdf_statement_preview_uses_generic_parser_with_shared_date_logic(self) -> None:
        text = """
Account Statement
From December 28, 2024 to January 10, 2025
28 Dec BOOK STORE ($12.34)
02 Jan INCOME TAX REFUND $150.00
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(result["notes"], ["Used generic PDF parser. Accuracy may vary for this bank format."])
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].date, "2024-12-28")
        self.assertEqual(preview_rows[0].amount, 12.34)
        self.assertEqual(preview_rows[0].type, "expense")
        self.assertEqual(preview_rows[1].date, "2025-01-02")
        self.assertEqual(preview_rows[1].type, "income")

    def test_parse_pdf_statement_preview_supports_month_first_and_numeric_dates(self) -> None:
        text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
Jan 02 PAYROLL DEPOSIT $1,500.00
01/03 BOOK STORE $12.34
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].date, "2025-01-02")
        self.assertEqual(preview_rows[0].type, "income")
        self.assertEqual(preview_rows[1].date, "2025-01-03")
        self.assertEqual(preview_rows[1].amount, 12.34)
        self.assertEqual(preview_rows[1].type, "expense")

    def test_parse_pdf_statement_preview_detects_td_profile_and_filters_headers(self) -> None:
        text = """
TD Canada Trust
Statement period 12/28/2024 - 01/10/2025
Transaction Date Description Amount
Jan 02 PAYROLL DEPOSIT $1,500.00
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        self.assertEqual(
            result["notes"],
            ["Detected bank profile: TD Canada Trust. Using generic parser with bank-aware noise filtering; review carefully."],
        )
        self.assertEqual(len(result["preview_rows"]), 1)
        self.assertEqual(result["preview_rows"][0].date, "2025-01-02")

    def test_parse_pdf_statement_preview_supports_bmo_french_rows(self) -> None:
        text = """
BMO Banque de Montr/e8al
Relev/e8 de Services bancaires courants
P/e8riode termin/e8e le /1/3 Avril /2/0/2/6
Montants d/e8duits Montants ajout/e8s
Date Description de votre compte /28$/29 /e0 votre compte /28$/29 Solde /28$/29
/1/6 Mars Achat par carte de d/e8bit/2c MCDONALD/27S #/4/0/0 /6/2c/2/1 /2/6/0/2c/0/5
/1/7 Mars Virement INTERAC re/e7u /3/6/2/2c/0/0 /5/1/0/2c/8/2
/0/1 er Avr R/e8gl/2e de fact/2e en ligne/2c HAZELVIEW PROP /1 /3/8/8/2c/0/0 /1/5/2c/8/4
/1/3 Avr Totaux /e0 la fermeture /7 /1/5/4/2c/9/4 /6 /6/9/3/2c/5/2
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        self.assertEqual(
            result["notes"],
            [
                "Detected bank profile: BMO French. Using running-balance checks to infer income vs expense direction."
            ],
        )
        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 3)
        self.assertEqual(preview_rows[0].date, "2026-03-16")
        self.assertEqual(preview_rows[0].description, "MCDONALD'S #400")
        self.assertEqual(preview_rows[0].amount, 6.21)
        self.assertEqual(preview_rows[0].type, "expense")
        self.assertEqual(preview_rows[1].date, "2026-03-17")
        self.assertEqual(preview_rows[1].type, "income")
        self.assertEqual(preview_rows[1].amount, 362.00)
        self.assertEqual(preview_rows[2].date, "2026-04-01")
        self.assertEqual(preview_rows[2].description, "Online bill payment HAZELVIEW PROP")
        self.assertEqual(preview_rows[2].amount, 1388.00)

    def test_parse_pdf_statement_preview_supports_transaction_and_posted_dates(self) -> None:
        text = """
TD Canada Trust
Statement period 12/28/2024 - 01/10/2025
Transaction Date Posted Date Description Debit Credit Balance
Jan 02 Jan 03 PAYROLL 0.00 1,500.00 1,700.00
Jan 03 Jan 04 MONTHLY FEE 15.99 0.00 1,684.01
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].date, "2025-01-02")
        self.assertEqual(preview_rows[0].description, "PAYROLL")
        self.assertEqual(preview_rows[0].type, "income")
        self.assertGreaterEqual(preview_rows[0].confidence, 0.9)
        self.assertIsNone(preview_rows[0].review_reason)
        self.assertEqual(preview_rows[1].date, "2025-01-03")
        self.assertEqual(preview_rows[1].description, "MONTHLY FEE")
        self.assertEqual(preview_rows[1].type, "expense")
        self.assertGreaterEqual(preview_rows[1].confidence, 0.9)
        self.assertIsNone(preview_rows[1].review_reason)

    def test_parse_pdf_statement_preview_supports_numeric_transaction_and_posted_dates(self) -> None:
        text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
01/02 01/03 BOOK STORE $12.34
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 1)
        self.assertEqual(preview_rows[0].date, "2025-01-02")
        self.assertEqual(preview_rows[0].description, "BOOK STORE")
        self.assertEqual(preview_rows[0].amount, 12.34)

    def test_parse_pdf_statement_preview_supports_cibc_credit_debit_markers(self) -> None:
        text = """
Canadian Imperial Bank of Commerce
Statement period 12/28/2024 - 01/10/2025
Transaction Date Description Amount
Jan 02 PAYROLL 1,500.00CR
Jan 03 MONTHLY FEE 15.99DR
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].type, "income")
        self.assertEqual(preview_rows[0].amount, 1500.00)
        self.assertEqual(preview_rows[1].type, "expense")
        self.assertEqual(preview_rows[1].amount, 15.99)

    def test_parse_pdf_statement_preview_supports_debit_credit_balance_columns(self) -> None:
        text = """
TD Canada Trust
Statement period 12/28/2024 - 01/10/2025
Transaction Date Description Debit Credit Balance
Jan 02 PAYROLL 0.00 1,500.00 1,700.00
Jan 03 MONTHLY FEE 15.99 0.00 1,684.01
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].type, "income")
        self.assertEqual(preview_rows[0].amount, 1500.00)
        self.assertIn("balance=1,700.00", preview_rows[0].source_line or "")
        self.assertGreaterEqual(preview_rows[0].confidence, 0.9)
        self.assertEqual(preview_rows[1].type, "expense")
        self.assertEqual(preview_rows[1].amount, 15.99)
        self.assertIn("balance=1,684.01", preview_rows[1].source_line or "")
        self.assertGreaterEqual(preview_rows[1].confidence, 0.9)

    def test_parse_pdf_statement_preview_flags_amount_balance_without_direction(self) -> None:
        text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
Jan 03 FARMERS MARKET $12.34 $1,684.01
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_row = result["preview_rows"][0]
        self.assertEqual(preview_row.type, "expense")
        self.assertLess(preview_row.confidence, 0.75)
        self.assertIn("no debit or credit marker", preview_row.review_reason or "")

    def test_parse_pdf_statement_preview_supports_placeholder_debit_credit_columns(self) -> None:
        text = """
TD Canada Trust
Statement period 12/28/2024 - 01/10/2025
Transaction Date Description Debit Credit Balance
Jan 02 PAYROLL - 1,500.00 1,700.00
Jan 03 MONTHLY FEE 15.99 - 1,684.01
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].type, "income")
        self.assertEqual(preview_rows[0].amount, 1500.00)
        self.assertEqual(preview_rows[1].type, "expense")
        self.assertEqual(preview_rows[1].amount, 15.99)

    def test_parse_pdf_statement_preview_uses_statement_period_to_disambiguate_numeric_dates(self) -> None:
        text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
03/01 BOOK STORE $12.34
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 1)
        self.assertEqual(preview_rows[0].date, "2025-01-03")

    def test_parse_pdf_statement_preview_reports_scanned_or_image_only_pdf(self) -> None:
        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(
                    "",
                    total_pages=2,
                    readable_text_pages=0,
                    page_texts=("", ""),
                ),
            ),
            patch.object(service, "extract_pdf_page_image_candidates", return_value=[]),
            patch.object(service, "is_local_ocr_enabled", return_value=False),
            patch.object(service, "is_vision_ocr_enabled", return_value=False),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "No page images could be extracted or rendered for OCR fallback.",
            ):
                service.parse_pdf_statement_preview(
                    db=self.db,
                    owner_id=123,
                    file_bytes=b"fake-pdf",
                )

    def test_parse_pdf_statement_preview_reports_missing_tesseract_for_scanned_pdf(self) -> None:
        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(
                    "",
                    total_pages=1,
                    readable_text_pages=0,
                    page_texts=("",),
                ),
            ),
            patch.object(
                service,
                "extract_pdf_page_image_candidates",
                return_value=[
                    service.PdfPageImageCandidate(
                        page_number=1,
                        name="rendered-page-1.png",
                        data=b"fake-image",
                        mime_type="image/png",
                    )
                ],
            ),
            patch.object(service, "is_local_ocr_enabled", return_value=False),
            patch.object(service, "is_vision_ocr_enabled", return_value=False),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "Deploy the backend with Docker so Tesseract is installed",
            ):
                service.parse_pdf_statement_preview(
                    db=self.db,
                    owner_id=123,
                    file_bytes=b"fake-pdf",
                )

    def test_parse_pdf_statement_preview_uses_local_ocr_fallback_for_scanned_pdf(self) -> None:
        ocr_text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
Jan 02 PAYROLL DEPOSIT $1,500.00
Jan 03 BOOK STORE $12.34
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(
                    "",
                    total_pages=2,
                    readable_text_pages=0,
                    page_texts=("", ""),
                ),
            ),
            patch.object(
                service,
                "extract_pdf_page_image_candidates",
                return_value=[
                    service.PdfPageImageCandidate(
                        page_number=1,
                        name="page-1.jpg",
                        data=b"fake-image",
                        mime_type="image/jpeg",
                    )
                ],
            ),
            patch.object(service, "is_local_ocr_enabled", return_value=True),
            patch.object(
                service,
                "ocr_pdf_page_images_with_local_tesseract",
                return_value=service.PdfOcrFallbackResult(
                    text=ocr_text,
                    notes=(
                        "Used free local Tesseract OCR on 1 scanned PDF page. Review extracted rows carefully.",
                    ),
                    candidate_pages=1,
                    processed_pages=1,
                ),
            ),
            patch.object(service, "is_vision_ocr_enabled", return_value=False),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].date, "2025-01-02")
        self.assertEqual(preview_rows[0].type, "income")
        self.assertEqual(preview_rows[1].date, "2025-01-03")
        self.assertEqual(result["notes"], [
            "Used generic PDF parser. Accuracy may vary for this bank format.",
            "Used free local Tesseract OCR on 1 scanned PDF page. Review extracted rows carefully.",
        ])

    def test_parse_pdf_statement_preview_uses_openai_ocr_fallback_for_scanned_pdf(self) -> None:
        ocr_text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
Jan 02 PAYROLL DEPOSIT $1,500.00
Jan 03 BOOK STORE $12.34
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(
                    "",
                    total_pages=2,
                    readable_text_pages=0,
                    page_texts=("", ""),
                ),
            ),
            patch.object(
                service,
                "extract_pdf_page_image_candidates",
                return_value=[
                    service.PdfPageImageCandidate(
                        page_number=1,
                        name="page-1.jpg",
                        data=b"fake-image",
                        mime_type="image/jpeg",
                    )
                ],
            ),
            patch.object(service, "is_local_ocr_enabled", return_value=False),
            patch.object(service, "is_vision_ocr_enabled", return_value=True),
            patch.object(
                service,
                "ocr_pdf_page_images_to_text",
                return_value=service.PdfOcrFallbackResult(
                    text=ocr_text,
                    notes=("Used OCR fallback on 1 scanned PDF page. Review extracted rows carefully.",),
                    candidate_pages=1,
                    processed_pages=1,
                ),
            ),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        preview_rows = result["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0].date, "2025-01-02")
        self.assertEqual(preview_rows[0].type, "income")
        self.assertEqual(preview_rows[1].date, "2025-01-03")
        self.assertEqual(result["notes"], [
            "Used generic PDF parser. Accuracy may vary for this bank format.",
            "Used OCR fallback on 1 scanned PDF page. Review extracted rows carefully.",
        ])

    def test_parse_pdf_statement_preview_adds_note_for_partially_readable_pdf(self) -> None:
        text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
Jan 02 PAYROLL DEPOSIT $1,500.00
        """.strip()

        with (
            patch.object(
                service,
                "extract_pdf_text_result",
                return_value=self.extraction_result(text, total_pages=3, readable_text_pages=1),
            ),
            patch.object(service, "extract_pdf_page_image_candidates", return_value=[]),
            patch.object(service, "categorize_transaction_details", side_effect=self.categorize),
        ):
            result = service.parse_pdf_statement_preview(
                db=self.db,
                owner_id=123,
                file_bytes=b"fake-pdf",
            )

        self.assertEqual(
            result["notes"],
            [
                "Used generic PDF parser. Accuracy may vary for this bank format.",
                "Only 1 of 3 PDF pages contained selectable text. Image-only pages were checked for OCR fallback when available.",
            ],
        )

    def test_parse_pdf_statement_preview_reports_unrecognized_layout_when_text_exists(self) -> None:
        text = """
Account Statement
Statement period 12/28/2024 - 01/10/2025
Important information about your account
Please check this account statement
        """.strip()

        with patch.object(
            service,
            "extract_pdf_text_result",
            return_value=self.extraction_result(text),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "Readable text was extracted from this PDF, but no transaction rows were recognized.",
            ):
                service.parse_pdf_statement_preview(
                    db=self.db,
                    owner_id=123,
                    file_bytes=b"fake-pdf",
                )


if __name__ == "__main__":
    unittest.main()
