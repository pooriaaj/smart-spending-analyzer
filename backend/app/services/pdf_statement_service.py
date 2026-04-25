from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.schemas import StatementPreviewRow
from app.services.transaction_service import categorize_transaction_details
from app.services.vision_ocr_service import (
    build_input_image_part,
    is_vision_ocr_enabled,
    run_vision_prompt,
)


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
PLACEHOLDER_AMOUNT_TOKEN_REGEX = re.compile(r"^[-–—]+$")
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


@dataclass(frozen=True)
class PdfTextExtractionResult:
    text: str
    total_pages: int
    readable_text_pages: int
    page_texts: tuple[str, ...] = ()


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
DEFAULT_NO_TRANSACTIONS_ERROR = (
    "No transaction rows could be extracted from this PDF. Try a more text-based statement PDF."
)
PDF_OCR_MAX_PAGES = 8


@dataclass(frozen=True)
class PdfPageImageCandidate:
    page_number: int
    name: str
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class PdfOcrFallbackResult:
    text: str = ""
    notes: tuple[str, ...] = ()
    candidate_pages: int = 0
    processed_pages: int = 0


def extract_pdf_text_result(file_bytes: bytes) -> PdfTextExtractionResult:
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts: list[str] = []
    total_pages = len(reader.pages)
    readable_text_pages = 0
    page_texts: list[str] = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        normalized_page_text = page_text.strip()
        page_texts.append(normalized_page_text)
        if page_text.strip():
            readable_text_pages += 1
            text_parts.append(page_text)

    return PdfTextExtractionResult(
        text="\n".join(text_parts).strip(),
        total_pages=total_pages,
        readable_text_pages=readable_text_pages,
        page_texts=tuple(page_texts),
    )


def extract_pdf_text(file_bytes: bytes) -> str:
    return extract_pdf_text_result(file_bytes).text


def infer_pdf_image_mime_type(image_name: str, image_bytes: bytes) -> str | None:
    lowered_name = image_name.lower()

    if lowered_name.endswith((".jpg", ".jpeg")) or image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if lowered_name.endswith(".png") or image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if lowered_name.endswith(".webp") or (
        image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP"
    ):
        return "image/webp"

    return None


def extract_pdf_page_image_candidates(
    file_bytes: bytes,
    page_texts: tuple[str, ...] = (),
) -> list[PdfPageImageCandidate]:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception:
        return []

    candidates: list[PdfPageImageCandidate] = []

    for page_index, page in enumerate(reader.pages):
        if page_texts and page_index < len(page_texts) and page_texts[page_index].strip():
            continue

        try:
            page_images = list(page.images)
        except Exception:
            continue
        if not page_images:
            continue

        supported_images: list[tuple[int, Any, str]] = []
        for image in page_images:
            mime_type = infer_pdf_image_mime_type(image.name, image.data)
            if not mime_type:
                continue
            supported_images.append((len(image.data), image, mime_type))

        if not supported_images:
            continue

        _, chosen_image, mime_type = max(supported_images, key=lambda item: item[0])
        candidates.append(
            PdfPageImageCandidate(
                page_number=page_index + 1,
                name=chosen_image.name,
                data=chosen_image.data,
                mime_type=mime_type,
            )
        )

    return candidates


def ocr_pdf_page_images_to_text(
    image_candidates: list[PdfPageImageCandidate],
) -> PdfOcrFallbackResult:
    if not image_candidates:
        return PdfOcrFallbackResult()

    processed_candidates = image_candidates[:PDF_OCR_MAX_PAGES]
    prompt = """
You are extracting raw text from scanned bank statement page images.

Return only plain text from the page image.
Preserve dates, descriptions, balances, statement headers, and transaction rows.
Keep transaction rows on separate lines when possible.
Do not summarize, explain, or use markdown.
""".strip()

    page_texts: list[str] = []
    for candidate in processed_candidates:
        page_text = run_vision_prompt(
            prompt,
            [build_input_image_part(candidate.data, candidate.mime_type)],
        )
        cleaned_text = page_text.strip()
        if cleaned_text:
            page_texts.append(cleaned_text)

    notes: list[str] = []
    if page_texts:
        notes.append(
            f"Used OCR fallback on {len(page_texts)} scanned PDF page"
            f"{'' if len(page_texts) == 1 else 's'}. Review extracted rows carefully."
        )
    if len(image_candidates) > len(processed_candidates):
        notes.append(
            f"OCR fallback processed the first {len(processed_candidates)} image-only PDF pages."
        )

    return PdfOcrFallbackResult(
        text="\n\n".join(page_texts).strip(),
        notes=tuple(notes),
        candidate_pages=len(image_candidates),
        processed_pages=len(processed_candidates),
    )


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


