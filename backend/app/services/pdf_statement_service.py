from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.schemas import StatementPreviewRow
from app.services.transaction_service import categorize_transaction


DAY_MONTH_DATE_START_REGEX = re.compile(
    r"^(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3,9})(?:,\s*|\s+)?(?:(?P<year>\d{2,4})\s+)?(?P<rest>.*)$"
)
MONTH_DAY_DATE_START_REGEX = re.compile(
    r"^(?P<mon>[A-Za-z]{3,9})\s+(?P<day>\d{1,2})(?:,\s*|\s+)?(?:(?P<year>\d{2,4})\s+)?(?P<rest>.*)$"
)
NUMERIC_DATE_START_REGEX = re.compile(
    r"^(?P<n1>\d{1,2})[/-](?P<n2>\d{1,2})(?:[/-](?P<year>\d{2,4}))?\s+(?P<rest>.*)$"
)
TRAILING_AMOUNT_TOKEN_REGEX = re.compile(
    r"(?i)(?:\(?[+-]?\$?\d[\d,]*\.\d{2}\)?(?:cr|dr)?|\$?\d[\d,]*\.\d{2}-)$"
)
WORD_STATEMENT_RANGE_REGEX = re.compile(
    r"From\s+(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2}),\s+(?P<y1>\d{4})\s+to\s+"
    r"(?P<m2>[A-Za-z]+)\s+(?P<d2>\d{1,2}),\s+(?P<y2>\d{4})",
    flags=re.IGNORECASE,
)
NUMERIC_STATEMENT_RANGE_REGEX = re.compile(
    r"(?:(?:statement\s+period|period|from)\s*:?\s*)?"
    r"(?P<start>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|-)\s*"
    r"(?P<end>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    flags=re.IGNORECASE,
)
MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
GENERIC_NOISE_PREFIXES = (
    "important information about your account",
    "summary of your account for this period",
    "opening balance",
    "closing balance",
    "p.o. box",
    "how to reach us",
    "your account number",
    "protect your pin",
    "here are four ways",
    "stay informed",
    "please check this account statement",
)
GENERIC_BALANCE_MARKERS = (
    "opening balance",
    "closing balance",
    "balance brought forward",
    "balance carried forward",
    "daily closing balance",
)
HEADER_ONLY_WORDS = {
    "account",
    "activity",
    "amount",
    "balance",
    "balances",
    "cheque",
    "cheques",
    "check",
    "checks",
    "credit",
    "credits",
    "date",
    "dates",
    "debit",
    "debits",
    "deposit",
    "deposits",
    "description",
    "details",
    "number",
    "transaction",
    "transactions",
    "withdrawal",
    "withdrawals",
}


@dataclass(frozen=True)
class StatementProfile:
    profile_id: str
    display_name: str
    detection_markers: tuple[str, ...]
    parser_kind: str = "generic"
    extra_noise_prefixes: tuple[str, ...] = ()
    extra_balance_markers: tuple[str, ...] = ()
    match_all_markers: bool = False


STATEMENT_PROFILES = (
    StatementProfile(
        profile_id="rbc",
        display_name="RBC",
        detection_markers=("royal bank of canada", "details of your account activity"),
        parser_kind="rbc",
        extra_noise_prefixes=(
            "your rbc personal banking account statement",
            "details of your account activity",
            "royal bank of canada",
        ),
        match_all_markers=True,
    ),
    StatementProfile(
        profile_id="td",
        display_name="TD Canada Trust",
        detection_markers=("td canada trust", "the toronto-dominion bank"),
        extra_noise_prefixes=(
            "td canada trust",
            "the toronto-dominion bank",
            "daily account activity",
            "statement period",
            "account activity",
        ),
        extra_balance_markers=("opening account balance", "closing account balance"),
    ),
    StatementProfile(
        profile_id="cibc",
        display_name="CIBC",
        detection_markers=("canadian imperial bank of commerce", "cibc"),
        extra_noise_prefixes=(
            "canadian imperial bank of commerce",
            "account activity",
            "statement period",
        ),
        extra_balance_markers=("opening account balance", "closing account balance"),
    ),
    StatementProfile(
        profile_id="scotiabank",
        display_name="Scotiabank",
        detection_markers=("scotiabank",),
        extra_noise_prefixes=(
            "scotiabank",
            "account details",
            "statement period",
        ),
        extra_balance_markers=("opening balance", "closing balance"),
    ),
)
GENERIC_STATEMENT_PROFILE = StatementProfile(
    profile_id="generic",
    display_name="Generic bank statement",
    detection_markers=(),
)


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts: list[str] = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            text_parts.append(page_text)

    return "\n".join(text_parts).strip()


