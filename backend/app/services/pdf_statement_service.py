from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.schemas import StatementPreviewRow
from app.services.transaction_service import categorize_transaction


DATE_REGEX = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4}|\d{2}/\d{2}/\d{2})"
)
AMOUNT_REGEX = re.compile(r"(?P<amount>\(?-?\$?\d[\d,]*\.\d{2}\)?)$")


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts: list[str] = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            text_parts.append(page_text)

    return "\n".join(text_parts).strip()


def normalize_date(value: str) -> str | None:
    value = value.strip()
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%m/%d/%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def parse_amount(value: str) -> float | None:
    try:
        cleaned = value.replace("$", "").replace(",", "").strip()
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = f"-{cleaned[1:-1]}"
        return abs(float(cleaned))
    except Exception:
        return None


def infer_type_from_line(line: str, amount_text: str) -> str:
    lowered = line.lower()

    income_markers = [
        "deposit",
        "payroll",
        "salary",
        "refund",
        "interest",
        "credit",
        "payment received",
    ]

    if any(marker in lowered for marker in income_markers):
        return "income"

    if amount_text.strip().startswith("-") or "(" in amount_text:
        return "expense"

    return "expense"


def parse_pdf_statement_preview(
    db: Session,
    owner_id: int,
    file_bytes: bytes,
) -> dict[str, Any]:
    text = extract_pdf_text(file_bytes)

    if not text:
        raise ValueError("No readable text was found in this PDF statement.")

    preview_rows: list[StatementPreviewRow] = []
    notes: list[str] = []

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        date_match = DATE_REGEX.search(line)
        amount_match = AMOUNT_REGEX.search(line)

        if not date_match or not amount_match:
            continue

        raw_date = date_match.group("date")
        normalized_date = normalize_date(raw_date)
        if not normalized_date:
            continue

        raw_amount = amount_match.group("amount")
        amount = parse_amount(raw_amount)
        if amount is None:
            continue

        description = line
        description = description.replace(raw_date, "", 1).strip()
        if description.endswith(raw_amount):
            description = description[: -len(raw_amount)].strip()

        description = re.sub(r"\s+", " ", description).strip(" -|")
        if not description:
            description = "Imported statement transaction"

        tx_type = infer_type_from_line(line, raw_amount)
        category = categorize_transaction(
            db=db,
            owner_id=owner_id,
            description=description,
            tx_type=tx_type,
        )

        preview_rows.append(
            StatementPreviewRow(
                date=normalized_date,
                description=description,
                amount=amount,
                type=tx_type,
                category=category,
                source_line=line[:300],
            )
        )

    if not preview_rows:
        raise ValueError(
            "No transaction rows could be extracted from this PDF. Try a more text-based statement PDF."
        )

    if len(preview_rows) > 100:
        preview_rows = preview_rows[:100]
        notes.append("Preview limited to the first 100 detected rows.")

    return {
        "preview_rows": preview_rows,
        "notes": notes,
    }