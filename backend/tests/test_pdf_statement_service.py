from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import MagicMock, patch

from app.services import pdf_statement_service as service


class PdfStatementServiceHelpersTest(unittest.TestCase):
    def test_parse_amount_token_supports_bank_formats(self) -> None:
        self.assertAlmostEqual(service.parse_amount_token("$1,234.56") or 0.0, 1234.56)
        self.assertAlmostEqual(service.parse_amount_token("($89.10)") or 0.0, -89.10)
        self.assertAlmostEqual(service.parse_amount_token("-$15.75") or 0.0, -15.75)
        self.assertAlmostEqual(service.parse_amount_token("$1,500.00CR") or 0.0, 1500.00)
        self.assertAlmostEqual(service.parse_amount_token("$15.99DR") or 0.0, -15.99)
        self.assertAlmostEqual(service.parse_amount_token("12.34-") or 0.0, -12.34)

    def test_split_line_and_trailing_amounts_extracts_multiple_tokens(self) -> None:
        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "GROCERY STORE TORONTO $45.67 $1,234.56"
        )

        self.assertEqual(body, "GROCERY STORE TORONTO")
        self.assertEqual(trailing_amounts, ["$45.67", "$1,234.56"])

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


class PdfStatementServicePreviewParsingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = MagicMock()

    def categorize(self, **kwargs: str) -> str:
        return "income" if kwargs["tx_type"] == "income" else "other"

    def extraction_result(
        self,
        text: str,
        total_pages: int = 1,
        readable_text_pages: int = 1,
    ) -> service.PdfTextExtractionResult:
        return service.PdfTextExtractionResult(
            text=text,
            total_pages=total_pages,
            readable_text_pages=readable_text_pages,
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

        with patch.object(service, "categorize_transaction", side_effect=self.categorize):
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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
        self.assertEqual(preview_rows[1].date, "2025-01-03")
        self.assertEqual(preview_rows[1].description, "MONTHLY FEE")
        self.assertEqual(preview_rows[1].type, "expense")

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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
        self.assertEqual(preview_rows[1].type, "expense")
        self.assertEqual(preview_rows[1].amount, 15.99)
        self.assertIn("balance=1,684.01", preview_rows[1].source_line or "")

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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
        with patch.object(
            service,
            "extract_pdf_text_result",
            return_value=self.extraction_result("", total_pages=2, readable_text_pages=0),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "This PDF appears to have no selectable text. It may be image-only or scanned.",
            ):
                service.parse_pdf_statement_preview(
                    db=self.db,
                    owner_id=123,
                    file_bytes=b"fake-pdf",
                )

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
            patch.object(service, "categorize_transaction", side_effect=self.categorize),
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
                "Only 1 of 3 PDF pages contained readable text. Some pages may be image-only until OCR fallback is added.",
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
