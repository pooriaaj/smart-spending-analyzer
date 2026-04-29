from __future__ import annotations

import unittest
from collections.abc import Generator
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import Account, CategoryMemory, MerchantCategoryProfile, MerchantLookupCache, Transaction, User
from app.routes.transaction_routes import router as transaction_router
from app.services import pdf_statement_service


def build_text_pdf(lines: list[str]) -> bytes:
    def escape_pdf_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_lines = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        if index > 0:
            content_lines.append("0 -16 Td")
        content_lines.append(f"({escape_pdf_text(line)}) Tj")
    content_lines.append("ET")
    content_stream = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n"
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\n"
            b"endobj\n"
        ),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            f"5 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
            + content_stream
            + b"\nendstream\nendobj\n"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(pdf)


class SmartImportRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        cls.session_local = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False, future=True)
        Base.metadata.create_all(bind=cls.engine)

        with cls.session_local() as session:
            user = User(email="tester@example.com", password_hash="hashed")
            session.add(user)
            session.flush()

            account = Account(
                name="Testing Account",
                type="chequing",
                owner_id=user.id,
                is_active=True,
            )
            session.add(account)
            session.commit()

            cls.user_id = user.id
            cls.account_id = account.id

        app = FastAPI()
        app.include_router(transaction_router)

        def override_get_db() -> Generator[Session, None, None]:
            session = cls.session_local()
            try:
                yield session
            finally:
                session.close()

        def override_get_current_user() -> User:
            return User(id=cls.user_id, email="tester@example.com", password_hash="hashed")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def tearDown(self) -> None:
        with self.session_local() as session:
            session.query(Transaction).delete()
            session.query(CategoryMemory).delete()
            session.query(MerchantCategoryProfile).delete()
            session.query(MerchantLookupCache).delete()
            session.commit()

    def test_transactions_route_returns_legacy_rows_without_account(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=42.5,
                    category="legacy",
                    description="Older imported transaction",
                    date=date(2026, 4, 12),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=None,
                )
            )
            session.commit()

        response = self.client.get("/transactions/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertIsNone(payload[0]["account_id"])
        self.assertEqual(payload[0]["description"], "Older imported transaction")

    def test_import_file_returns_rbc_preview_from_pdf_upload(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From December 15, 2024 to January 15, 2025",
                "15 Dec COFFEE SHOP $5.25 $1,200.00",
                "02 Jan DIRECT DEPOSIT PAYROLL $2,000.00 $3,200.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("rbc-statement.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["detected_type"], "pdf_statement")
        self.assertEqual(payload["status"], "table_review")
        self.assertEqual(len(payload["preview_rows"]), 2)
        self.assertEqual(payload["preview_rows"][0]["date"], "2024-12-15")
        self.assertIn("confidence", payload["preview_rows"][0])
        self.assertIn("review_reason", payload["preview_rows"][0])
        self.assertEqual(payload["preview_rows"][1]["date"], "2025-01-02")
        self.assertEqual(payload["preview_rows"][1]["type"], "income")

    def test_import_file_cleans_rbc_descriptions_before_categorizing(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 8572",
                "ORANGE MART 15.51 10.00",
                "4 Mar Contactless Interac Transit - 0620",
                "PRES/R8SFN9RVZG 3.30 6.70",
                "5 Mar ATM deposit - TZ661796 100.00 106.70",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("rbc-cleaning.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]

        self.assertEqual([row["description"] for row in preview_rows], ["ORANGE MART", "Transit", "ATM deposit"])
        self.assertEqual([row["category"] for row in preview_rows], ["groceries", "transport", "income"])
        self.assertTrue(all(row["review_reason"] is None for row in preview_rows))

    def test_import_file_uses_merchant_semantics_for_unknown_food_merchants(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 1001",
                "KHORAK SUPERMAR 15.51 100.00",
                "4 Mar Contactless Interac purchase - 1002",
                "ARZON SUPERMARK 20.25 79.75",
                "5 Mar Contactless Interac purchase - 1003",
                "BAGEL NASH 8.50 71.25",
                "6 Mar Contactless Interac purchase - 1004",
                "THAI ISLAND RES 18.25 53.00",
                "7 Mar Misc Payment Paypal * BAGEL NASH 9.25 43.75",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("merchant-semantics.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]

        self.assertEqual(
            [row["category"] for row in preview_rows],
            ["groceries", "groceries", "restaurant", "restaurant", "restaurant"],
        )
        self.assertTrue(
            all(row["category_source"] in {"merchant_semantic", "merchant_lookup_cache"} for row in preview_rows)
        )
        with self.session_local() as session:
            cached_count = session.query(MerchantLookupCache).count()

        self.assertGreaterEqual(cached_count, 4)

    def test_batch_statement_import_accepts_up_to_six_files(self) -> None:
        csv_one = (
            "Date,Description,Amount,Type,Category\n"
            "2025-01-03,Metro Groceries,54.25,expense,groceries\n"
        ).encode("utf-8")
        csv_two = (
            "Date,Description,Amount,Type,Category\n"
            "2025-01-04,Payroll Deposit,2000.00,income,salary\n"
        ).encode("utf-8")

        response = self.client.post(
            "/transactions/import/files",
            data={"account_id": str(self.account_id)},
            files=[
                ("files", ("january.csv", csv_one, "text/csv")),
                ("files", ("february.csv", csv_two, "text/csv")),
            ],
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "table_review")
        self.assertEqual(payload["import_summary"]["imported"], 0)
        self.assertEqual(len(payload["preview_rows"]), 2)
        self.assertEqual(len(payload["notes"]), 2)

        with self.session_local() as session:
            transaction_count = (
                session.query(Transaction)
                .filter(Transaction.owner_id == self.user_id)
                .count()
            )

        self.assertEqual(transaction_count, 0)

        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": payload["preview_rows"],
            },
        )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        self.assertEqual(confirm_response.json()["imported"], 2)

    def test_batch_statement_import_combines_pdf_preview_rows(self) -> None:
        first_pdf = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From January 1, 2025 to January 31, 2025",
                "03 Jan COFFEE SHOP $5.25 $1,200.00",
            ]
        )
        second_pdf = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From February 1, 2025 to February 28, 2025",
                "04 Feb GROCERY STORE $42.10 $1,100.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/files",
            data={"account_id": str(self.account_id)},
            files=[
                ("files", ("january.pdf", first_pdf, "application/pdf")),
                ("files", ("february.pdf", second_pdf, "application/pdf")),
            ],
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "table_review")
        self.assertEqual(len(payload["preview_rows"]), 2)
        self.assertIn("january.pdf", payload["preview_rows"][0]["source_line"])
        self.assertIn("february.pdf", payload["preview_rows"][1]["source_line"])

    def test_batch_statement_import_rejects_more_than_six_files_for_free_plan(self) -> None:
        statement = (
            "Date,Description,Amount,Type,Category\n"
            "2025-01-03,Metro Groceries,54.25,expense,groceries\n"
        ).encode("utf-8")

        response = self.client.post(
            "/transactions/import/files",
            data={"account_id": str(self.account_id)},
            files=[
                ("files", (f"statement-{index}.csv", statement, "text/csv"))
                for index in range(7)
            ],
        )

        self.assertEqual(response.status_code, 402, response.text)
        self.assertIn("Upgrade to Premium", response.json()["detail"])

    def test_confirm_preview_import_persists_rows_after_pdf_preview(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Account Statement",
                "From December 28, 2024 to January 10, 2025",
                "28 Dec BOOK STORE ($12.34)",
                "02 Jan INCOME TAX REFUND $150.00",
            ]
        )

        preview_response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("generic-statement.pdf", pdf_bytes, "application/pdf")},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)

        preview_payload = preview_response.json()
        self.assertEqual(preview_payload["notes"], ["Used generic PDF parser. Accuracy may vary for this bank format."])
        self.assertEqual(len(preview_payload["preview_rows"]), 2)

        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": preview_payload["preview_rows"],
            },
        )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        self.assertEqual(
            confirm_response.json(),
            {
                "message": "Preview import completed",
                "imported": 2,
                "duplicates_skipped": 0,
                "invalid_rows_skipped": 0,
            },
        )

        with self.session_local() as session:
            transactions = session.query(Transaction).order_by(Transaction.date.asc()).all()

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0].date.isoformat(), "2024-12-28")
        self.assertEqual(transactions[0].amount, 12.34)
        self.assertEqual(transactions[0].type, "expense")
        self.assertEqual(transactions[1].date.isoformat(), "2025-01-02")
        self.assertEqual(transactions[1].type, "income")

    def test_import_file_marks_existing_and_in_preview_duplicates(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=12.34,
                    category="shopping",
                    description="BOOK STORE",
                    date=date(2024, 12, 28),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.account_id,
                )
            )
            session.commit()

        pdf_bytes = build_text_pdf(
            [
                "Account Statement",
                "From December 28, 2024 to December 31, 2024",
                "28 Dec BOOK STORE $12.34",
                "29 Dec GIFT SHOP $50.00",
                "29 Dec GIFT SHOP $50.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("duplicate-check.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual(len(preview_rows), 3)
        self.assertTrue(preview_rows[0]["is_duplicate"])
        self.assertEqual(preview_rows[0]["duplicate_reason"], "Already written as BOOK STORE.")
        self.assertEqual(preview_rows[0]["reconciliation_status"], "matched")
        self.assertFalse(preview_rows[1]["is_duplicate"])
        self.assertIsNone(preview_rows[1]["duplicate_reason"])
        self.assertEqual(preview_rows[1]["reconciliation_status"], "missing")
        self.assertTrue(preview_rows[2]["is_duplicate"])
        self.assertEqual(
            preview_rows[2]["duplicate_reason"],
            "Duplicate of another row in this preview.",
        )

    def test_statement_reconciliation_matches_manual_transaction_with_different_category(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=8.75,
                    category="coffee with friend",
                    description="Morning latte",
                    date=date(2025, 1, 5),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.account_id,
                )
            )
            session.commit()

        pdf_bytes = build_text_pdf(
            [
                "Account Statement",
                "From January 1, 2025 to January 31, 2025",
                "05 Jan TIM HORTONS $8.75",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("january-check.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_row = response.json()["preview_rows"][0]
        self.assertTrue(preview_row["is_duplicate"])
        self.assertEqual(preview_row["reconciliation_status"], "matched")
        self.assertEqual(preview_row["duplicate_reason"], "Already written as Morning latte.")
        self.assertIsNotNone(preview_row["matched_transaction_id"])

        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": [preview_row],
            },
        )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        self.assertEqual(confirm_response.json()["imported"], 0)
        self.assertEqual(confirm_response.json()["duplicates_skipped"], 1)

    def test_statement_preview_flags_repeating_income_and_expense_patterns(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="salary",
                        description="DIRECT DEPOSIT PAYROLL",
                        date=date(2025, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=45.0,
                        category="health",
                        description="GYM MEMBERSHIP",
                        date=date(2025, 1, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                ]
            )
            session.commit()

        pdf_bytes = build_text_pdf(
            [
                "Account Statement",
                "From February 1, 2025 to February 28, 2025",
                "03 Feb DIRECT DEPOSIT PAYROLL $2,000.00",
                "10 Feb GYM MEMBERSHIP $45.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("february-check.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        payroll_row = next(item for item in preview_rows if "PAYROLL" in item["description"])
        gym_row = next(item for item in preview_rows if "GYM" in item["description"])

        self.assertTrue(payroll_row["is_repeating_pattern"])
        self.assertEqual(payroll_row["repeating_pattern_type"], "income")
        self.assertIn("repeating income", payroll_row["repeating_pattern_reason"].lower())

        self.assertTrue(gym_row["is_repeating_pattern"])
        self.assertEqual(gym_row["repeating_pattern_type"], "expense")
        self.assertIn("repeating expense", gym_row["repeating_pattern_reason"].lower())

    def test_fresh_start_deletes_old_transactions_and_keeps_current_life(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=20.00,
                        category="legacy",
                        description="Old statement row",
                        date=date(2024, 12, 28),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=9.50,
                        category="groceries",
                        description="Today groceries",
                        date=date(2025, 1, 2),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/transactions/fresh-start",
            json={
                "keep_from": "2025-01-01",
                "account_id": self.account_id,
                "delete_all": False,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["deleted_count"], 1)

        with self.session_local() as session:
            remaining = session.query(Transaction).filter(Transaction.owner_id == self.user_id).all()

        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].description, "Today groceries")

    def test_import_file_reports_pdf_with_no_selectable_text(self) -> None:
        pdf_bytes = build_text_pdf([])

        with (
            patch.object(pdf_statement_service, "extract_pdf_page_image_candidates", return_value=[]),
            patch.object(pdf_statement_service, "is_vision_ocr_enabled", return_value=False),
        ):
            response = self.client.post(
                "/transactions/import/file",
                data={"account_id": str(self.account_id)},
                files={"file": ("scanned.pdf", pdf_bytes, "application/pdf")},
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "This PDF appears to have no selectable text. It may be image-only or scanned. "
                    "Add a valid OPENAI_API_KEY to enable OCR fallback for scanned PDFs."
                )
            },
        )

    def test_import_file_uses_ocr_fallback_for_scanned_pdf(self) -> None:
        pdf_bytes = build_text_pdf([])

        with (
            patch.object(
                pdf_statement_service,
                "extract_pdf_text_result",
                return_value=pdf_statement_service.PdfTextExtractionResult(
                    text="",
                    total_pages=1,
                    readable_text_pages=0,
                    page_texts=("",),
                ),
            ),
            patch.object(
                pdf_statement_service,
                "extract_pdf_page_image_candidates",
                return_value=[
                    pdf_statement_service.PdfPageImageCandidate(
                        page_number=1,
                        name="page-1.jpg",
                        data=b"fake-image",
                        mime_type="image/jpeg",
                    )
                ],
            ),
            patch.object(pdf_statement_service, "is_vision_ocr_enabled", return_value=True),
            patch.object(
                pdf_statement_service,
                "ocr_pdf_page_images_to_text",
                return_value=pdf_statement_service.PdfOcrFallbackResult(
                    text=(
                        "Account Statement\n"
                        "Statement period 12/28/2024 - 01/10/2025\n"
                        "Jan 02 PAYROLL DEPOSIT $1,500.00"
                    ),
                    notes=("Used OCR fallback on 1 scanned PDF page. Review extracted rows carefully.",),
                    candidate_pages=1,
                    processed_pages=1,
                ),
            ),
        ):
            response = self.client.post(
                "/transactions/import/file",
                data={"account_id": str(self.account_id)},
                files={"file": ("scanned-ocr.pdf", pdf_bytes, "application/pdf")},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "table_review")
        self.assertEqual(len(payload["preview_rows"]), 1)
        self.assertEqual(payload["preview_rows"][0]["date"], "2025-01-02")
        self.assertEqual(
            payload["notes"],
            [
                "Used generic PDF parser. Accuracy may vary for this bank format.",
                "Used OCR fallback on 1 scanned PDF page. Review extracted rows carefully.",
            ],
        )

    def test_import_file_reports_unrecognized_pdf_layout_when_text_exists(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Account Statement",
                "Statement period 12/28/2024 - 01/10/2025",
                "Important information about your account",
                "Please check this account statement",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("needs-tuning.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Readable text was extracted from this PDF, but no transaction rows were recognized. "
                    "This bank layout may need more parser tuning."
                )
            },
        )

    def test_create_transaction_saves_category_memory_for_future_suggestions(self) -> None:
        categorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 18.25,
                "category": "restaurant",
                "description": "Chipotle Yorkdale",
                "date": "2025-01-03",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(categorized_response.status_code, 200, categorized_response.text)

        uncategorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 16.10,
                "category": "other",
                "description": "Chipotle Union",
                "date": "2025-01-04",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(uncategorized_response.status_code, 200, uncategorized_response.text)

        preview_response = self.client.get(
            "/transactions/categorize/bulk-preview",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        suggestions = preview_response.json()["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["description"], "Chipotle Union")
        self.assertEqual(suggestions[0]["suggested_category"], "restaurant")
        self.assertEqual(suggestions[0]["matched_keyword"], "chipotle")
        self.assertIn("learned category memory", suggestions[0]["reason"].lower())

        with self.session_local() as session:
            memories = session.query(CategoryMemory).filter(CategoryMemory.owner_id == self.user_id).all()

        self.assertTrue(any(memory.keyword == "chipotle" for memory in memories))

    def test_create_transaction_persists_when_category_memory_fails(self) -> None:
        with patch(
            "app.routes.transaction_routes.save_category_memory",
            side_effect=RuntimeError("learning unavailable"),
        ):
            response = self.client.post(
                "/transactions/",
                json={
                    "amount": 11.00,
                    "category": "personal",
                    "description": "Cigar",
                    "date": "2026-04-26",
                    "type": "expense",
                    "account_id": self.account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["description"], "Cigar")
        self.assertEqual(payload["amount"], 11.0)

        with self.session_local() as session:
            saved = (
                session.query(Transaction)
                .filter(
                    Transaction.owner_id == self.user_id,
                    Transaction.description == "Cigar",
                )
                .one_or_none()
            )

        self.assertIsNotNone(saved)

    def test_confirm_preview_import_saves_category_memory_for_future_suggestions(self) -> None:
        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": [
                    {
                        "date": "2025-01-03",
                        "description": "Sephora Eaton",
                        "amount": 42.15,
                        "type": "expense",
                        "category": "personal",
                    }
                ],
            },
        )
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)

        uncategorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 28.40,
                "category": "other",
                "description": "Sephora Yorkdale",
                "date": "2025-01-04",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(uncategorized_response.status_code, 200, uncategorized_response.text)

        preview_response = self.client.get(
            "/transactions/categorize/bulk-preview",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        suggestions = preview_response.json()["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["description"], "Sephora Yorkdale")
        self.assertEqual(suggestions[0]["suggested_category"], "personal")
        self.assertEqual(suggestions[0]["matched_keyword"], "sephora")
        self.assertIn("learned category memory", suggestions[0]["reason"].lower())

    def test_confirm_preview_import_does_not_fail_when_learning_memory_fails(self) -> None:
        with patch(
            "app.routes.transaction_routes.save_category_memory",
            side_effect=RuntimeError("learning table unavailable"),
        ):
            confirm_response = self.client.post(
                "/transactions/import/confirm-preview",
                json={
                    "account_id": self.account_id,
                    "rows": [
                        {
                            "date": "2025-01-03",
                            "description": "Metro Groceries",
                            "amount": 54.25,
                            "type": "expense",
                            "category": "groceries",
                        }
                    ],
                },
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        payload = confirm_response.json()
        self.assertEqual(payload["imported"], 1)
        self.assertEqual(payload["invalid_rows_skipped"], 0)

        with self.session_local() as session:
            imported_transaction = (
                session.query(Transaction)
                .filter(
                    Transaction.owner_id == self.user_id,
                    Transaction.description == "Metro Groceries",
                )
                .one_or_none()
            )

        self.assertIsNotNone(imported_transaction)

    def test_confirmed_categories_train_learned_merchant_profiles(self) -> None:
        categorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 42.15,
                "category": "Beauty Treat",
                "description": "Sephora Eaton Centre",
                "date": "2025-01-03",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(categorized_response.status_code, 200, categorized_response.text)

        uncategorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 28.40,
                "category": "other",
                "description": "Sephora Yorkdale",
                "date": "2025-01-04",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(uncategorized_response.status_code, 200, uncategorized_response.text)

        preview_response = self.client.get(
            "/transactions/categorize/bulk-preview",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        suggestions = preview_response.json()["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["description"], "Sephora Yorkdale")
        self.assertEqual(suggestions[0]["suggested_category"], "beauty treat")
        self.assertEqual(suggestions[0]["matched_keyword"], "sephora")
        self.assertIn("learned merchant profile", suggestions[0]["reason"].lower())

        with self.session_local() as session:
            profile = (
                session.query(MerchantCategoryProfile)
                .filter(
                    MerchantCategoryProfile.owner_id == self.user_id,
                    MerchantCategoryProfile.merchant_key == "sephora",
                )
                .one()
            )

        self.assertEqual(profile.category, "beauty treat")
        self.assertGreaterEqual(profile.confirmation_count, 1)

    def test_normalize_categories_route_backfills_category_memory(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=33.50,
                        category="Personal",
                        description="Aesop Queen",
                        date=date(2025, 1, 3),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=19.25,
                        category="other",
                        description="Aesop King",
                        date=date(2025, 1, 4),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                ]
            )
            session.commit()

        normalize_response = self.client.post(
            "/transactions/normalize-categories",
            params={"account_id": self.account_id},
        )
        self.assertEqual(normalize_response.status_code, 200, normalize_response.text)
        payload = normalize_response.json()
        self.assertEqual(payload["updated_count"], 1)
        self.assertGreaterEqual(payload["memory_entries_created"], 1)

        preview_response = self.client.get(
            "/transactions/categorize/bulk-preview",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        suggestions = preview_response.json()["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["description"], "Aesop King")
        self.assertEqual(suggestions[0]["suggested_category"], "personal")
        self.assertEqual(suggestions[0]["matched_keyword"], "aesop")
        self.assertIn("learned category memory", suggestions[0]["reason"].lower())

    def test_bulk_category_preview_returns_rule_based_explanation(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=7.45,
                    category="other",
                    description="Starbucks Front",
                    date=date(2025, 1, 5),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.account_id,
                )
            )
            session.commit()

        preview_response = self.client.get(
            "/transactions/categorize/bulk-preview",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        suggestions = preview_response.json()["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["suggested_category"], "cafe")
        self.assertEqual(suggestions[0]["matched_keyword"], "starbucks")
        self.assertIn("merchant/category rule", suggestions[0]["reason"].lower())

    def test_bulk_category_preview_skips_low_confidence_fallback_suggestions(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=14.75,
                    category="other",
                    description="Unmapped Merchant 123",
                    date=date(2025, 1, 6),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.account_id,
                )
            )
            session.commit()

        preview_response = self.client.get(
            "/transactions/categorize/bulk-preview",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        suggestions = preview_response.json()["suggestions"]
        self.assertEqual(suggestions, [])

    def test_bulk_category_preview_sorts_stronger_suggestions_first(self) -> None:
        categorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 18.25,
                "category": "restaurant",
                "description": "Chipotle Yorkdale",
                "date": "2025-01-03",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(categorized_response.status_code, 200, categorized_response.text)

        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=16.10,
                        category="other",
                        description="Chipotle Union",
                        date=date(2025, 1, 4),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=7.45,
                        category="other",
                        description="Starbucks Front",
                        date=date(2025, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                ]
            )
            session.commit()

        preview_response = self.client.get(
            "/transactions/categorize/bulk-preview",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        suggestions = preview_response.json()["suggestions"]
        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[0]["description"], "Chipotle Union")
        self.assertGreater(suggestions[0]["confidence"], suggestions[1]["confidence"])

    def test_import_file_supports_numeric_period_and_month_first_dates(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Account Statement",
                "Statement period 12/28/2024 - 01/10/2025",
                "Jan 02 PAYROLL DEPOSIT $1,500.00",
                "01/03 BOOK STORE $12.34",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("generic-alt-dates.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0]["date"], "2025-01-02")
        self.assertEqual(preview_rows[0]["type"], "income")
        self.assertEqual(preview_rows[1]["date"], "2025-01-03")
        self.assertEqual(preview_rows[1]["amount"], 12.34)

    def test_import_file_reports_detected_td_profile(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "TD Canada Trust",
                "Statement period 12/28/2024 - 01/10/2025",
                "Transaction Date Description Amount",
                "Jan 02 PAYROLL DEPOSIT $1,500.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("td-statement.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(
            payload["notes"],
            ["Detected bank profile: TD Canada Trust. Using generic parser with bank-aware noise filtering; review carefully."],
        )
        self.assertEqual(len(payload["preview_rows"]), 1)
        self.assertEqual(payload["preview_rows"][0]["date"], "2025-01-02")

    def test_import_file_supports_transaction_and_posted_dates(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "TD Canada Trust",
                "Statement period 12/28/2024 - 01/10/2025",
                "Transaction Date Posted Date Description Debit Credit Balance",
                "Jan 02 Jan 03 PAYROLL 0.00 1,500.00 1,700.00",
                "Jan 03 Jan 04 MONTHLY FEE 15.99 0.00 1,684.01",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("td-posted-dates.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0]["date"], "2025-01-02")
        self.assertEqual(preview_rows[0]["description"], "PAYROLL")
        self.assertEqual(preview_rows[0]["type"], "income")
        self.assertEqual(preview_rows[1]["date"], "2025-01-03")
        self.assertEqual(preview_rows[1]["description"], "MONTHLY FEE")
        self.assertEqual(preview_rows[1]["type"], "expense")

    def test_import_file_supports_cibc_credit_debit_amount_markers(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Canadian Imperial Bank of Commerce",
                "Statement period 12/28/2024 - 01/10/2025",
                "Transaction Date Description Amount",
                "Jan 02 PAYROLL 1,500.00CR",
                "Jan 03 MONTHLY FEE 15.99DR",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("cibc-statement.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0]["type"], "income")
        self.assertEqual(preview_rows[0]["amount"], 1500.00)
        self.assertEqual(preview_rows[1]["type"], "expense")
        self.assertEqual(preview_rows[1]["amount"], 15.99)

    def test_import_file_supports_debit_credit_balance_columns(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "TD Canada Trust",
                "Statement period 12/28/2024 - 01/10/2025",
                "Transaction Date Description Debit Credit Balance",
                "Jan 02 PAYROLL 0.00 1,500.00 1,700.00",
                "Jan 03 MONTHLY FEE 15.99 0.00 1,684.01",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("td-columns.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0]["type"], "income")
        self.assertEqual(preview_rows[0]["amount"], 1500.00)
        self.assertEqual(preview_rows[1]["type"], "expense")
        self.assertEqual(preview_rows[1]["amount"], 15.99)

    def test_import_file_supports_placeholder_debit_credit_columns(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "TD Canada Trust",
                "Statement period 12/28/2024 - 01/10/2025",
                "Transaction Date Description Debit Credit Balance",
                "Jan 02 PAYROLL - 1,500.00 1,700.00",
                "Jan 03 MONTHLY FEE 15.99 - 1,684.01",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("td-placeholders.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual(len(preview_rows), 2)
        self.assertEqual(preview_rows[0]["type"], "income")
        self.assertEqual(preview_rows[0]["amount"], 1500.00)
        self.assertEqual(preview_rows[1]["type"], "expense")
        self.assertEqual(preview_rows[1]["amount"], 15.99)

    def test_import_file_uses_statement_period_to_disambiguate_numeric_dates(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Account Statement",
                "Statement period 12/28/2024 - 01/10/2025",
                "03/01 BOOK STORE $12.34",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("ambiguous-date.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual(len(preview_rows), 1)
        self.assertEqual(preview_rows[0]["date"], "2025-01-03")


if __name__ == "__main__":
    unittest.main()
