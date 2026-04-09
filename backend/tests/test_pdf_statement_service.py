from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services import pdf_statement_service as service


class PdfStatementServiceHelpersTest(unittest.TestCase):
    def test_parse_amount_token_supports_bank_formats(self) -> None:
        self.assertAlmostEqual(service.parse_amount_token("$1,234.56") or 0.0, 1234.56)
        self.assertAlmostEqual(service.parse_amount_token("($89.10)") or 0.0, -89.10)
        self.assertAlmostEqual(service.parse_amount_token("-$15.75") or 0.0, -15.75)

    def test_split_line_and_trailing_amounts_extracts_multiple_tokens(self) -> None:
        body, trailing_amounts = service.split_line_and_trailing_amounts(
            "GROCERY STORE TORONTO $45.67 $1,234.56"
        )

        self.assertEqual(body, "GROCERY STORE TORONTO")
        self.assertEqual(trailing_amounts, ["$45.67", "$1,234.56"])

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


class PdfStatementServicePreviewParsingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = MagicMock()

    def categorize(self, **kwargs: str) -> str:
        return "income" if kwargs["tx_type"] == "income" else "other"

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
            patch.object(service, "extract_pdf_text", return_value=text),
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


if __name__ == "__main__":
    unittest.main()
