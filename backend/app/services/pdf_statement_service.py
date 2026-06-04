from __future__ import annotations

import io
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.schemas import StatementPreviewRow
from app.services.category_taxonomy import strip_payment_processor_prefixes
from app.services.import_quality_service import suggest_reference_code_amount_values
from app.services.local_ocr_service import is_local_ocr_enabled, run_local_ocr_image
from app.services.transaction_service import (
    CategoryDecision,
    build_category_review_metadata,
    categorize_transaction_details,
)
from app.services.vision_ocr_service import (
    build_input_image_part,
    is_vision_ocr_enabled,
    run_vision_prompt,
)


MONTH_WORD_PATTERN = r"[^\W\d_]{3,12}\.?"
DAY_MONTH_DATE_START_REGEX = re.compile(
    rf"^(?P<day>\d{{1,2}})\s+(?P<mon>{MONTH_WORD_PATTERN})(?:,\s*|\s+)?(?:(?P<year>\d{{2,4}})\s+)?(?P<rest>.*)$",
    flags=re.IGNORECASE,
)
MONTH_DAY_DATE_START_REGEX = re.compile(
    rf"^(?P<mon>{MONTH_WORD_PATTERN})\s+(?P<day>\d{{1,2}})(?:,\s*|\s+)?(?:(?P<year>\d{{2,4}})\s+)?(?P<rest>.*)$",
    flags=re.IGNORECASE,
)
NUMERIC_DATE_START_REGEX = re.compile(
    r"^(?P<n1>\d{1,2})[/-](?P<n2>\d{1,2})(?:[/-](?P<year>\d{2,4}))?\s+(?P<rest>.*)$"
)
AMOUNT_NUMBER_PATTERN = (
    r"(?:"
    r"\d{1,3}(?:,\d{3})+\.\d{2}"
    r"|\d{1,3}(?:[ .]\d{3})+,\d{2}"
    r"|\d+[,.]\d{2}"
    r")"
)
AMOUNT_TOKEN_PATTERN = (
    rf"\(?[+-]?\$?{AMOUNT_NUMBER_PATTERN}\)?(?:cr|dr)?"
    rf"|[+-]?\$?{AMOUNT_NUMBER_PATTERN}-"
)
TRAILING_AMOUNT_TOKEN_REGEX = re.compile(
    rf"(?i)(?:{AMOUNT_TOKEN_PATTERN})$"
)
FULL_AMOUNT_TOKEN_REGEX = re.compile(
    rf"(?i)^(?:{AMOUNT_TOKEN_PATTERN})$"
)
TRAILING_AMOUNT_CAPTURE_REGEX = re.compile(
    rf"(?i)(?<![A-Za-z0-9,.-])(?P<amount>{AMOUNT_TOKEN_PATTERN}|[-\u2013\u2014]+)\s*$"
)
PLACEHOLDER_AMOUNT_TOKEN_REGEX = re.compile(r"^[-–—]+$")
WORD_STATEMENT_RANGE_REGEX = re.compile(
    rf"From\s+(?P<m1>{MONTH_WORD_PATTERN})\s+(?P<d1>\d{{1,2}}),\s+(?P<y1>\d{{4}})\s+to\s+"
    rf"(?P<m2>{MONTH_WORD_PATTERN})\s+(?P<d2>\d{{1,2}}),\s+(?P<y2>\d{{4}})",
    flags=re.IGNORECASE,
)
NUMERIC_STATEMENT_RANGE_REGEX = re.compile(
    r"(?:(?:statement\s+period|period|from)\s*:?\s*)?"
    r"(?P<start>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:to|-)\s*"
    r"(?P<end>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    flags=re.IGNORECASE,
)
ISO_STATEMENT_RANGE_REGEX = re.compile(
    r"(?:(?:statement\s+period|period|from|du|de)\s*:?\s*)?"
    r"(?P<start>\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:to|-|au)\s*"
    r"(?P<end>\d{4}[/-]\d{1,2}[/-]\d{1,2})",
    flags=re.IGNORECASE,
)
FRENCH_STATEMENT_END_DATE_REGEX = re.compile(
    rf"periode\s+terminee\s+le\s+(?P<day>\d{{1,2}})\s+(?P<mon>{MONTH_WORD_PATTERN})\s+(?P<year>\d{{4}})",
    flags=re.IGNORECASE,
)
MONTH_MAP = {
    "jan": 1,
    "janv": 1,
    "janvier": 1,
    "january": 1,
    "feb": 2,
    "fev": 2,
    "fevr": 2,
    "fevrier": 2,
    "february": 2,
    "mar": 3,
    "mars": 3,
    "march": 3,
    "apr": 4,
    "avr": 4,
    "avril": 4,
    "april": 4,
    "may": 5,
    "mai": 5,
    "jun": 6,
    "juin": 6,
    "june": 6,
    "jul": 7,
    "juil": 7,
    "juillet": 7,
    "july": 7,
    "aug": 8,
    "aout": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "septembre": 9,
    "september": 9,
    "oct": 10,
    "octobre": 10,
    "october": 10,
    "nov": 11,
    "novembre": 11,
    "november": 11,
    "dec": 12,
    "decembre": 12,
    "december": 12,
}
PDF_TEXT_ESCAPE_REPLACEMENTS = {
    "/20": " ",
    "/21": "!",
    "/22": '"',
    "/23": "#",
    "/24": "$",
    "/25": "%",
    "/26": "&",
    "/27": "'",
    "/28": "(",
    "/29": ")",
    "/2a": "*",
    "/2b": "+",
    "/2c": ",",
    "/2d": "-",
    "/2e": ".",
    "/2f": "/",
    "/3a": ":",
    "/3b": ";",
    "/3c": "<",
    "/3d": "=",
    "/3e": ">",
    "/3f": "?",
    "/e0": "\u00e0",
    "/e2": "\u00e2",
    "/e7": "\u00e7",
    "/e8": "\u00e8",
    "/e9": "\u00e9",
    "/ea": "\u00ea",
    "/eb": "\u00eb",
    "/ee": "\u00ee",
    "/ef": "\u00ef",
    "/f4": "\u00f4",
    "/f9": "\u00f9",
    "/fb": "\u00fb",
    "/fc": "\u00fc",
}
GENERIC_NOISE_PREFIXES = (
    "important information about your account",
    "summary of your account for this period",
    "opening balance",
    "closing balance",
    "amount paid",
    "applying your payments",
    "credit card payment centre",
    "determination of interest",
    "p.o. box",
    "how to reach us",
    "interest rate chart",
    "making your payment",
    "minimum payment",
    "missed payments",
    "payment due date",
    "payments & interest rates",
    "your account number",
    "protect your pin",
    "here are four ways",
    "stay informed",
    "please check this account statement",
    "time to pay",
    "adresse de votre succursale",
    "banque de montreal",
    "bmo banque de montreal",
    "compte de cheques",
    "date description",
    "montants ajoutes",
    "montants deduits",
    "periode terminee",
    "releve de services bancaires courants",
    "services bancaires courants",
    "sommaire de votre compte",
    "titulaire du compte",
    "voici les mouvements",
    "vous pouvez nous joindre",
)
GENERIC_BALANCE_MARKERS = (
    "opening balance",
    "closing balance",
    "balance brought forward",
    "balance carried forward",
    "daily closing balance",
    "total account balance",
    "solde d'ouverture",
    "solde de fermeture",
    "solde de cloture",
    "solde total",
    "solde des montants",
    "totaux a la fermeture",
    "total des montants",
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
    "ajoutes",
    "compte",
    "deduits",
    "montants",
    "solde",
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
    balance_delta_type_inference: bool = False
    default_amount_type: str | None = None


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
        profile_id="rbc_visa",
        display_name="RBC Visa",
        detection_markers=("rbc", "visa", "activity description amount"),
        parser_kind="rbc",
        extra_noise_prefixes=(
            "rbc avion visa",
            "transaction date",
            "posting date",
            "date activity description amount",
            "payments and interest rates",
            "calculating your balance",
        ),
        extra_balance_markers=(
            "total account balance",
            "previous account balance",
            "new balance",
            "minimum payment",
        ),
        match_all_markers=True,
        default_amount_type="expense",
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
    StatementProfile(
        profile_id="tangerine",
        display_name="Tangerine",
        detection_markers=("tangerine",),
        extra_noise_prefixes=(
            "tangerine bank",
            "tangerine",
            "account activity",
            "transaction details",
            "transaction date",
            "posting date",
            "statement period",
            "account summary",
        ),
        extra_balance_markers=(
            "opening balance",
            "closing balance",
            "previous balance",
            "new balance",
            "available credit",
        ),
    ),
    StatementProfile(
        profile_id="simplii",
        display_name="Simplii Financial",
        detection_markers=("simplii financial", "simplii"),
        extra_noise_prefixes=(
            "simplii financial",
            "account activity",
            "transaction details",
            "statement period",
            "account summary",
        ),
        extra_balance_markers=(
            "opening balance",
            "closing balance",
            "previous balance",
            "new balance",
        ),
    ),
    StatementProfile(
        profile_id="desjardins",
        display_name="Desjardins",
        detection_markers=("desjardins",),
        extra_noise_prefixes=(
            "desjardins",
            "caisse desjardins",
            "releve de compte",
            "releve d'operations",
            "periode du",
            "date description",
            "description retrait depot solde",
            "description retraits depots solde",
            "folio",
            "transit",
        ),
        extra_balance_markers=(
            "solde d'ouverture",
            "solde precedent",
            "solde anterieur",
            "nouveau solde",
            "solde de cloture",
            "solde de fermeture",
        ),
        balance_delta_type_inference=True,
    ),
    StatementProfile(
        profile_id="national_bank",
        display_name="National Bank",
        detection_markers=("national bank of canada", "banque nationale"),
        extra_noise_prefixes=(
            "national bank of canada",
            "banque nationale",
            "account statement",
            "statement period",
            "account activity",
            "transaction details",
            "date description",
        ),
        extra_balance_markers=(
            "opening balance",
            "closing balance",
            "previous balance",
            "new balance",
            "solde d'ouverture",
            "solde de fermeture",
        ),
        balance_delta_type_inference=True,
    ),
    StatementProfile(
        profile_id="bmo_french",
        display_name="BMO French",
        detection_markers=("banque de montreal", "montants deduits", "montants ajoutes"),
        extra_noise_prefixes=(
            "bmo banque de montreal",
            "releve de services bancaires courants",
            "services bancaires courants",
            "adresse de votre succursale",
            "periode terminee",
            "sommaire de votre compte",
            "compte de cheques",
            "voici les mouvements",
            "date description",
            "montants deduits",
            "montants ajoutes",
        ),
        extra_balance_markers=(
            "solde d'ouverture",
            "solde de fermeture",
            "solde de cloture",
            "totaux a la fermeture",
        ),
        match_all_markers=True,
        balance_delta_type_inference=True,
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
PDF_OCR_RENDER_DPI_DEFAULT = 200
PDF_TEXT_MAX_PAGES_DEFAULT = 40
logger = logging.getLogger(__name__)


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


def get_pdf_text_max_pages() -> int:
    try:
        value = int(os.getenv("PDF_TEXT_MAX_PAGES", str(PDF_TEXT_MAX_PAGES_DEFAULT)))
    except (TypeError, ValueError):
        return PDF_TEXT_MAX_PAGES_DEFAULT
    return max(1, min(value, 200))


def strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def normalize_month_token(value: str) -> str:
    return strip_accents(value.strip().lower().rstrip("."))


def looks_like_pypdf_slash_escaped_text(text: str) -> bool:
    if re.search(r"/e[0-9a-f]", text, flags=re.IGNORECASE):
        return True

    if re.search(r"(?:/\d){2,}", text):
        return True

    punctuation_escape_count = len(re.findall(r"/(?:2[a-f]|3[a-f])", text, flags=re.IGNORECASE))
    return punctuation_escape_count >= 3


def normalize_extracted_pdf_text(text: str) -> str:
    """Decode common pypdf slash escapes seen in some Canadian bank PDFs."""
    if not text:
        return ""

    if not looks_like_pypdf_slash_escaped_text(text):
        return text.replace("\xa0", " ")

    normalized = text
    for escaped, replacement in PDF_TEXT_ESCAPE_REPLACEMENTS.items():
        normalized = normalized.replace(escaped, replacement)
        normalized = normalized.replace(escaped.upper(), replacement)

    normalized = re.sub(r"/(?=\d)", "", normalized)
    normalized = normalized.replace("\xa0", " ")
    return normalized


def get_pdf_ocr_render_dpi() -> int:
    raw_value = os.getenv("PDF_OCR_RENDER_DPI")
    if not raw_value:
        return PDF_OCR_RENDER_DPI_DEFAULT

    try:
        parsed_value = int(raw_value)
    except ValueError:
        return PDF_OCR_RENDER_DPI_DEFAULT

    return max(120, min(parsed_value, 300))


def extract_pdf_text_result(file_bytes: bytes) -> PdfTextExtractionResult:
    reader = PdfReader(io.BytesIO(file_bytes))
    text_parts: list[str] = []
    total_pages = len(reader.pages)
    max_pages = get_pdf_text_max_pages()
    if total_pages > max_pages:
        raise ValueError(f"PDF has too many pages. Maximum supported statement length is {max_pages} pages.")

    readable_text_pages = 0
    page_texts: list[str] = []

    for page in reader.pages:
        page_text = normalize_extracted_pdf_text(page.extract_text() or "")
        normalized_page_text = page_text.strip()
        page_texts.append(normalized_page_text)
        if normalized_page_text:
            readable_text_pages += 1
            text_parts.append(normalized_page_text)

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


def _load_pymupdf_module() -> Any | None:
    try:
        import pymupdf  # type: ignore[import-not-found]

        return pymupdf
    except Exception:
        try:
            import fitz  # type: ignore[import-not-found]

            return fitz
        except Exception:
            return None


def render_pdf_page_image_candidates(
    file_bytes: bytes,
    page_texts: tuple[str, ...] = (),
    skipped_page_numbers: set[int] | None = None,
) -> list[PdfPageImageCandidate]:
    pymupdf = _load_pymupdf_module()
    if pymupdf is None:
        return []

    skipped_page_numbers = skipped_page_numbers or set()
    candidates: list[PdfPageImageCandidate] = []

    try:
        document = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception:
        return []

    try:
        for page_index in range(len(document)):
            page_number = page_index + 1
            if page_number in skipped_page_numbers:
                continue
            if page_texts and page_index < len(page_texts) and page_texts[page_index].strip():
                continue

            try:
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(dpi=get_pdf_ocr_render_dpi(), alpha=False)
                image_bytes = pixmap.tobytes("png")
            except Exception:
                continue

            if image_bytes:
                candidates.append(
                    PdfPageImageCandidate(
                        page_number=page_number,
                        name=f"rendered-page-{page_number}.png",
                        data=image_bytes,
                        mime_type="image/png",
                    )
                )

            if len(candidates) >= PDF_OCR_MAX_PAGES:
                break
    finally:
        try:
            document.close()
        except Exception:
            pass

    return candidates


def extract_pdf_page_image_candidates(
    file_bytes: bytes,
    page_texts: tuple[str, ...] = (),
) -> list[PdfPageImageCandidate]:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception:
        return []

    candidates: list[PdfPageImageCandidate] = []
    pages_with_embedded_candidates: set[int] = set()

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
        page_number = page_index + 1
        pages_with_embedded_candidates.add(page_number)
        candidates.append(
            PdfPageImageCandidate(
                page_number=page_number,
                name=chosen_image.name,
                data=chosen_image.data,
                mime_type=mime_type,
            )
        )

    if len(candidates) >= PDF_OCR_MAX_PAGES:
        return candidates[:PDF_OCR_MAX_PAGES]

    rendered_candidates = render_pdf_page_image_candidates(
        file_bytes,
        page_texts=page_texts,
        skipped_page_numbers=pages_with_embedded_candidates,
    )

    return [*candidates, *rendered_candidates][:PDF_OCR_MAX_PAGES]


def ocr_pdf_page_images_with_local_tesseract(
    image_candidates: list[PdfPageImageCandidate],
) -> PdfOcrFallbackResult:
    if not image_candidates or not is_local_ocr_enabled():
        return PdfOcrFallbackResult(candidate_pages=len(image_candidates))

    processed_candidates = image_candidates[:PDF_OCR_MAX_PAGES]
    page_texts: list[str] = []
    failed_pages: list[int] = []

    for candidate in processed_candidates:
        try:
            page_text = run_local_ocr_image(candidate.data, candidate.mime_type)
        except ValueError:
            failed_pages.append(candidate.page_number)
            continue

        cleaned_text = page_text.strip()
        if cleaned_text:
            page_texts.append(cleaned_text)

    notes: list[str] = []
    if page_texts:
        notes.append(
            f"Used free local Tesseract OCR on {len(page_texts)} scanned PDF page"
            f"{'' if len(page_texts) == 1 else 's'}. Review extracted rows carefully."
        )
    elif failed_pages:
        notes.append(
            "Free local Tesseract OCR was available, but it could not recover readable text "
            "from the scanned PDF pages."
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

    accentless_text = strip_accents(text)
    french_end_match = FRENCH_STATEMENT_END_DATE_REGEX.search(accentless_text)
    if french_end_match:
        end_date = normalize_statement_date(
            french_end_match.group("day"),
            french_end_match.group("mon"),
            int(french_end_match.group("year")),
        )
        return None, end_date

    iso_match = ISO_STATEMENT_RANGE_REGEX.search(text)
    if iso_match:
        start_date = parse_iso_statement_date(iso_match.group("start"))
        end_date = parse_iso_statement_date(iso_match.group("end"))
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


def parse_iso_statement_date(value: str) -> date | None:
    parts = re.split(r"[/-]", value)
    if len(parts) != 3:
        return None

    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


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
    if not start_date and not end_date:
        return None, None
    return (start_date.year if start_date else None), (end_date.year if end_date else None)


def normalize_statement_date(day: str, mon: str, year: int) -> date | None:
    month_num = MONTH_MAP.get(normalize_month_token(mon))
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


def clean_statement_description(value: str) -> str:
    cleaned = clean_description_line(value)

    replacements = (
        (
            r"(?i)^contactless\s+interac\s+purchase\s*-\s*\d+\s+",
            "",
        ),
        (
            r"(?i)^contactless\s+interac\s+transit\s*-\s*\d+\s+(?:pres/[a-z0-9]+)?\s*",
            "Transit",
        ),
        (
            r"(?i)^online\s+banking\s+payment\s*-\s*\d+\s+",
            "",
        ),
        (
            r"(?i)^atm\s+deposit\s*-\s*[a-z0-9]+\s*",
            "ATM deposit",
        ),
        (
            r"(?i)^achat\s+par\s+carte\s+de\s+d(?:\u00e8|\u00e9|e)bit,\s*",
            "",
        ),
        (
            r"(?i)^d(?:\u00e8|\u00e9|e)p(?:\u00f4|o)t\s+direct,\s*",
            "Direct deposit ",
        ),
        (
            r"(?i)^virement\s+interac\s+re(?:\u00e7|c)u\s*",
            "Interac received ",
        ),
        (
            r"(?i)^virement\s+interac\s+envoy(?:\u00e8|\u00e9|e)\s*",
            "Interac sent ",
        ),
        (
            r"(?i)^r(?:\u00e8|e)gl\.\s+de\s+fact\.\s+en\s+ligne,?\s*(?:\d+\s*)?",
            "Online bill payment ",
        ),
        (
            r"(?i)^virement\s+en\s+ligne,\s*tf\s+[a-z0-9#-]+\s*",
            "Online transfer ",
        ),
        (
            r"(?i)^paiem(?:ent)?\s+periodiq(?:ue)?\s*",
            "Periodic payment ",
        ),
    )

    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned).strip()

    cleaned = strip_payment_processor_prefixes(cleaned)

    cleaned = re.sub(
        r"(?i)\b(e-transfer\s+received\s+[A-Z][A-Z\s.'-]*?)\s+CA[a-z0-9]+\b",
        r"\1",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\b\d{1,2}\s*(?:jan|feb|fev|f[e\u00e9]v|mar|apr|avr|may|mai|jun|jui|jul|aug|aou|ao[u\u00fb]|sep|oct|nov|dec|d[e\u00e9]c)\s*\d{4},?\s*",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\s+PRES/[A-Z0-9]+\b", "", cleaned)
    cleaned = re.sub(r"(?i)\s+CA[A-Z0-9]{5,}\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|")
    return cleaned or clean_description_line(value)


def statement_has_no_activity(text: str) -> bool:
    return bool(re.search(r"(?i)\bno\s+activity\s+for\s+this\s+period\b", text))


def detect_statement_profile(text: str) -> StatementProfile:
    lowered = strip_accents(text.lower())

    for profile in STATEMENT_PROFILES:
        if profile.match_all_markers:
            if all(marker in lowered for marker in profile.detection_markers):
                return profile
            continue

        if any(marker in lowered for marker in profile.detection_markers):
            return profile

    return GENERIC_STATEMENT_PROFILE


def looks_like_column_header_line(line: str) -> bool:
    words = re.findall(r"[a-z]+", strip_accents(line.lower()))
    if not 2 <= len(words) <= 10:
        return False
    return all(word in HEADER_ONLY_WORDS for word in words)


def is_noise_line(line: str, extra_noise_prefixes: tuple[str, ...] = ()) -> bool:
    lowered = strip_accents(line.lower().strip())

    if not lowered:
        return True

    noise_prefixes = GENERIC_NOISE_PREFIXES + tuple(extra_noise_prefixes)

    if any(lowered.startswith(prefix) for prefix in noise_prefixes):
        return True

    if re.fullmatch(r"\d+\s+of\s+\d+", lowered):
        return True

    if re.fullmatch(r"\d{8,}", line.strip()):
        return True

    if re.fullmatch(r"[A-Z0-9_\-\*\/]{8,}", line.strip()):
        return True

    if looks_like_column_header_line(lowered):
        return True

    if "gst registration number" in lowered:
        return True

    return False


def looks_like_card_reference_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line.strip())
    return bool(re.fullmatch(r"\d{10,30}", compact))


def is_statement_disclosure_description(description: str) -> bool:
    lowered = clean_statement_description(description).lower()
    lowered = lowered.replace("&", " and ")
    lowered = re.sub(r"\s+", " ", lowered).strip()

    if not lowered:
        return True

    disclosure_markers = (
        "time to pay",
        "minimum payment each month",
        "minimum payment",
        "fully repay the outstanding balance",
        "outstanding balance",
        "not a recommended long term repayment plan",
        "payments in arrears",
        "credit limit",
        "overlimit fee",
        "credit privileges",
        "authorize future transactions",
        "rbc avion visa platinum",
        "statement from",
        "remaining balance",
        "expiry date",
        "purchases and fees",
    )

    return any(marker in lowered for marker in disclosure_markers)


def is_income_description(description: str) -> bool:
    lowered = strip_accents(description.lower())

    if any(marker in lowered for marker in ("purchase interest", "interest charged")):
        return False

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
        "depot direct",
        "interac recu",
        "virement interac recu",
        "recu",
    ]

    return any(marker in lowered for marker in income_markers)


