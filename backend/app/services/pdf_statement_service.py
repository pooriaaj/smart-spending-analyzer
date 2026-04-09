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
TRAILING_AMOUNT_TOKEN_REGEX = re.compile(r"\(?-?\$?\d[\d,]*\.\d{2}\)?$")
STATEMENT_RANGE_REGEX = re.compile(
    r"From\s+(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2}),\s+(?P<y1>\d{4})\s+to\s+"
    r"(?P<m2>[A-Za-z]+)\s+(?P<d2>\d{1,2}),\s+(?P<y2>\d{4})",
    flags=re.IGNORECASE,
)
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
    match = STATEMENT_RANGE_REGEX.search(text)
    if match:
        return int(match.group("y2"))

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        return int(year_match.group(1))

    return datetime.utcnow().year


def extract_statement_year_range(text: str) -> tuple[int | None, int | None]:
    match = STATEMENT_RANGE_REGEX.search(text)
    if not match:
        return None, None
    return int(match.group("y1")), int(match.group("y2"))


def normalize_statement_date(day: str, mon: str, year: int) -> date | None:
    month_num = MONTH_MAP.get(mon.strip().lower())
    if not month_num:
        return None

    try:
        return date(year, month_num, int(day))
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
        "income tax refund",
        "direct deposit",
    ]

    return any(marker in lowered for marker in income_markers)


def is_expense_description(description: str) -> bool:
    lowered = description.lower()
    expense_markers = [
        "purchase",
        "pos",
        "debit",
        "bill payment",
        "withdrawal",
        "fee",
        "service charge",
        "pre-authorized",
        "subscription",
        "payment sent",
        "e-transfer sent",
    ]
    return any(marker in lowered for marker in expense_markers)


def looks_like_balance_only_line(line: str) -> bool:
    lowered = line.lower()
    balance_markers = [
        "opening balance",
        "closing balance",
        "balance brought forward",
        "balance carried forward",
        "daily closing balance",
    ]
    return any(marker in lowered for marker in balance_markers)


def parse_amount_token(value: str) -> float | None:
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None

    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"

    try:
        return float(cleaned)
    except ValueError:
        return None


def split_line_and_trailing_amounts(line: str) -> tuple[str, list[str]]:
    tokens = line.split()
    trailing_amounts_reversed: list[str] = []

    for token in reversed(tokens):
        if TRAILING_AMOUNT_TOKEN_REGEX.fullmatch(token):
            trailing_amounts_reversed.append(token)
        else:
            break

    trailing_amounts = list(reversed(trailing_amounts_reversed))
    body_token_count = len(tokens) - len(trailing_amounts)
    body = " ".join(tokens[:body_token_count]).strip()
    return body, trailing_amounts


def infer_transaction_type(description: str) -> str:
    if is_income_description(description):
        return "income"
    if is_expense_description(description):
        return "expense"
    return "expense"


def resolve_statement_year_for_month(
    month_num: int,
    start_year: int | None,
    end_year: int | None,
) -> int:
    if start_year is None or end_year is None:
        return end_year or start_year or datetime.utcnow().year

    if start_year == end_year:
        return end_year

    # Cross-year statements are typically Dec->Jan. Use month bucket to reduce
    # January transactions being assigned to the prior year.
    if month_num >= 10:
        return start_year
    return end_year


def finalize_pending_transaction(
    db: Session,
    owner_id: int,
    current_date: date | None,
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

    amount = parse_amount_token(amount_text_1)
    if amount is None:
        return

    tx_type = infer_transaction_type(description)
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
            date=current_date.isoformat(),
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
    statement_start_year, statement_end_year = extract_statement_year_range(text)
    fallback_year = extract_statement_year(text)
    lines = [line.rstrip() for line in text.splitlines()]

    preview_rows: list[StatementPreviewRow] = []
    notes: list[str] = []

    current_date: date | None = None
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
            month_num = MONTH_MAP.get(mon.strip().lower())
            if not month_num:
                continue
            resolved_year = resolve_statement_year_for_month(
                month_num=month_num,
                start_year=statement_start_year,
                end_year=statement_end_year,
            )
            normalized_date = normalize_statement_date(day, mon, resolved_year or fallback_year)

            if normalized_date:
                current_date = normalized_date
                line = rest
            else:
                continue

        if not current_date:
            continue

        body, trailing_amounts = split_line_and_trailing_amounts(line)
        if trailing_amounts:
            amount_1 = trailing_amounts[0]
            amount_2 = trailing_amounts[1] if len(trailing_amounts) > 1 else None
            body = clean_description_line(body)

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
    statement_start_year, statement_end_year = extract_statement_year_range(text)
    fallback_year = extract_statement_year(text)
    current_date: date | None = None
    description_parts: list[str] = []

    for line in lines:
        if is_noise_line(line) or looks_like_balance_only_line(line):
            continue

        date_match = DATE_START_REGEX.match(line)
        if date_match:
            if description_parts:
                description_parts = []

            month_num = MONTH_MAP.get(date_match.group("mon").strip().lower())
            if not month_num:
                continue
            resolved_year = resolve_statement_year_for_month(
                month_num=month_num,
                start_year=statement_start_year,
                end_year=statement_end_year,
            )
            current_date = normalize_statement_date(
                date_match.group("day"),
                date_match.group("mon"),
                resolved_year or fallback_year,
            )
            line = date_match.group("rest").strip()

        if not current_date:
            continue

        body, trailing_amounts = split_line_and_trailing_amounts(line)
        if trailing_amounts:
            amount_1 = trailing_amounts[0]
            amount_2 = trailing_amounts[1] if len(trailing_amounts) > 1 else None
            body = clean_description_line(body)

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
