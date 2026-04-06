from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.schemas import StatementPreviewRow
from app.services.transaction_service import categorize_transaction


DATE_START_REGEX = re.compile(r"^(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+(?P<rest>.*)$")
ENDING_AMOUNTS_REGEX = re.compile(r"(?P<body>.*?)(?P<a1>\d+\.\d{2})(?:\s+(?P<a2>\d+\.\d{2}))?$")
MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts: list[str] = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            text_parts.append(page_text)

    return "\n".join(text_parts).strip()


def extract_statement_year(text: str) -> int:
    match = re.search(
        r"From\s+[A-Za-z]+\s+\d{1,2},\s+(?P<y1>\d{4})\s+to\s+[A-Za-z]+\s+\d{1,2},\s+(?P<y2>\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return int(match.group("y2"))

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        return int(year_match.group(1))

    return datetime.utcnow().year


def normalize_statement_date(day: str, mon: str, year: int) -> str | None:
    month_num = MONTH_MAP.get(mon.strip().lower())
    if not month_num:
        return None

    try:
        return date(year, month_num, int(day)).isoformat()
    except ValueError:
        return None


def clean_description_line(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    value = value.strip(" -|")
    return value


def is_noise_line(line: str) -> bool:
    lowered = line.lower().strip()

    if not lowered:
        return True

    noise_prefixes = [
        "your rbc personal banking account statement",
        "details of your account activity",
        "important information about your account",
        "summary of your account for this period",
        "date description withdrawals",
        "opening balance",
        "closing balance",
        "royal bank of canada",
        "p.o. box",
        "how to reach us",
        "your account number",
        "protect your pin",
        "here are four ways",
        "stay informed",
        "please check this account statement",
    ]

    if any(lowered.startswith(prefix) for prefix in noise_prefixes):
        return True

    if re.fullmatch(r"\d+\s+of\s+\d+", lowered):
        return True

    if re.fullmatch(r"[A-Z0-9_\-\*\/ ]{8,}", line.strip()):
        return True

    if "gst registration number" in lowered:
        return True

    return False


def is_income_description(description: str) -> bool:
    lowered = description.lower()

    income_markers = [
        "e-transfer received",
        "received",
        "atm deposit",
        "deposit",
        "salary",
        "payroll",
        "refund",
        "interest",
    ]

    return any(marker in lowered for marker in income_markers)


def looks_like_balance_only_line(line: str) -> bool:
    lowered = line.lower()
    return "opening balance" in lowered or "closing balance" in lowered


def finalize_pending_transaction(
    db: Session,
    owner_id: int,
    current_date: str | None,
    description_parts: list[str],
    amount_text_1: str | None,
    amount_text_2: str | None,
    preview_rows: list[StatementPreviewRow],
) -> None:
    if not current_date or not description_parts or not amount_text_1:
        return

    description = clean_description_line(" ".join(part for part in description_parts if part))
    if not description:
        return

    try:
        amount = float(amount_text_1)
    except ValueError:
        return

    tx_type = "income" if is_income_description(description) else "expense"
    category = categorize_transaction(
        db=db,
        owner_id=owner_id,
        description=description,
        tx_type=tx_type,
    )

    source_line = description
    if amount_text_2:
        source_line = f"{description} | amount={amount_text_1} | balance={amount_text_2}"
    else:
        source_line = f"{description} | amount={amount_text_1}"

    preview_rows.append(
        StatementPreviewRow(
            date=current_date,
            description=description,
            amount=abs(amount),
            type=tx_type,
            category=category,
            source_line=source_line[:300],
        )
    )


def parse_rbc_statement_preview(
    db: Session,
    owner_id: int,
    text: str,
) -> dict[str, Any]:
    year = extract_statement_year(text)
    lines = [line.rstrip() for line in text.splitlines()]

    preview_rows: list[StatementPreviewRow] = []
    notes: list[str] = []

    current_date: str | None = None
    description_parts: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if is_noise_line(line):
            continue

        if looks_like_balance_only_line(line):
            continue

        date_match = DATE_START_REGEX.match(line)
        if date_match:
            # If a new dated row starts while a previous row was incomplete, discard the incomplete one.
            if description_parts:
                description_parts = []

            day = date_match.group("day")
            mon = date_match.group("mon")
            rest = date_match.group("rest").strip()
            normalized_date = normalize_statement_date(day, mon, year)

            if normalized_date:
                current_date = normalized_date
                line = rest
            else:
                continue

        if not current_date:
            continue

        amount_match = ENDING_AMOUNTS_REGEX.match(line)
        if amount_match:
            body = clean_description_line(amount_match.group("body"))
            amount_1 = amount_match.group("a1")
            amount_2 = amount_match.group("a2")

            if body:
                description_parts.append(body)

            finalize_pending_transaction(
                db=db,
                owner_id=owner_id,
                current_date=current_date,
                description_parts=description_parts,
                amount_text_1=amount_1,
                amount_text_2=amount_2,
                preview_rows=preview_rows,
            )

            description_parts = []
            continue

        cleaned = clean_description_line(line)
        if cleaned:
            description_parts.append(cleaned)

    if not preview_rows:
        raise ValueError(
            "No transaction rows could be extracted from this PDF. Try a more text-based statement PDF."
        )

    return {
        "preview_rows": preview_rows[:200],
        "notes": notes,
    }


def parse_pdf_statement_preview(
    db: Session,
    owner_id: int,
    file_bytes: bytes,
) -> dict[str, Any]:
    text = extract_pdf_text(file_bytes)

    if not text:
        raise ValueError("No readable text was found in this PDF statement.")

    lowered = text.lower()

    if "royal bank of canada" in lowered and "details of your account activity" in lowered:
        return parse_rbc_statement_preview(
            db=db,
            owner_id=owner_id,
            text=text,
        )

    # Fallback generic parser
    preview_rows: list[StatementPreviewRow] = []
    notes = ["Used generic PDF parser. Accuracy may vary for this bank format."]

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    current_year = extract_statement_year(text)
    current_date: str | None = None
    description_parts: list[str] = []

    for line in lines:
        if is_noise_line(line) or looks_like_balance_only_line(line):
            continue

        date_match = DATE_START_REGEX.match(line)
        if date_match:
            if description_parts:
                description_parts = []

            current_date = normalize_statement_date(
                date_match.group("day"),
                date_match.group("mon"),
                current_year,
            )
            line = date_match.group("rest").strip()

        if not current_date:
            continue

        amount_match = ENDING_AMOUNTS_REGEX.match(line)
        if amount_match:
            body = clean_description_line(amount_match.group("body"))
            amount_1 = amount_match.group("a1")
            amount_2 = amount_match.group("a2")

            if body:
                description_parts.append(body)

            finalize_pending_transaction(
                db=db,
                owner_id=owner_id,
                current_date=current_date,
                description_parts=description_parts,
                amount_text_1=amount_1,
                amount_text_2=amount_2,
                preview_rows=preview_rows,
            )

            description_parts = []
            continue

        cleaned = clean_description_line(line)
        if cleaned:
            description_parts.append(cleaned)

    if not preview_rows:
        raise ValueError(
            "No transaction rows could be extracted from this PDF. Try a more text-based statement PDF."
        )

    return {
        "preview_rows": preview_rows[:200],
        "notes": notes,
    }