def is_credit_card_credit_description(description: str) -> bool:
    lowered = strip_accents(description.lower())
    credit_markers = (
        "payment - thank you",
        "payment thank you",
        "paiement - merci",
        "payback with points",
        "statement credit",
        "credit adjustment",
        "refund",
        "rebate",
    )
    return any(marker in lowered for marker in credit_markers)


def is_expense_description(description: str) -> bool:
    lowered = strip_accents(description.lower())
    expense_markers = [
        "purchase interest",
        "interest charged",
        "purchase",
        "pos",
        "debit",
        "achat par carte",
        "achat par carte de debit",
        "bill payment",
        "regl. de fact. en ligne",
        "reglement de facture",
        "withdrawal",
        "fee",
        "service charge",
        "pre-authorized",
        "subscription",
        "payment sent",
        "e-transfer sent",
        "interac envoye",
        "virement interac envoye",
        "cheque",
        "insurance",
        "investment",
        "misc payment",
        "monthly fee",
        "online banking payment",
        "online banking transfer",
        "virement en ligne",
        "transit",
        "presto",
    ]
    return any(marker in lowered for marker in expense_markers)


def looks_like_balance_only_line(line: str, extra_balance_markers: tuple[str, ...] = ()) -> bool:
    lowered = strip_accents(line.lower())
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
    raw_value = value.strip().replace("\xa0", " ")
    if not raw_value:
        return None

    # Reject ambiguous space-thousands with dot decimals, e.g. "7 100.00".
    # That shape can be a reference-code digit sitting beside a true amount;
    # French/Canadian space-thousands remain supported through comma decimals.
    if not FULL_AMOUNT_TOKEN_REGEX.fullmatch(raw_value):
        return None

    cleaned = raw_value.replace("$", "")
    if cleaned.lower().endswith(("cr", "dr")):
        cleaned = cleaned[:-2]

    if cleaned.endswith("-"):
        cleaned = cleaned[:-1]

    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"

    cleaned = cleaned.replace(" ", "")
    last_dot_index = cleaned.rfind(".")
    last_comma_index = cleaned.rfind(",")
    if last_dot_index >= 0 and last_comma_index >= 0:
        decimal_separator = "." if last_dot_index > last_comma_index else ","
    elif last_comma_index >= 0:
        decimal_separator = ","
    else:
        decimal_separator = "."

    if decimal_separator == ",":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")

    try:
        parsed = float(cleaned)
    except ValueError:
        return None

    if direction == "income":
        return abs(parsed)
    if direction == "expense":
        return -abs(parsed)
    return parsed


