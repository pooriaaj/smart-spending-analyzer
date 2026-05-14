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
from app.models import (
    Account,
    CategoryLearningEvent,
    CategoryMemory,
    MerchantCategoryProfile,
    MerchantLookupCache,
    Transaction,
    User,
    UserLearningPreference,
)
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
            session.query(CategoryLearningEvent).delete()
            session.query(CategoryMemory).delete()
            session.query(MerchantCategoryProfile).delete()
            session.query(MerchantLookupCache).delete()
            session.query(UserLearningPreference).delete()
            session.query(User).filter(User.id != self.user_id).delete()
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

    def test_transactions_page_filters_and_paginates_in_database(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=8.25,
                        category="cafe",
                        description="Coffee",
                        date=date(2026, 4, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=54.20,
                        category="groceries",
                        description="Metro grocery",
                        date=date(2026, 4, 11),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=2200.00,
                        category="salary",
                        description="Payroll",
                        date=date(2026, 4, 12),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                ]
            )
            session.commit()

        page_response = self.client.get(
            "/transactions/page",
            params={"account_id": self.account_id, "page": 2, "page_size": 2},
        )
        self.assertEqual(page_response.status_code, 200, page_response.text)
        page_payload = page_response.json()
        self.assertEqual(page_payload["total"], 3)
        self.assertEqual(page_payload["scope_total"], 3)
        self.assertEqual(page_payload["page"], 2)
        self.assertEqual(len(page_payload["items"]), 1)
        self.assertEqual(page_payload["available_months"], ["2026-04"])
        self.assertEqual(page_payload["available_categories"], ["cafe", "groceries", "salary"])

        filtered_response = self.client.get(
            "/transactions/page",
            params={
                "account_id": self.account_id,
                "type": "expense",
                "category": "groceries",
                "amount_min": 50,
                "amount_max": 100,
            },
        )
        self.assertEqual(filtered_response.status_code, 200, filtered_response.text)
        filtered_payload = filtered_response.json()
        self.assertEqual(filtered_payload["total"], 1)
        self.assertEqual(filtered_payload["scope_total"], 3)
        self.assertEqual(filtered_payload["items"][0]["description"], "Metro grocery")

    def test_update_transaction_applies_category_to_similar_account_rows(self) -> None:
        with self.session_local() as session:
            target = Transaction(
                amount=8.90,
                category="other",
                description="SQDC77068 MTL",
                date=date(2026, 3, 16),
                type="expense",
                owner_id=self.user_id,
                account_id=self.account_id,
            )
            sibling = Transaction(
                amount=12.60,
                category="other",
                description="SQDC77068 MTL",
                date=date(2026, 3, 16),
                type="expense",
                owner_id=self.user_id,
                account_id=self.account_id,
            )
            legacy_row = Transaction(
                amount=10.00,
                category="other",
                description="SQDC77068 MTL",
                date=date(2026, 3, 16),
                type="expense",
                owner_id=self.user_id,
                account_id=None,
            )
            session.add_all([target, sibling, legacy_row])
            session.commit()
            target_id = target.id
            sibling_id = sibling.id
            legacy_row_id = legacy_row.id

        response = self.client.put(
            f"/transactions/{target_id}",
            json={
                "amount": 8.90,
                "category": "Smoking",
                "description": "SQDC77068 MTL",
                "date": "2026-03-16",
                "type": "expense",
                "account_id": self.account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["category"], "smoking")

        with self.session_local() as session:
            sibling = session.get(Transaction, sibling_id)
            legacy_row = session.get(Transaction, legacy_row_id)
            event = (
                session.query(CategoryLearningEvent)
                .filter(
                    CategoryLearningEvent.owner_id == self.user_id,
                    CategoryLearningEvent.merchant_key == "sqdc",
                )
                .one()
            )

            self.assertEqual(sibling.category, "smoking")
            self.assertEqual(legacy_row.category, "other")
            self.assertEqual(event.signal_source, "manual_edit")
            self.assertEqual(event.affected_count, 2)

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

    def test_import_file_does_not_merge_reference_code_digits_into_amounts(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From January 1, 2026 to February 28, 2026",
                "27 Jan e-Transfer received MAHTAALIJANI CAmGNFb7 100.00 126.21",
                "06 Feb e-Transfer received MAHTAALIJANI CA3Y5xH5 200.00 211.78",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("rbc-statement.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]
        self.assertEqual([row["amount"] for row in preview_rows], [100.0, 200.0])
        self.assertTrue(all("7100" not in row["source_line"] for row in preview_rows))
        self.assertTrue(all("5200" not in row["source_line"] for row in preview_rows))

    def test_transfer_income_rules_override_stale_learned_income_memory(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CategoryMemory(
                        keyword="mahtaalijani",
                        category="income",
                        transaction_type="income",
                        owner_id=self.user_id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="mahtaalijani",
                        display_name="Mahtaalijani",
                        category="income",
                        transaction_type="income",
                        confidence=0.99,
                        confirmation_count=5,
                        last_amount=100.00,
                        owner_id=self.user_id,
                    ),
                ]
            )
            session.commit()

        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From January 1, 2026 to January 31, 2026",
                "27 Jan e-Transfer received MAHTAALIJANI CAmGNFb7 100.00 126.21",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("rbc-transfer-memory.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_row = response.json()["preview_rows"][0]
        self.assertEqual(preview_row["type"], "income")
        self.assertEqual(preview_row["category"], "transfer")
        self.assertEqual(preview_row["category_source"], "protected_rule")
        self.assertIn("not treated as earned income", preview_row["category_reason"])

    def test_suspicious_amount_repair_reviews_legacy_reference_digit_merges(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=7100.0,
                        category="income",
                        description="e-Transfer received MAHTAALIJANI",
                        date=date(2026, 1, 27),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=5200.0,
                        category="income",
                        description="e-Transfer received MAHTAALIJANI",
                        date=date(2026, 2, 6),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="transfer",
                        description="e-Transfer received MAHTAALIJANI",
                        date=date(2026, 2, 20),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                ]
            )
            session.commit()

        preview_response = self.client.get(
            "/transactions/amount-repairs/preview",
            params={"account_id": self.account_id},
        )

        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        candidates = preview_response.json()["candidates"]
        self.assertEqual([item["current_amount"] for item in candidates], [5200.0, 7100.0])
        self.assertEqual([item["suggested_amount"] for item in candidates], [200.0, 100.0])

        apply_response = self.client.post(
            "/transactions/amount-repairs/apply",
            json={
                "account_id": self.account_id,
                "transaction_ids": [item["transaction_id"] for item in candidates],
            },
        )

        self.assertEqual(apply_response.status_code, 200, apply_response.text)
        self.assertEqual(apply_response.json()["updated_count"], 2)
        with self.session_local() as session:
            amounts = [
                row.amount
                for row in session.query(Transaction).order_by(Transaction.date.asc()).all()
            ]
        self.assertEqual(amounts, [100.0, 200.0, 2000.0])

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
        self.assertEqual([row["category"] for row in preview_rows], ["groceries", "transport", "transfer"])
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
            all(
                row["category_source"]
                in {"rule", "merchant_override", "merchant_semantic", "merchant_lookup_cache"}
                for row in preview_rows
            )
        )

    def test_import_file_uses_anonymized_community_merchant_learning(self) -> None:
        with self.session_local() as session:
            first_user = User(email="community-one@example.com", password_hash="hashed")
            second_user = User(email="community-two@example.com", password_hash="hashed")
            session.add_all([first_user, second_user])
            session.flush()
            session.add_all(
                [
                    MerchantCategoryProfile(
                        merchant_key="narcos",
                        display_name="Narcos",
                        category="clothing",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        last_amount=44.0,
                        owner_id=first_user.id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="narcos",
                        display_name="Narcos",
                        category="clothing",
                        transaction_type="expense",
                        confidence=0.94,
                        confirmation_count=2,
                        last_amount=45.0,
                        owner_id=second_user.id,
                    ),
                ]
            )
            session.commit()

        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 3001",
                "NARCOS DRIP 44.00 56.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("community-learning.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_row = response.json()["preview_rows"][0]

        self.assertEqual(preview_row["category"], "clothing")
        self.assertEqual(preview_row["category_source"], "community_profile")
        self.assertGreaterEqual(preview_row["category_confidence"], 0.8)

        with self.session_local() as session:
            cached_learning = (
                session.query(MerchantLookupCache)
                .filter(
                    MerchantLookupCache.merchant_key == "narcos",
                    MerchantLookupCache.transaction_type == "expense",
                    MerchantLookupCache.provider == "community",
                )
                .one_or_none()
            )

        self.assertIsNotNone(cached_learning)
        self.assertEqual(cached_learning.category, "clothing")

        with self.session_local() as session:
            session.add(
                MerchantCategoryProfile(
                    merchant_key="narcos",
                    display_name="Narcos",
                    category="entertainment",
                    transaction_type="expense",
                    confidence=0.97,
                    confirmation_count=3,
                    last_amount=44.0,
                    owner_id=self.user_id,
                )
            )
            session.commit()

        personal_response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("personal-learning-wins.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(personal_response.status_code, 200, personal_response.text)
        personal_row = personal_response.json()["preview_rows"][0]
        self.assertEqual(personal_row["category"], "entertainment")
        self.assertEqual(personal_row["category_source"], "merchant_profile")

    def test_import_file_excludes_users_who_disabled_community_learning(self) -> None:
        with self.session_local() as session:
            disabled_user = User(email="community-disabled@example.com", password_hash="hashed")
            enabled_user = User(email="community-enabled@example.com", password_hash="hashed")
            session.add_all([disabled_user, enabled_user])
            session.flush()
            session.add(
                UserLearningPreference(
                    owner_id=disabled_user.id,
                    community_learning_enabled=False,
                )
            )
            session.add_all(
                [
                    MerchantCategoryProfile(
                        merchant_key="narcos",
                        display_name="Narcos",
                        category="clothing",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        last_amount=44.0,
                        owner_id=disabled_user.id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="narcos",
                        display_name="Narcos",
                        category="clothing",
                        transaction_type="expense",
                        confidence=0.94,
                        confirmation_count=2,
                        last_amount=45.0,
                        owner_id=enabled_user.id,
                    ),
                ]
            )
            session.commit()

        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 3001",
                "NARCOS DRIP 44.00 56.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("community-opt-out.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_row = response.json()["preview_rows"][0]

        self.assertNotEqual(preview_row["category_source"], "community_profile")
        self.assertNotEqual(preview_row["category"], "clothing")

    def test_import_file_uses_expanded_lifestyle_categories(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 2001",
                "WEED CIGAR VAPE 21.00 100.00",
                "4 Mar Contactless Interac purchase - 2002",
                "MOKSHA CANNABIS 18.25 81.75",
                "5 Mar Contactless Interac purchase - 2003",
                "MR. PUFFS YORK 7.65 74.10",
                "6 Mar Contactless Interac purchase - 2004",
                "AMBROSIA THORNH 86.30 12.20",
                "7 Mar Contactless Interac purchase - 2005",
                "SHOPPERS DRUG M 28.22 50.00",
                "8 Mar Misc Payment PAYPAL 14.94 35.06",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("expanded-categories.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]

        self.assertEqual(
            [row["category"] for row in preview_rows],
            ["smoking", "smoking", "restaurant", "groceries", "health", "transfer"],
        )
        paypal_row = preview_rows[-1]
        self.assertEqual(paypal_row["category_source"], "payment_processor")
        self.assertLess(paypal_row["category_confidence"], 0.7)
        self.assertTrue(paypal_row["category_review_required"])
        self.assertIn("weak or generic signal", paypal_row["category_review_reason"])
        self.assertEqual(preview_rows[3]["category_source"], "merchant_override")

    def test_import_file_strips_payment_processor_prefixes_safely(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 2201",
                "SQ *BAGEL NASH 12.00 100.00",
                "4 Mar Contactless Interac purchase - 2202",
                "TST*OPENAI 20.00 80.00",
                "5 Mar Contactless Interac purchase - 2203",
                "PYPL*CANVA 18.00 62.00",
                "6 Mar Contactless Interac purchase - 2204",
                "SQDC77068 MTL 8.90 53.10",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("processor-prefixes.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]

        self.assertEqual(
            [row["description"] for row in preview_rows],
            ["BAGEL NASH", "OPENAI", "CANVA", "SQDC77068 MTL"],
        )
        self.assertEqual(
            [row["category"] for row in preview_rows],
            ["restaurant", "subscriptions", "subscriptions", "smoking"],
        )
        self.assertNotIn("sq ", preview_rows[0]["description"].lower())
        self.assertEqual(preview_rows[-1]["category_source"], "merchant_override")

    def test_ambrosia_food_shop_does_not_pollute_ambrosia_restaurant_names(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 2101",
                "AMBROSIA THORNH 42.40 100.00",
                "4 Mar Contactless Interac purchase - 2102",
                "AMBROSIA RESTAURANT NEW YORK NY 28.80 71.20",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("ambrosia-accuracy.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]

        self.assertEqual([row["category"] for row in preview_rows], ["groceries", "restaurant"])
        self.assertEqual(preview_rows[0]["category_source"], "merchant_override")
        self.assertEqual(preview_rows[1]["category_source"], "rule")

    def test_import_file_recognizes_education_testing_merchants(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 2301",
                "IDP EDUCATION LIMITED TORONTO ON 359.00 100.00",
                "4 Mar Contactless Interac purchase - 2302",
                "BRITISH COUNCIL IELTS TORONTO ON 65.00 35.00",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("education-testing.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]

        self.assertEqual([row["category"] for row in preview_rows], ["education", "education"])
        self.assertEqual(preview_rows[0]["category_source"], "merchant_override")
        self.assertEqual(preview_rows[1]["category_source"], "merchant_override")

    def test_category_suggest_route_uses_backend_learning_engine(self) -> None:
        response = self.client.post(
            "/transactions/categorize/suggest",
            json={
                "description": "IDP EDUCATION LIMITED TORONTO ON",
                "type": "expense",
                "amount": 359.00,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["suggested_category"], "education")
        self.assertGreaterEqual(payload["confidence"], 0.9)
        self.assertEqual(payload["matched_keyword"], "idp education limited")

    def test_single_letter_categories_are_rejected_before_they_train_memory(self) -> None:
        create_response = self.client.post(
            "/transactions/",
            json={
                "amount": 20.00,
                "category": "S",
                "description": "OPENAI",
                "date": "2026-03-16",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(create_response.status_code, 400, create_response.text)

        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": [
                    {
                        "date": "2026-03-16",
                        "description": "OPENAI",
                        "amount": 20.00,
                        "type": "expense",
                        "category": "S",
                        "confidence": 0.94,
                        "category_confidence": 0.90,
                        "category_review_required": False,
                    }
                ],
            },
        )
        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        self.assertEqual(confirm_response.json()["imported"], 0)
        self.assertEqual(confirm_response.json()["invalid_rows_skipped"], 1)

        with self.session_local() as session:
            self.assertEqual(session.query(Transaction).filter(Transaction.description == "OPENAI").count(), 0)
            self.assertEqual(session.query(CategoryMemory).filter(CategoryMemory.category == "s").count(), 0)

    def test_import_file_uses_north_america_merchant_taxonomy(self) -> None:
        pdf_bytes = build_text_pdf(
            [
                "Royal Bank of Canada",
                "Details of your account activity",
                "From March 2, 2026 to April 2, 2026",
                "Date Description Withdrawals ($) Deposits ($) Balance ($)",
                "3 Mar Contactless Interac purchase - 3001",
                "PUBLIX #221 MIAMI FL 42.50 200.00",
                "4 Mar Contactless Interac purchase - 3002",
                "WALGREENS 1234 NEW YORK NY 16.20 183.80",
                "5 Mar Contactless Interac purchase - 3003",
                "SHEETZ FUEL PITTSBURGH PA 51.12 132.68",
                "6 Mar Contactless Interac purchase - 3004",
                "TOKYO SMOKE TORONTO ON 19.99 112.69",
                "7 Mar Contactless Interac purchase - 3005",
                "SAQ MONTREAL QC 28.40 84.29",
                "8 Mar Contactless Interac purchase - 3006",
                "PARAMOUNT PLUS CA 11.29 73.00",
                "9 Mar Contactless Interac purchase - 3007",
                "IN-N-OUT BURGER LOS ANGELES CA 13.45 59.55",
                "10 Mar Preauthorized Payment",
                "HYDRO QUEBEC MONTREAL QC 66.20 6.65",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("north-america-taxonomy.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_rows = response.json()["preview_rows"]

        self.assertEqual(
            [row["category"] for row in preview_rows],
            [
                "groceries",
                "health",
                "gas",
                "smoking",
                "alcohol",
                "subscriptions",
                "restaurant",
                "utilities",
            ],
        )
        self.assertTrue(all(row["category_source"] == "rule" for row in preview_rows))

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

    def test_batch_statement_import_accepts_more_than_six_files(self) -> None:
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

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "table_review")
        self.assertEqual(len(payload["preview_rows"]), 7)

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
        reviewed_rows = [
            {
                **row,
                "category_review_required": False,
                "category_review_reason": None,
                "category_source": row.get("category_source") or "user_review",
            }
            for row in preview_payload["preview_rows"]
        ]

        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": reviewed_rows,
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

    def test_confirm_preview_import_repairs_header_polluted_expense_category(self) -> None:
        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": [
                    {
                        "date": "2026-03-26",
                        "description": (
                            "From March 2, 2026 to April 2, 2026 Date DescriptionWithdrawals ($) "
                            "Deposits ($) Balance ($) Contactless Interac purchase - 2653 ORANGE MART"
                        ),
                        "amount": 10.99,
                        "type": "expense",
                        "category": "income",
                    }
                ],
            },
        )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        self.assertEqual(confirm_response.json()["imported"], 1)

        with self.session_local() as session:
            transaction = (
                session.query(Transaction)
                .filter(Transaction.owner_id == self.user_id)
                .one()
            )

        self.assertEqual(transaction.description, "ORANGE MART")
        self.assertEqual(transaction.type, "expense")
        self.assertEqual(transaction.category, "groceries")

    def test_confirm_preview_import_skips_unreviewed_low_confidence_category_rows(self) -> None:
        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": [
                    {
                        "date": "2025-01-03",
                        "description": "PAYPAL UNKNOWN MERCHANT",
                        "amount": 22.15,
                        "type": "expense",
                        "category": "transfer",
                        "category_confidence": 0.58,
                        "category_source": "payment_processor",
                        "category_review_required": True,
                        "category_review_reason": "Review this generic processor row before importing.",
                    }
                ],
            },
        )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        payload = confirm_response.json()
        self.assertEqual(payload["imported"], 0)
        self.assertEqual(payload["invalid_rows_skipped"], 1)

        with self.session_local() as session:
            transaction_count = (
                session.query(Transaction)
                .filter(Transaction.owner_id == self.user_id)
                .count()
            )

        self.assertEqual(transaction_count, 0)

    def test_confirm_preview_import_allows_approved_category_review_rows(self) -> None:
        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": [
                    {
                        "date": "2025-01-03",
                        "description": "PAYPAL BAGEL NASH",
                        "amount": 22.15,
                        "type": "expense",
                        "category": "restaurant",
                        "category_confidence": 0.9,
                        "category_source": "user_review",
                        "category_review_required": False,
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
                    Transaction.description == "BAGEL NASH",
                )
                .one_or_none()
            )

        self.assertIsNotNone(imported_transaction)
        self.assertEqual(imported_transaction.category, "restaurant")

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

    def test_statement_reconciliation_likely_matches_nearby_manual_transaction(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=26.4,
                    category="restaurant",
                    description="Dinner with friend",
                    date=date(2025, 1, 4),
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
                "06 Jan THAI ISLAND RES $26.40",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("posted-date-check.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_row = response.json()["preview_rows"][0]
        self.assertTrue(preview_row["is_duplicate"])
        self.assertEqual(preview_row["reconciliation_status"], "matched")
        self.assertIn("Likely already written as Dinner with friend", preview_row["duplicate_reason"])
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

    def test_confirm_preview_import_skips_likely_nearby_match_even_without_preview_flag(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=68.15,
                    category="groceries",
                    description="Weekend groceries",
                    date=date(2025, 1, 10),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.account_id,
                )
            )
            session.commit()

        confirm_response = self.client.post(
            "/transactions/import/confirm-preview",
            json={
                "account_id": self.account_id,
                "rows": [
                    {
                        "date": "2025-01-12",
                        "description": "FOOD BASICS",
                        "amount": 68.15,
                        "type": "expense",
                        "category": "groceries",
                    }
                ],
            },
        )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.text)
        self.assertEqual(confirm_response.json()["imported"], 0)
        self.assertEqual(confirm_response.json()["duplicates_skipped"], 1)

        with self.session_local() as session:
            transaction_count = (
                session.query(Transaction)
                .filter(Transaction.owner_id == self.user_id)
                .count()
            )

        self.assertEqual(transaction_count, 1)

    def test_statement_reconciliation_does_not_likely_match_ambiguous_nearby_amounts(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=9.99,
                        category="cafe",
                        description="Morning coffee",
                        date=date(2025, 1, 4),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=9.99,
                        category="cafe",
                        description="Afternoon coffee",
                        date=date(2025, 1, 5),
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
                "From January 1, 2025 to January 31, 2025",
                "06 Jan COFFEE SHOP $9.99",
            ]
        )

        response = self.client.post(
            "/transactions/import/file",
            data={"account_id": str(self.account_id)},
            files={"file": ("ambiguous-nearby-match.pdf", pdf_bytes, "application/pdf")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview_row = response.json()["preview_rows"][0]
        self.assertFalse(preview_row["is_duplicate"])
        self.assertEqual(preview_row["reconciliation_status"], "missing")
        self.assertIsNone(preview_row["matched_transaction_id"])

    def test_statement_preview_keeps_repeating_pattern_fields_optional(self) -> None:
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

        self.assertIn("is_repeating_pattern", payroll_row)
        self.assertFalse(payroll_row["is_repeating_pattern"])

        self.assertIn("is_repeating_pattern", gym_row)
        self.assertFalse(gym_row["is_repeating_pattern"])

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
            patch.object(pdf_statement_service, "is_local_ocr_enabled", return_value=False),
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
                    "No page images could be extracted or rendered for OCR fallback. Make sure PyMuPDF "
                    "is installed so screenshot-style PDFs can be rendered before OCR."
                )
            },
        )

    def test_import_file_uses_local_ocr_fallback_for_scanned_pdf(self) -> None:
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
            patch.object(pdf_statement_service, "is_local_ocr_enabled", return_value=True),
            patch.object(
                pdf_statement_service,
                "ocr_pdf_page_images_with_local_tesseract",
                return_value=pdf_statement_service.PdfOcrFallbackResult(
                    text=(
                        "Account Statement\n"
                        "Statement period 12/28/2024 - 01/10/2025\n"
                        "Jan 02 PAYROLL DEPOSIT $1,500.00"
                    ),
                    notes=(
                        "Used free local Tesseract OCR on 1 scanned PDF page. Review extracted rows carefully.",
                    ),
                    candidate_pages=1,
                    processed_pages=1,
                ),
            ),
            patch.object(pdf_statement_service, "is_vision_ocr_enabled", return_value=False),
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
                "Used free local Tesseract OCR on 1 scanned PDF page. Review extracted rows carefully.",
            ],
        )

    def test_import_file_uses_openai_ocr_fallback_for_scanned_pdf(self) -> None:
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
            patch.object(pdf_statement_service, "is_local_ocr_enabled", return_value=False),
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

    def test_bulk_apply_records_learning_event_for_accepted_suggestion(self) -> None:
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

        apply_response = self.client.post(
            "/transactions/categorize/bulk-apply",
            json={"transaction_ids": [suggestions[0]["transaction_id"]]},
        )
        self.assertEqual(apply_response.status_code, 200, apply_response.text)
        self.assertEqual(apply_response.json()["updated_count"], 1)

        with self.session_local() as session:
            updated_transaction = session.get(Transaction, suggestions[0]["transaction_id"])
            learning_event = (
                session.query(CategoryLearningEvent)
                .filter(
                    CategoryLearningEvent.owner_id == self.user_id,
                    CategoryLearningEvent.merchant_key == "chipotle",
                    CategoryLearningEvent.signal_source == "bulk_apply",
                )
                .one_or_none()
            )

        self.assertEqual(updated_transaction.category, "restaurant")
        self.assertIsNotNone(learning_event)
        self.assertEqual(learning_event.category, "restaurant")

    def test_learning_candidates_group_similar_merchants_for_user_review(self) -> None:
        for amount in (8.90, 12.60, 10.25):
            response = self.client.post(
                "/transactions/",
                json={
                    "amount": amount,
                    "category": "other",
                    "description": "SQDC77068 MTL",
                    "date": "2026-03-16",
                    "type": "expense",
                    "account_id": self.account_id,
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

        preview_response = self.client.get(
            "/transactions/categorize/learning-candidates",
            params={"account_id": self.account_id},
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        payload = preview_response.json()
        self.assertEqual(payload["total_candidates"], 1)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["merchant_key"], "sqdc")
        self.assertEqual(candidate["transaction_count"], 3)
        self.assertEqual(candidate["current_category"], "other")
        self.assertTrue(candidate["review_required"])

    def test_learning_apply_updates_similar_transactions_and_memory(self) -> None:
        for amount in (8.90, 12.60, 10.25):
            response = self.client.post(
                "/transactions/",
                json={
                    "amount": amount,
                    "category": "other",
                    "description": "SQDC77068 MTL",
                    "date": "2026-03-16",
                    "type": "expense",
                    "account_id": self.account_id,
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

        apply_response = self.client.post(
            "/transactions/categorize/learning-apply",
            json={
                "merchant_key": "sqdc",
                "type": "expense",
                "category": "smoking",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(apply_response.status_code, 200, apply_response.text)
        payload = apply_response.json()
        self.assertEqual(payload["matched_count"], 3)
        self.assertEqual(payload["updated_count"], 3)

        with self.session_local() as session:
            transactions = (
                session.query(Transaction)
                .filter(Transaction.owner_id == self.user_id, Transaction.description == "SQDC77068 MTL")
                .all()
            )
            profile = (
                session.query(MerchantCategoryProfile)
                .filter(
                    MerchantCategoryProfile.owner_id == self.user_id,
                    MerchantCategoryProfile.merchant_key == "sqdc",
                    MerchantCategoryProfile.transaction_type == "expense",
                )
                .one_or_none()
            )

        self.assertTrue(transactions)
        self.assertTrue(all(transaction.category == "smoking" for transaction in transactions))
        self.assertIsNotNone(profile)
        self.assertEqual(profile.category, "smoking")

    def test_learning_summary_reports_category_memory_health(self) -> None:
        categorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 8.90,
                "category": "smoking",
                "description": "SQDC77068 MTL",
                "date": "2026-03-16",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(categorized_response.status_code, 200, categorized_response.text)

        uncategorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 12.60,
                "category": "other",
                "description": "SQDC77068 MTL",
                "date": "2026-03-17",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(uncategorized_response.status_code, 200, uncategorized_response.text)

        summary_response = self.client.get(
            "/transactions/categorize/learning-summary",
            params={"account_id": self.account_id},
        )

        self.assertEqual(summary_response.status_code, 200, summary_response.text)
        payload = summary_response.json()
        self.assertEqual(payload["transaction_count"], 2)
        self.assertEqual(payload["uncategorized_count"], 1)
        self.assertEqual(payload["learning_candidate_count"], 1)
        self.assertGreaterEqual(payload["personal_memory_count"], 1)
        self.assertGreaterEqual(payload["merchant_profile_count"], 1)
        self.assertEqual(payload["learning_event_count"], 1)
        self.assertEqual(len(payload["recent_learning_events"]), 1)
        self.assertEqual(payload["recent_learning_events"][0]["merchant_key"], "sqdc")
        self.assertEqual(payload["recent_learning_events"][0]["signal_source"], "manual_create")
        self.assertTrue(payload["community_learning_enabled"])
        self.assertIn(payload["confidence_level"], {"low", "medium", "high"})

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
                        "category_source": "user_review",
                        "category_confidence": 0.96,
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

        with self.session_local() as session:
            learning_event = (
                session.query(CategoryLearningEvent)
                .filter(CategoryLearningEvent.owner_id == self.user_id)
                .one_or_none()
            )

        self.assertIsNotNone(learning_event)
        self.assertEqual(learning_event.merchant_key, "sephora")
        self.assertEqual(learning_event.signal_source, "import_review")

    def test_confirmed_learning_events_feed_future_category_suggestions(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CategoryLearningEvent(
                        merchant_key="mooncrate",
                        display_name="Mooncrate",
                        category="hobby",
                        transaction_type="expense",
                        signal_source="learning_apply",
                        confidence=0.95,
                        affected_count=1,
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    CategoryLearningEvent(
                        merchant_key="mooncrate",
                        display_name="Mooncrate",
                        category="hobby",
                        transaction_type="expense",
                        signal_source="manual_edit",
                        confidence=0.95,
                        affected_count=1,
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=24.50,
                        category="other",
                        description="Mooncrate Shop",
                        date=date(2025, 1, 7),
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
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["suggested_category"], "hobby")
        self.assertEqual(suggestions[0]["matched_keyword"], "mooncrate")
        self.assertIn("confirmed category learning history", suggestions[0]["reason"].lower())

    def test_single_learning_event_does_not_override_known_rules(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CategoryLearningEvent(
                        merchant_key="starbucks",
                        display_name="Starbucks",
                        category="rent",
                        transaction_type="expense",
                        signal_source="manual_edit",
                        confidence=1.0,
                        affected_count=1,
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
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["suggested_category"], "cafe")
        self.assertEqual(suggestions[0]["matched_keyword"], "starbucks")

    def test_learning_events_respect_amount_sensitive_merchants(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CategoryLearningEvent(
                        merchant_key="orange mart",
                        display_name="Orange Mart",
                        category="smoking",
                        transaction_type="expense",
                        signal_source="learning_apply",
                        confidence=0.95,
                        affected_count=2,
                        amount_bucket="10",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=12.60,
                        category="other",
                        description="Orange Mart",
                        date=date(2025, 1, 4),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=35.00,
                        category="other",
                        description="Orange Mart",
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
        suggestions = {
            suggestion["transaction_id"]: suggestion
            for suggestion in preview_response.json()["suggestions"]
        }

        smoking_suggestion = next(
            suggestion
            for suggestion in suggestions.values()
            if suggestion["description"] == "Orange Mart"
            and suggestion["suggested_category"] == "smoking"
        )
        grocery_suggestion = next(
            suggestion
            for suggestion in suggestions.values()
            if suggestion["description"] == "Orange Mart"
            and suggestion["suggested_category"] == "groceries"
        )

        self.assertIn("confirmed category learning history", smoking_suggestion["reason"].lower())
        self.assertEqual(grocery_suggestion["matched_keyword"], "orange mart")

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

    def test_amount_sensitive_merchant_learning_respects_amount_context(self) -> None:
        categorized_response = self.client.post(
            "/transactions/",
            json={
                "amount": 10.99,
                "category": "smoking",
                "description": "Orange Mart Cigarettes",
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
                        amount=12.60,
                        category="other",
                        description="Orange Mart",
                        date=date(2025, 1, 4),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=35.00,
                        category="other",
                        description="Orange Mart",
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
        suggestions = {
            (suggestion["description"], suggestion["transaction_id"]): suggestion
            for suggestion in preview_response.json()["suggestions"]
        }

        small_amount_suggestion = next(
            suggestion
            for suggestion in suggestions.values()
            if suggestion["description"] == "Orange Mart"
            and suggestion["suggested_category"] == "smoking"
        )
        large_amount_suggestion = next(
            suggestion
            for suggestion in suggestions.values()
            if suggestion["description"] == "Orange Mart"
            and suggestion["suggested_category"] == "groceries"
        )

        self.assertIn("learned merchant profile", small_amount_suggestion["reason"].lower())
        self.assertEqual(large_amount_suggestion["suggested_category"], "groceries")

    def test_generic_statement_words_do_not_train_or_match_category_memory(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CategoryMemory(
                        keyword="time",
                        category="rent",
                        transaction_type="expense",
                        owner_id=self.user_id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="time",
                        display_name="Time",
                        category="rent",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        last_amount=20.99,
                        owner_id=self.user_id,
                    ),
                    Transaction(
                        amount=20.99,
                        category="other",
                        description="Time",
                        date=date(2026, 4, 25),
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
        self.assertEqual(preview_response.json()["suggestions"], [])

        create_response = self.client.post(
            "/transactions/",
            json={
                "amount": 21.50,
                "category": "rent",
                "description": "Time",
                "date": "2026-04-26",
                "type": "expense",
                "account_id": self.account_id,
            },
        )
        self.assertEqual(create_response.status_code, 200, create_response.text)

        with self.session_local() as session:
            time_profiles = (
                session.query(MerchantCategoryProfile)
                .filter(
                    MerchantCategoryProfile.owner_id == self.user_id,
                    MerchantCategoryProfile.merchant_key == "time",
                )
                .all()
            )
            time_memories = (
                session.query(CategoryMemory)
                .filter(
                    CategoryMemory.owner_id == self.user_id,
                    CategoryMemory.keyword == "time",
                )
                .all()
            )

        self.assertEqual(len(time_profiles), 1)
        self.assertEqual(len(time_memories), 1)

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
        self.assertEqual(payload["updated_count"], 2)
        self.assertGreaterEqual(payload["memory_entries_created"], 1)

        with self.session_local() as session:
            categories = {
                transaction.description: transaction.category
                for transaction in session.query(Transaction)
                .filter(Transaction.description.like("Aesop%"))
                .all()
            }

        self.assertEqual(categories["Aesop Queen"], "personal")
        self.assertEqual(categories["Aesop King"], "personal")

    def test_normalize_categories_route_repairs_accidental_single_letter_categories(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=20.00,
                        category="S",
                        description="OPENAI",
                        date=date(2026, 3, 16),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.account_id,
                    ),
                    Transaction(
                        amount=359.00,
                        category="E",
                        description="IDP EDUCATION LIMITED TORONTO ON",
                        date=date(2026, 3, 17),
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
        self.assertEqual(payload["updated_count"], 2)

        with self.session_local() as session:
            categories = {
                transaction.description: transaction.category
                for transaction in session.query(Transaction)
                .filter(Transaction.description.in_(["OPENAI", "IDP EDUCATION LIMITED TORONTO ON"]))
                .all()
            }
            short_category_memories = (
                session.query(CategoryMemory)
                .filter(CategoryMemory.owner_id == self.user_id, CategoryMemory.category.in_(["s", "e"]))
                .count()
            )

        self.assertEqual(categories["OPENAI"], "subscriptions")
        self.assertEqual(categories["IDP EDUCATION LIMITED TORONTO ON"], "education")
        self.assertEqual(short_category_memories, 0)

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