def normalize_year_token(year_text: str | None, fallback_year: int) -> int:
    if not year_text:
        return fallback_year

    normalized = year_text.strip()
    if not normalized:
        return fallback_year

    year = int(normalized)
    if len(normalized) == 2:
        return 2000 + year
    return year


def resolve_numeric_month_day(first_text: str, second_text: str) -> tuple[int | None, int | None]:
    first = int(first_text)
    second = int(second_text)

    if first > 12 and second <= 12:
        return second, first
    if second > 31:
        return None, None
    return first, second


def parse_numeric_statement_date(
    first_text: str,
    second_text: str,
    year_text: str | None,
    fallback_year: int,
) -> date | None:
    month_num, day_num = resolve_numeric_month_day(first_text, second_text)
    if not month_num or not day_num:
        return None

    year = normalize_year_token(year_text, fallback_year)

    try:
        return date(year, month_num, day_num)
    except ValueError:
        return None


def extract_statement_period(text: str) -> tuple[date | None, date | None]:
    word_match = WORD_STATEMENT_RANGE_REGEX.search(text)
    if word_match:
        start_date = normalize_statement_date(
            word_match.group("d1"),
            word_match.group("m1"),
            int(word_match.group("y1")),
        )
        end_date = normalize_statement_date(
            word_match.group("d2"),
            word_match.group("m2"),
            int(word_match.group("y2")),
        )
        return start_date, end_date

    numeric_match = NUMERIC_STATEMENT_RANGE_REGEX.search(text)
    if not numeric_match:
        return None, None

    start_parts = re.split(r"[/-]", numeric_match.group("start"))
    end_parts = re.split(r"[/-]", numeric_match.group("end"))
    if len(start_parts) != 3 or len(end_parts) != 3:
        return None, None

    start_date = parse_numeric_statement_date(
        start_parts[0],
        start_parts[1],
        start_parts[2],
        datetime.now().year,
    )
    end_date = parse_numeric_statement_date(
        end_parts[0],
        end_parts[1],
        end_parts[2],
        datetime.now().year,
    )
    return start_date, end_date


def extract_statement_year(text: str) -> int:
    _, end_date = extract_statement_period(text)
    if end_date:
        return end_date.year

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        return int(year_match.group(1))

    return datetime.now().year


def extract_statement_year_range(text: str) -> tuple[int | None, int | None]:
    start_date, end_date = extract_statement_period(text)
    if not start_date or not end_date:
        return None, None
    return start_date.year, end_date.year


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


def detect_statement_profile(text: str) -> StatementProfile:
    lowered = text.lower()

    for profile in STATEMENT_PROFILES:
        if profile.match_all_markers:
            if all(marker in lowered for marker in profile.detection_markers):
                return profile
            continue

        if any(marker in lowered for marker in profile.detection_markers):
            return profile

    return GENERIC_STATEMENT_PROFILE


def looks_like_column_header_line(line: str) -> bool:
    words = re.findall(r"[a-z]+", line.lower())
    if not 2 <= len(words) <= 10:
        return False
    return all(word in HEADER_ONLY_WORDS for word in words)


def is_noise_line(line: str, extra_noise_prefixes: tuple[str, ...] = ()) -> bool:
    lowered = line.lower().strip()

    if not lowered:
        return True

    noise_prefixes = GENERIC_NOISE_PREFIXES + tuple(extra_noise_prefixes)

    if any(lowered.startswith(prefix) for prefix in noise_prefixes):
        return True

    if re.fullmatch(r"\d+\s+of\s+\d+", lowered):
        return True

    if re.fullmatch(r"[A-Z0-9_\-\*\/ ]{8,}", line.strip()):
        return True

    if looks_like_column_header_line(lowered):
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


def looks_like_balance_only_line(line: str, extra_balance_markers: tuple[str, ...] = ()) -> bool:
    lowered = line.lower()
    balance_markers = GENERIC_BALANCE_MARKERS + tuple(extra_balance_markers)
    return any(marker in lowered for marker in balance_markers)


def infer_amount_token_type(value: str) -> str | None:
    lowered = value.strip().lower()
    if not lowered:
        return None

    if lowered.endswith("cr"):
        return "income"

    if lowered.endswith("dr") or lowered.endswith("-"):
        return "expense"

    if lowered.startswith("-") or (lowered.startswith("(") and lowered.endswith(")")):
        return "expense"

    return None


def parse_amount_token(value: str) -> float | None:
    direction = infer_amount_token_type(value)
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None

    if cleaned.lower().endswith(("cr", "dr")):
        cleaned = cleaned[:-2]

    if cleaned.endswith("-"):
        cleaned = cleaned[:-1]

    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"

    try:
        parsed = float(cleaned)
    except ValueError:
        return None

    if direction == "income":
        return abs(parsed)
    if direction == "expense":
        return -abs(parsed)
    return parsed


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