def values_match(left: float, right: float, tolerance: float = 0.02) -> bool:
    return abs(left - right) <= tolerance


def extract_last_amount_from_line(line: str) -> float | None:
    _, trailing_amounts = split_line_and_trailing_amounts(line)
    if not trailing_amounts:
        return None
    return parse_amount_token(trailing_amounts[-1])


def infer_type_from_running_balance(
    amount: float,
    previous_balance: float | None,
    current_balance: float | None,
) -> str | None:
    if previous_balance is None or current_balance is None:
        return None

    delta = current_balance - previous_balance
    if values_match(abs(delta), abs(amount)):
        if delta > 0:
            return "income"
        if delta < 0:
            return "expense"

    return None


def split_line_and_trailing_amounts(line: str) -> tuple[str, list[str]]:
    body = line.strip()
    trailing_amounts_reversed: list[str] = []

    while body:
        match = TRAILING_AMOUNT_CAPTURE_REGEX.search(body)
        if not match:
            break

        token = match.group("amount").strip()
        if not token:
            break

        trailing_amounts_reversed.append(token)
        body = body[: match.start()].rstrip()

    trailing_amounts = list(reversed(trailing_amounts_reversed))
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
    if is_credit_card_credit_description(description):
        return "income"

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
        return 0.88, None

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
    line = re.sub(
        rf"^(\d{{1,2}})\s+er\s+(?={MONTH_WORD_PATTERN}\b)",
        r"\1 ",
        line,
        flags=re.IGNORECASE,
    )

    for regex in (DAY_MONTH_DATE_START_REGEX, MONTH_DAY_DATE_START_REGEX):
        match = regex.match(line)
        if not match:
            continue

        month_num = MONTH_MAP.get(normalize_month_token(match.group("mon")))
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
    if profile.parser_kind == "rbc":
        return [f"Detected bank profile: {profile.display_name}. Using RBC-tuned parser."]
    if profile.balance_delta_type_inference:
        return [
            (
                f"Detected bank profile: {profile.display_name}. Using running-balance "
                "checks to infer income vs expense direction."
            )
        ]
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
    local_ocr_enabled = is_local_ocr_enabled()
    vision_ocr_enabled = is_vision_ocr_enabled()

    if image_candidate_count <= 0:
        return (
            "This PDF appears to have no selectable text. It may be image-only or scanned. "
            "No page images could be extracted or rendered for OCR fallback. Make sure PyMuPDF "
            "is installed so screenshot-style PDFs can be rendered before OCR."
        )

    if not local_ocr_enabled and not vision_ocr_enabled:
        return (
            "This PDF appears to have no selectable text. It may be image-only or scanned. "
            "Free local OCR is not available on this backend because Tesseract was not found, "
            "and OpenAI vision OCR is not configured. Deploy the backend with Docker so "
            "Tesseract is installed, or add a valid OPENAI_API_KEY to enable scanned PDF support."
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
    previous_balance: float | None = None,
    profile: StatementProfile | None = None,
) -> float | None:
    if not current_date or not description_parts or not trailing_amounts:
        return None

    raw_description = clean_description_line(" ".join(part for part in description_parts if part))
    if not raw_description:
        return None

    if looks_like_balance_only_line(raw_description):
        return None

    description = clean_statement_description(raw_description)
    if is_statement_disclosure_description(description):
        return None

    amount_text_1, amount_text_2, explicit_type = resolve_trailing_amount_columns(trailing_amounts)
    if not amount_text_1:
        return None

    amount = parse_amount_token(amount_text_1)
    if amount is None:
        return None

    balance_amount = parse_amount_token(amount_text_2) if amount_text_2 else None
    balance_inferred_type: str | None = None
    if profile and profile.balance_delta_type_inference:
        balance_inferred_type = infer_type_from_running_balance(
            amount=amount,
            previous_balance=previous_balance,
            current_balance=balance_amount,
        )
        if balance_inferred_type == "income":
            amount = abs(amount)
        elif balance_inferred_type == "expense":
            amount = -abs(amount)

    credit_card_credit = is_credit_card_credit_description(raw_description) or is_credit_card_credit_description(description)
    if credit_card_credit:
        amount = abs(amount)

    default_profile_type = None
    if (
        profile
        and profile.default_amount_type
        and not credit_card_credit
        and not balance_inferred_type
        and not explicit_type
    ):
        default_profile_type = profile.default_amount_type

    resolved_explicit_type = "income" if credit_card_credit else balance_inferred_type or explicit_type or default_profile_type
    tx_type = resolved_explicit_type or resolve_transaction_type(amount_text_1, raw_description)
    confidence, review_reason = build_preview_row_review_metadata(
        trailing_amounts=trailing_amounts,
        amount_text=amount_text_1,
        balance_text=amount_text_2,
        explicit_type=resolved_explicit_type,
        description=raw_description,
        tx_type=tx_type,
    )
    category_decision = safe_pdf_category_decision(
        db=db,
        owner_id=owner_id,
        description=description,
        tx_type=tx_type,
        amount=abs(amount),
    )
    category = category_decision.category
    category_review_required, category_review_reason = build_category_review_metadata(category_decision)
    amount_review = suggest_reference_code_amount_values(
        description=description,
        amount=abs(amount),
    )
    amount_confidence = 1.0
    amount_review_required = False
    amount_review_reason = None
    suggested_amount = None
    if amount_review:
        amount_confidence = amount_review.confidence
        amount_review_required = True
        amount_review_reason = amount_review.reason
        suggested_amount = amount_review.suggested_amount
        review_reason = (
            f"{review_reason} {amount_review_reason}".strip()
            if review_reason
            else amount_review_reason
        )

    source_line = raw_description
    if amount_text_2:
        source_line = f"{raw_description} | amount={amount_text_1} | balance={amount_text_2}"
    else:
        source_line = f"{raw_description} | amount={amount_text_1}"

    preview_rows.append(
        StatementPreviewRow(
            date=current_date.isoformat(),
            description=description,
            amount=abs(amount),
            amount_confidence=amount_confidence,
            amount_review_required=amount_review_required,
            amount_review_reason=amount_review_reason,
            suggested_amount=suggested_amount,
            type=tx_type,
            category=category,
            source_line=source_line[:300],
            confidence=confidence,
            review_reason=review_reason,
            category_confidence=category_decision.confidence,
            category_source=category_decision.source,
            category_reason=category_decision.reason,
            category_review_required=category_review_required,
            category_review_reason=category_review_reason,
        )
    )

    return balance_amount