def build_numeric_date_candidates(
    first_text: str,
    second_text: str,
    year_text: str | None,
    fallback_year: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[date]:
    first = int(first_text)
    second = int(second_text)

    month_day_pairs: list[tuple[int, int]] = []
    if first <= 12 and second <= 31:
        month_day_pairs.append((first, second))
    if second <= 12 and first <= 31 and (second, first) not in month_day_pairs:
        month_day_pairs.append((second, first))

    candidate_years: list[int] = []
    if year_text:
        candidate_years.append(normalize_year_token(year_text, fallback_year))
    else:
        candidate_years.append(fallback_year)
        if start_date:
            candidate_years.append(start_date.year)
        if end_date:
            candidate_years.append(end_date.year)

    candidates: list[date] = []
    seen: set[tuple[int, int, int]] = set()
    for year in candidate_years:
        for month_num, day_num in month_day_pairs:
            try:
                candidate = date(year, month_num, day_num)
            except ValueError:
                continue

            key = (candidate.year, candidate.month, candidate.day)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)

    return candidates


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


def is_placeholder_amount_token(value: str) -> bool:
    return bool(PLACEHOLDER_AMOUNT_TOKEN_REGEX.fullmatch(value.strip()))


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
        if TRAILING_AMOUNT_TOKEN_REGEX.fullmatch(token) or is_placeholder_amount_token(token):
            trailing_amounts_reversed.append(token)
        else:
            break

    trailing_amounts = list(reversed(trailing_amounts_reversed))
    body_token_count = len(tokens) - len(trailing_amounts)
    body = " ".join(tokens[:body_token_count]).strip()
    return body, trailing_amounts


def is_zero_amount_token(value: str) -> bool:
    parsed = parse_amount_token(value)
    return parsed is not None and abs(parsed) < 0.005


def is_effectively_empty_amount_token(value: str) -> bool:
    return is_placeholder_amount_token(value) or is_zero_amount_token(value)


def resolve_trailing_amount_columns(
    trailing_amounts: list[str],
) -> tuple[str | None, str | None, str | None]:
    if not trailing_amounts:
        return None, None, None

    if len(trailing_amounts) == 1:
        transaction_amount = trailing_amounts[0]
        if is_effectively_empty_amount_token(transaction_amount):
            return None, None, None
        return transaction_amount, None, infer_amount_token_type(transaction_amount)

    if len(trailing_amounts) >= 3:
        debit_amount = trailing_amounts[0]
        credit_amount = trailing_amounts[1]
        balance_amount = None if is_placeholder_amount_token(trailing_amounts[-1]) else trailing_amounts[-1]

        debit_is_zero = is_effectively_empty_amount_token(debit_amount)
        credit_is_zero = is_effectively_empty_amount_token(credit_amount)

        if debit_is_zero and not credit_is_zero:
            return credit_amount, balance_amount, "income"
        if credit_is_zero and not debit_is_zero:
            return debit_amount, balance_amount, "expense"

        explicit_type = infer_amount_token_type(debit_amount) or infer_amount_token_type(credit_amount)
        return debit_amount, balance_amount, explicit_type

    first_amount, second_amount = trailing_amounts
    first_is_zero = is_effectively_empty_amount_token(first_amount)
    second_is_zero = is_effectively_empty_amount_token(second_amount)

    if first_is_zero and not second_is_zero:
        return second_amount, None, "income"
    if second_is_zero and not first_is_zero:
        return first_amount, None, "expense"

    explicit_type = infer_amount_token_type(first_amount)
    return first_amount, second_amount, explicit_type


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


def build_preview_row_review_metadata(
    trailing_amounts: list[str],
    amount_text: str,
    balance_text: str | None,
    explicit_type: str | None,
    description: str,
    tx_type: str,
) -> tuple[float, str | None]:
    if explicit_type or infer_amount_token_type(amount_text):
        return 0.94, None

    if len(trailing_amounts) >= 3:
        return (
            0.58,
            "Multiple amount columns were detected without a clear debit or credit marker; verify the amount and type.",
        )

    if is_income_description(description) or is_expense_description(description):
        return 0.86, "Type was inferred from transaction wording; verify if this row looks unusual."

    if balance_text:
        return (
            0.72,
            "Detected an amount plus balance, but no debit or credit marker; verify the transaction type.",
        )

    if tx_type == "expense":
        return (
            0.68,
            "No debit or credit marker was available, so this row was assumed to be an expense.",
        )

    return 0.72, "No debit or credit marker was available; verify the transaction type."


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
    start_date: date | None = None,
    end_date: date | None = None,
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

    candidates = build_numeric_date_candidates(
        numeric_match.group("n1"),
        numeric_match.group("n2"),
        numeric_match.group("year"),
        default_year or fallback_year,
        start_date=start_date,
        end_date=end_date,
    )
    if not candidates:
        return None

    if start_date and end_date:
        in_period_candidates = [candidate for candidate in candidates if start_date <= candidate <= end_date]
        if len(in_period_candidates) == 1:
            return in_period_candidates[0], numeric_match.group("rest").strip()

    normalized_date = candidates[0]

    return normalized_date, numeric_match.group("rest").strip()