def resolve_transaction_type(amount_text: str | None, description: str) -> str:
    if amount_text:
        explicit_type = infer_amount_token_type(amount_text)
        if explicit_type:
            return explicit_type
    return infer_transaction_type(description)


def resolve_statement_year_for_month(
    month_num: int,
    start_year: int | None,
    end_year: int | None,
) -> int:
    if start_year is None or end_year is None:
        return end_year or start_year or datetime.now().year

    if start_year == end_year:
        return end_year

    # Cross-year statements are typically Dec->Jan. Use month bucket to reduce
    # January transactions being assigned to the prior year.
    if month_num >= 10:
        return start_year
    return end_year


def extract_transaction_date_from_line(
    line: str,
    start_year: int | None,
    end_year: int | None,
    fallback_year: int,
) -> tuple[date, str] | None:
    for regex in (DAY_MONTH_DATE_START_REGEX, MONTH_DAY_DATE_START_REGEX):
        match = regex.match(line)
        if not match:
            continue

        month_num = MONTH_MAP.get(match.group("mon").strip().lower())
        if not month_num:
            continue

        default_year = resolve_statement_year_for_month(
            month_num=month_num,
            start_year=start_year,
            end_year=end_year,
        )
        normalized_date = normalize_statement_date(
            match.group("day"),
            match.group("mon"),
            normalize_year_token(match.groupdict().get("year"), default_year or fallback_year),
        )
        if normalized_date:
            return normalized_date, match.group("rest").strip()

    numeric_match = NUMERIC_DATE_START_REGEX.match(line)
    if not numeric_match:
        return None

    default_year = fallback_year
    month_num, _ = resolve_numeric_month_day(
        numeric_match.group("n1"),
        numeric_match.group("n2"),
    )
    if month_num:
        default_year = resolve_statement_year_for_month(
            month_num=month_num,
            start_year=start_year,
            end_year=end_year,
        )

    normalized_date = parse_numeric_statement_date(
        numeric_match.group("n1"),
        numeric_match.group("n2"),
        numeric_match.group("year"),
        default_year or fallback_year,
    )
    if not normalized_date:
        return None

    return normalized_date, numeric_match.group("rest").strip()


def build_profile_notes(profile: StatementProfile) -> list[str]:
    if profile.profile_id == "rbc":
        return ["Detected bank profile: RBC. Using RBC-tuned parser."]
    if profile.profile_id == "generic":
        return ["Used generic PDF parser. Accuracy may vary for this bank format."]
    return [
        f"Detected bank profile: {profile.display_name}. Using generic parser with bank-aware noise filtering; review carefully."
    ]


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

    tx_type = resolve_transaction_type(amount_text_1, description)
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
    profile: StatementProfile | None = None,
) -> dict[str, Any]:
    profile = profile or detect_statement_profile(text)
    statement_start_year, statement_end_year = extract_statement_year_range(text)
    fallback_year = extract_statement_year(text)
    lines = [line.rstrip() for line in text.splitlines()]

    preview_rows: list[StatementPreviewRow] = []
    notes = build_profile_notes(profile)

    current_date: date | None = None
    description_parts: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if is_noise_line(line, extra_noise_prefixes=profile.extra_noise_prefixes):
            continue

        if looks_like_balance_only_line(line, extra_balance_markers=profile.extra_balance_markers):
            continue

        extracted_date = extract_transaction_date_from_line(
            line=line,
            start_year=statement_start_year,
            end_year=statement_end_year,
            fallback_year=fallback_year,
        )
        if extracted_date:
            # If a new dated row starts while a previous row was incomplete, discard the incomplete one.
            if description_parts:
                description_parts = []

            current_date, line = extracted_date

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
        raise ValueError(
            "No readable text was found in this PDF statement. Scanned PDF OCR fallback is not available yet."
        )

    profile = detect_statement_profile(text)

    if profile.parser_kind == "rbc":
        return parse_rbc_statement_preview(
            db=db,
            owner_id=owner_id,
            text=text,
            profile=profile,
        )

    # Fallback generic parser
    preview_rows: list[StatementPreviewRow] = []
    notes = build_profile_notes(profile)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    statement_start_year, statement_end_year = extract_statement_year_range(text)
    fallback_year = extract_statement_year(text)
    current_date: date | None = None
    description_parts: list[str] = []

    for line in lines:
        if is_noise_line(line, extra_noise_prefixes=profile.extra_noise_prefixes) or looks_like_balance_only_line(
            line,
            extra_balance_markers=profile.extra_balance_markers,
        ):
            continue

        extracted_date = extract_transaction_date_from_line(
            line=line,
            start_year=statement_start_year,
            end_year=statement_end_year,
            fallback_year=fallback_year,
        )
        if extracted_date:
            if description_parts:
                description_parts = []

            current_date, line = extracted_date

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