def safe_pdf_category_decision(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    amount: float,
) -> CategoryDecision:
    try:
        return categorize_transaction_details(
            db=db,
            owner_id=owner_id,
            description=description,
            tx_type=tx_type,
            amount=amount,
        )
    except Exception:
        db.rollback()
        logger.warning(
            "PDF category lookup failed; falling back to review-required category for owner_id=%s tx_type=%s",
            owner_id,
            tx_type,
            exc_info=True,
        )
        return CategoryDecision(
            category="other",
            confidence=0.0,
            matched_keyword=None,
            reason="Category lookup failed while preparing this preview row. Review and choose the category before importing.",
            source="fallback",
        )


def append_note_once(notes: list[str], note: str) -> None:
    if note not in notes:
        notes.append(note)


def finalize_pending_transaction_safely(
    *,
    db: Session,
    owner_id: int,
    current_date: date | None,
    description_parts: list[str],
    trailing_amounts: list[str],
    preview_rows: list[StatementPreviewRow],
    notes: list[str],
    previous_balance: float | None = None,
    profile: StatementProfile | None = None,
) -> float | None:
    try:
        return finalize_pending_transaction(
            db=db,
            owner_id=owner_id,
            current_date=current_date,
            description_parts=description_parts,
            trailing_amounts=trailing_amounts,
            preview_rows=preview_rows,
            previous_balance=previous_balance,
            profile=profile,
        )
    except Exception:
        db.rollback()
        logger.warning(
            "PDF statement row skipped after parser conversion failure for owner_id=%s",
            owner_id,
            exc_info=True,
        )
        append_note_once(
            notes,
            "One statement row could not be safely converted and was skipped. Review the original statement and add it manually if needed.",
        )
        return previous_balance


