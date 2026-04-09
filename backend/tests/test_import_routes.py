from __future__ import annotations

import unittest
from collections.abc import Generator
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import Account, Transaction, User
from app.routes.transaction_routes import router as transaction_router


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
            session.commit()

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
        self.assertEqual(payload["preview_rows"][1]["date"], "2025-01-02")
        self.assertEqual(payload["preview_rows"][1]["type"], "income")

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
        self.assertEqual(preview_rows[0]["duplicate_reason"], "Already exists in this account.")
        self.assertFalse(preview_rows[1]["is_duplicate"])
        self.assertIsNone(preview_rows[1]["duplicate_reason"])
        self.assertTrue(preview_rows[2]["is_duplicate"])
        self.assertEqual(
            preview_rows[2]["duplicate_reason"],
            "Duplicate of another row in this preview.",
        )


if __name__ == "__main__":
    unittest.main()