def build_profile_notes(profile: StatementProfile) -> list[str]:
    if profile.profile_id == "rbc":
        return ["Detected bank profile: RBC. Using RBC-tuned parser."]
    if profile.profile_id == "generic":
        return ["Used generic PDF parser. Accuracy may vary for this bank format."]
    return [
        f"Detected bank profile: {profile.display_name}. Using generic parser with bank-aware noise filtering; review carefully."
    ]


def build_extraction_notes(extraction_result: PdfTextExtractionResult) -> list[str]:
    if (
        extraction_result.total_pages > 1
        and 0 < extraction_result.readable_text_pages < extraction_result.total_pages
    ):
        return [
            (
                f"Only {extraction_result.readable_text_pages} of {extraction_result.total_pages} PDF pages "
                "contained selectable text. Image-only pages were checked for OCR fallback when available."
            )
        ]

    return []


def build_no_readable_text_error(
    extraction_result: PdfTextExtractionResult,
    image_candidate_count: int,
) -> str:
    if not is_vision_ocr_enabled():
        return (
            "This PDF appears to have no selectable text. It may be image-only or scanned. "
            "Add a valid OPENAI_API_KEY to enable OCR fallback for scanned PDFs."
        )

    if image_candidate_count <= 0:
        return (
            "This PDF appears to have no selectable text, and no page images could be extracted "
            "for OCR fallback."
        )

    return (
        "This PDF appears to have no selectable text, and OCR fallback could not recover "
        "readable text from its scanned pages."
    )


def build_no_transaction_rows_error(
    profile: StatementProfile,
    extraction_result: PdfTextExtractionResult,
) -> str:
    if (
        extraction_result.total_pages > 1
        and 0 < extraction_result.readable_text_pages < extraction_result.total_pages
    ):
        return (
            f"Readable text was extracted from only {extraction_result.readable_text_pages} "
            f"of {extraction_result.total_pages} PDF pages, but no transaction rows were recognized. "
            "Some pages may still need additional OCR cleanup or parser tuning."
        )

    if profile.profile_id == "generic":
        return (
            "Readable text was extracted from this PDF, but no transaction rows were recognized. "
            "This bank layout may need more parser tuning."
        )

    return (
        f"Readable text was extracted from this PDF, but no transaction rows were recognized for "
        f"the detected {profile.display_name} layout. This statement format may need more parser tuning."
    )


def strip_secondary_leading_date(
    line: str,
    start_year: int | None,
    end_year: int | None,
    fallback_year: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    secondary_date = extract_transaction_date_from_line(
        line=line,
        start_year=start_year,
        end_year=end_year,
        fallback_year=fallback_year,
        start_date=start_date,
        end_date=end_date,
    )
    if not secondary_date:
        return line

    _, remaining_line = secondary_date
    return remaining_line or line


def finalize_pending_transaction(
    db: Session,
    owner_id: int,
    current_date: date | None,
    description_parts: list[str],
    trailing_amounts: list[str],
    preview_rows: list[StatementPreviewRow],
) -> None:
    if not current_date or not description_parts or not trailing_amounts:
        return

    description = clean_description_line(" ".join(part for part in description_parts if part))
    if not description:
        return

    amount_text_1, amount_text_2, explicit_type = resolve_trailing_amount_columns(trailing_amounts)
    if not amount_text_1:
        return

    amount = parse_amount_token(amount_text_1)
    if amount is None:
        return

    tx_type = explicit_type or resolve_transaction_type(amount_text_1, description)
    confidence, review_reason = build_preview_row_review_metadata(
        trailing_amounts=trailing_amounts,
        amount_text=amount_text_1,
        balance_text=amount_text_2,
        explicit_type=explicit_type,
        description=description,
        tx_type=tx_type,
    )
    category_decision = categorize_transaction_details(
        db=db,
        owner_id=owner_id,
        description=description,
        tx_type=tx_type,
    )
    category = category_decision.category

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
            confidence=confidence,
            review_reason=review_reason,
            category_confidence=category_decision.confidence,
            category_source=category_decision.source,
            category_reason=category_decision.reason,
        )
    )