def parse_rbc_statement_preview(
    db: Session,
    owner_id: int,
    text: str,
    profile: StatementProfile | None = None,
    additional_notes: list[str] | None = None,
    empty_result_message: str | None = None,
) -> dict[str, Any]:
    text = normalize_extracted_pdf_text(text)
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
    running_balance: float | None = None

    for raw_line in lines:
        line = raw_line.strip()
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
        else:
            if current_date and description_parts and looks_like_card_reference_line(line):
                continue

            if is_noise_line(line, extra_noise_prefixes=profile.extra_noise_prefixes):
                current_date = None
                description_parts = []
                continue

            if looks_like_balance_only_line(line, extra_balance_markers=profile.extra_balance_markers):
                line_balance = extract_last_amount_from_line(line)
                if line_balance is not None:
                    running_balance = line_balance
                current_date = None
                description_parts = []
                continue

        if not current_date:
            continue

        body, trailing_amounts = split_line_and_trailing_amounts(line)
        if trailing_amounts:
            body = clean_description_line(body)

            if body:
                description_parts.append(body)

            next_balance = finalize_pending_transaction_safely(
                db=db,
                owner_id=owner_id,
                current_date=current_date,
                description_parts=description_parts,
                trailing_amounts=trailing_amounts,
                preview_rows=preview_rows,
                notes=notes,
                previous_balance=running_balance,
                profile=profile,
            )
            if next_balance is not None:
                running_balance = next_balance

            description_parts = []
            continue

        cleaned = clean_description_line(line)
        if cleaned:
            description_parts.append(cleaned)

    if not preview_rows and statement_has_no_activity(text):
        notes.append("Statement says no activity for this period.")
        return {
            "preview_rows": [],
            "notes": notes,
        }

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
    text = normalize_extracted_pdf_text(extraction_result.text)
    image_candidates: list[PdfPageImageCandidate] = []
    ocr_result = PdfOcrFallbackResult()

    if extraction_result.readable_text_pages < extraction_result.total_pages:
        image_candidates = extract_pdf_page_image_candidates(
            file_bytes,
            page_texts=extraction_result.page_texts,
        )

        if image_candidates and is_local_ocr_enabled():
            ocr_result = ocr_pdf_page_images_with_local_tesseract(image_candidates)
            if ocr_result.text:
                text = "\n\n".join(part for part in [text, ocr_result.text] if part).strip()

        if image_candidates and not ocr_result.text and is_vision_ocr_enabled():
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
    running_balance: float | None = None

    for line in lines:
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
        else:
            if current_date and description_parts and looks_like_card_reference_line(line):
                continue

            if is_noise_line(line, extra_noise_prefixes=profile.extra_noise_prefixes) or looks_like_balance_only_line(
                line,
                extra_balance_markers=profile.extra_balance_markers,
            ):
                line_balance = extract_last_amount_from_line(line)
                if line_balance is not None:
                    running_balance = line_balance
                current_date = None
                description_parts = []
                continue

        if not current_date:
            continue

        body, trailing_amounts = split_line_and_trailing_amounts(line)
        if trailing_amounts:
            body = clean_description_line(body)

            if body:
                description_parts.append(body)

            next_balance = finalize_pending_transaction_safely(
                db=db,
                owner_id=owner_id,
                current_date=current_date,
                description_parts=description_parts,
                trailing_amounts=trailing_amounts,
                preview_rows=preview_rows,
                notes=notes,
                previous_balance=running_balance,
                profile=profile,
            )
            if next_balance is not None:
                running_balance = next_balance

            description_parts = []
            continue

        cleaned = clean_description_line(line)
        if cleaned:
            description_parts.append(cleaned)

    if not preview_rows and statement_has_no_activity(text):
        notes.append("Statement says no activity for this period.")
        return {
            "preview_rows": [],
            "notes": notes,
        }

    if not preview_rows:
        raise ValueError(no_transaction_rows_error)

    return {
        "preview_rows": preview_rows[:200],
        "notes": notes,
    }