def parse_rbc_statement_preview(
    db: Session,
    owner_id: int,
    text: str,
    profile: StatementProfile | None = None,
    additional_notes: list[str] | None = None,
    empty_result_message: str | None = None,
) -> dict[str, Any]:
    statement_start_date, statement_end_date = extract_statement_period(text)
    profile = profile or detect_statement_profile(text)
    statement_start_year, statement_end_year = extract_statement_year_range(text)
    fallback_year = extract_statement_year(text)
    lines = [line.rstrip() for line in text.splitlines()]

    preview_rows: list[StatementPreviewRow] = []
    notes = build_profile_notes(profile)
    if additional_notes:
        notes.extend(additional_notes)

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
            start_date=statement_start_date,
            end_date=statement_end_date,
        )
        if extracted_date:
            # If a new dated row starts while a previous row was incomplete, discard the incomplete one.
            if description_parts:
                description_parts = []

            current_date, line = extracted_date
            line = strip_secondary_leading_date(
                line=line,
                start_year=statement_start_year,
                end_year=statement_end_year,
                fallback_year=fallback_year,
                start_date=statement_start_date,
                end_date=statement_end_date,
            )

        if not current_date:
            continue

        body, trailing_amounts = split_line_and_trailing_amounts(line)
        if trailing_amounts:
            body = clean_description_line(body)

            if body:
                description_parts.append(body)

            finalize_pending_transaction(
                db=db,
                owner_id=owner_id,
                current_date=current_date,
                description_parts=description_parts,
                trailing_amounts=trailing_amounts,
                preview_rows=preview_rows,
            )

            description_parts = []
            continue

        cleaned = clean_description_line(line)
        if cleaned:
            description_parts.append(cleaned)

    if not preview_rows:
        raise ValueError(empty_result_message or DEFAULT_NO_TRANSACTIONS_ERROR)

    return {
        "preview_rows": preview_rows[:200],
        "notes": notes,
    }


def parse_pdf_statement_preview(
    db: Session,
    owner_id: int,
    file_bytes: bytes,
) -> dict[str, Any]:
    extraction_result = extract_pdf_text_result(file_bytes)
    text = extraction_result.text
    image_candidates: list[PdfPageImageCandidate] = []
    ocr_result = PdfOcrFallbackResult()

    if extraction_result.readable_text_pages < extraction_result.total_pages:
        image_candidates = extract_pdf_page_image_candidates(
            file_bytes,
            page_texts=extraction_result.page_texts,
        )
        if image_candidates and is_vision_ocr_enabled():
            ocr_result = ocr_pdf_page_images_to_text(image_candidates)
            if ocr_result.text:
                text = "\n\n".join(part for part in [text, ocr_result.text] if part).strip()

    if not text:
        raise ValueError(
            build_no_readable_text_error(
                extraction_result,
                image_candidate_count=len(image_candidates),
            )
        )

    profile = detect_statement_profile(text)
    extraction_notes = build_extraction_notes(extraction_result) + list(ocr_result.notes)
    no_transaction_rows_error = build_no_transaction_rows_error(profile, extraction_result)

    if profile.parser_kind == "rbc":
        return parse_rbc_statement_preview(
            db=db,
            owner_id=owner_id,
            text=text,
            profile=profile,
            additional_notes=extraction_notes,
            empty_result_message=no_transaction_rows_error,
        )

    # Fallback generic parser
    preview_rows: list[StatementPreviewRow] = []
    notes = build_profile_notes(profile) + extraction_notes

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    statement_start_date, statement_end_date = extract_statement_period(text)
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
            start_date=statement_start_date,
            end_date=statement_end_date,
        )
        if extracted_date:
            if description_parts:
                description_parts = []

            current_date, line = extracted_date
            line = strip_secondary_leading_date(
                line=line,
                start_year=statement_start_year,
                end_year=statement_end_year,
                fallback_year=fallback_year,
                start_date=statement_start_date,
                end_date=statement_end_date,
            )

        if not current_date:
            continue

        body, trailing_amounts = split_line_and_trailing_amounts(line)
        if trailing_amounts:
            body = clean_description_line(body)

            if body:
                description_parts.append(body)

            finalize_pending_transaction(
                db=db,
                owner_id=owner_id,
                current_date=current_date,
                description_parts=description_parts,
                trailing_amounts=trailing_amounts,
                preview_rows=preview_rows,
            )

            description_parts = []
            continue

        cleaned = clean_description_line(line)
        if cleaned:
            description_parts.append(cleaned)

    if not preview_rows:
        raise ValueError(no_transaction_rows_error)

    return {
        "preview_rows": preview_rows[:200],
        "notes": notes,
    }
