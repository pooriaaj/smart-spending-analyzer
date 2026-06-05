from __future__ import annotations

import csv
import io
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models import (
    CategoryLearningEvent,
    CategoryMemory,
    MerchantCategoryProfile,
    MerchantLookupCache,
    Transaction,
    UserLearningPreference,
)
from app.services.category_taxonomy import (
    CATEGORY_ALIAS_EXPANSION,
    CATEGORY_KEYWORD_EXPANSION,
    MERCHANT_ALIAS_EXPANSION,
    NORTH_AMERICA_LOCATION_STOPWORDS,
    match_merchant_category_override,
    normalize_category_signal_text,
    strip_location_and_bank_noise_tokens,
    strip_payment_processor_prefixes,
)
from app.services.import_quality_service import suggest_reference_code_amount_values
from app.services.merchant_enrichment_service import enrich_merchant_category
from app.schemas import StatementPreviewRow
from app.security import max_csv_rows, sanitize_import_text


SUPPORTED_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
UNCATEGORIZED_VALUES = {"other", "misc", "uncategorized", "unknown"}
STATEMENT_RECONCILIATION_DATE_WINDOW_DAYS = 3
STATEMENT_RECONCILIATION_AMOUNT_TOLERANCE = 0.01
CATEGORY_REVIEW_CONFIDENCE_THRESHOLD = 0.75
CATEGORY_REVIEW_REQUIRED_SOURCES = {"fallback", "payment_processor"}
EXPENSE_INCOMPATIBLE_CATEGORIES = {"income", "salary", "refund"}
COMMUNITY_PROFILE_MIN_OWNER_COUNT = 2
COMMUNITY_PROFILE_MIN_OWNER_CONFIRMATIONS = 2
COMMUNITY_PROFILE_MIN_CATEGORY_SHARE = 0.67
COMMUNITY_PROFILE_AUTO_TRUST_CATEGORY_SHARE = 0.8
COMMUNITY_PROFILE_EXCLUDED_CATEGORIES = {
    "bank fees",
    "debt payments",
    "income",
    "refund",
    "rent",
    "salary",
    "taxes",
    "transfer",
}
MAX_TRANSACTION_PAGE_SIZE = 100
MAX_BULK_CATEGORY_CANDIDATES = 500
MAX_REVIEW_SCAN_TRANSACTIONS_DEFAULT = 2500
TRANSACTION_SOURCE_LABELS = {
    "manual": "Written transactions",
    "manual_import_review": "Manual import review rows",
    "csv_import": "CSV statement imports",
    "pdf_import": "PDF statement imports",
    "receipt_import": "Receipt imports",
    "statement_import": "Statement imports",
    "seed": "Demo seed data",
}
IMPORTED_TRANSACTION_SOURCES = {
    "manual_import_review",
    "csv_import",
    "pdf_import",
    "receipt_import",
    "statement_import",
}


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def max_review_scan_transactions() -> int:
    return _bounded_int_env(
        "MAX_TRANSACTION_REVIEW_SCAN",
        MAX_REVIEW_SCAN_TRANSACTIONS_DEFAULT,
        100,
        25_000,
    )

HEADER_ALIASES = {
    "date": {"date", "transaction_date", "posted_date"},
    "description": {"description", "details", "memo", "merchant", "transaction_description"},
    "amount": {"amount", "transaction_amount"},
    "debit": {"debit", "withdrawal", "money_out"},
    "credit": {"credit", "deposit", "money_in"},
    "type": {"type", "transaction_type"},
    "category": {"category", "expense", "expense_category"},
}
CSV_ROW_NUMBER_KEY = "__csv_row_number"
CSV_MONTH_CONTEXT_KEY = "__csv_month_context"
TRACKER_EXPENSE_HEADER_ALIASES = {"expense", "expense_category"}
MONTH_NAME_TO_NUMBER = {
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

CATEGORY_RULES = {
    "salary": [
        "salary",
        "payroll",
        "paycheque",
        "paycheck",
        "deposit payroll",
        "direct deposit",
        "pay/pay",
        "pay pay",
        "paie",
        "depot paie",
        "depot de paie",
        "depot direct paie",
        "cffa vendome",
    ],
    "rent": ["rent", "lease", "landlord", "hazelview", "hazielview", "hazielview prop"],
    "groceries": ["grocery", "supermarket", "freshco", "nofrills", "costco", "walmart", "loblaws"],
    "transport": ["uber", "lyft", "ttc", "presto", "parking", "transit"],
    "gas": ["gas station", "shell", "esso", "petro canada", "ultramar", "pioneer"],
    "internet": ["internet", "rogers", "bell internet"],
    "phone": ["phone", "mobile", "wireless", "telus", "freedom", "fido"],
    "restaurant": ["restaurant", "pizza", "burger", "shawarma", "mcdonald", "kfc", "subway"],
    "cafe": ["coffee", "cafe", "café", "starbucks", "tim hortons"],
    "entertainment": ["netflix", "spotify", "cinema", "movie", "youtube"],
    "shopping": ["amazon", "dollarama", "discount store", "department store", "shopping mall"],
    "transfer": [
        "e-transfer",
        "e-transfer received",
        "e-transfer sent",
        "interac received",
        "interac sent",
        "online transfer",
        "online banking transfer",
        "transfer to deposit account",
        "virement interac",
        "virement en ligne",
        "interac e-transfer received",
        "interac e-transfer sent",
        "abm transfer",
        "transfer from",
        "transfer to",
        "atm deposit",
        "payment - thank you",
        "payment thank you",
        "paiement - merci",
        "credit card payment",
    ],
    "utilities": ["utility", "utilities", "hydro", "electric", "water", "gas bill"],
    "car maintenance": ["car maintenance", "mechanic", "oil change", "tire", "repair"],
    "personal": ["personal", "haircut", "laundry", "dry cleaner"],
}

CATEGORY_RULES["groceries"].extend([
    "ambrosia natural foods",
    "ambrosia thornh",
    "ambrosia vaughan",
    "arzon",
    "asian grocery",
    "butcher",
    "convenience store",
    "discount supermarket",
    "farmers market",
    "no frills",
    "metro grocery",
    "metro supermarket",
    "provigo",
    "maxi",
    "iga",
    "super c",
    "food basics",
    "food store",
    "farm boy",
    "galleria",
    "h mart",
    "health food",
    "khorak",
    "longos",
    "market",
    "rabba",
    "sobeys",
    "t and t",
    "tnt supermarket",
    "orange mart",
    "kourosh super",
    "kourosh bakery",
    "whole foods",
])
CATEGORY_RULES["transport"].extend(["bus station", "subway station", "taxi", "train station"])
CATEGORY_RULES["restaurant"].extend([
    "bagel",
    "bistro",
    "breakfast",
    "brunch",
    "chipotle",
    "deli",
    "domino",
    "dominos",
    "donut",
    "grill",
    "kitchen",
    "mr puffs",
    "puffs",
    "ramen",
    "sandwich",
    "sushi",
    "taco",
    "thai",
    "ubereats",
    "uber eats",
    "doordash",
    "skip the dishes",
])
CATEGORY_RULES["cafe"].extend(["timhortons", "second cup", "coffee shop", "espresso", "tea house"])
CATEGORY_RULES["entertainment"].extend([
    "disney",
    "prime video",
    "apple music",
    "playstation",
    "xbox",
])
CATEGORY_RULES["personal"].extend(["just print", "print2go"])
CATEGORY_RULES.update(
    {
        "smoking": [
            "cannabis",
            "cbd",
            "cigar",
            "cigarette",
            "dispensary",
            "hookah",
            "marijuana",
            "moksha",
            "ocs",
            "smoke shop",
            "tobacco",
            "vape",
            "weed",
        ],
        "alcohol": ["lcbo", "beer store", "liquor", "wine rack", "brewery", "distillery", "winery"],
        "beauty": ["beauty", "barber", "hair salon", "nail salon", "salon", "sephora", "cosmetics", "spa"],
        "clothing": ["clothing", "foot locker", "h&m", "h and m", "shoe store", "uniqlo", "winners", "zara"],
        "home": ["home depot", "rona", "ikea", "hardware", "furniture", "home goods", "home improvement"],
        "electronics": ["best buy", "electronics", "computer", "cell phone store", "memory express"],
        "pets": ["pet store", "pet food", "petsmart", "veterinary", "vet clinic"],
        "shipping": ["canada post", "courier", "fedex", "purolator", "shipping", "ups store", "the ups store"],
        "health": [
            "clinic",
            "doctor",
            "dental",
            "dentist",
            "drugstore",
            "hospital",
            "medical",
            "pharmacy",
            "health",
            "gym",
            "shoppers drug",
        ],
        "insurance": ["insurance", "belair", "intact", "aviva", "td insurance"],
        "debt payments": [
            "loan payment",
            "student loan",
            "line of credit",
            "minimum payment",
            "purchase interest",
            "credit card interest",
            "interest charge",
        ],
        "education": ["tuition", "school", "college", "university", "course", "concordia", "univ"],
        "investment": ["investment", "wealthsimple", "ws investments"],
        "travel": ["air canada", "westjet", "hotel", "airbnb", "booking.com", "expedia"],
        "bank fees": ["monthly fee", "bank fee", "service fee"],
        "taxes": ["cra", "revenue canada", "income tax", "property tax"],
        "donations": ["charity", "donation", "gofundme", "red cross", "unicef"],
        "subscriptions": ["subscription", "patreon", "onlyfans", "substack"],
        "refund": [
            "payback with points",
            "refund",
            "rebate",
            "returned purchase",
            "statement credit",
        ],
    }
)
CATEGORY_RULES["utilities"].extend(["metergy", "ez-pay", "ez pay"])
CATEGORY_RULES["utilities"].extend(["alectra", "enbridge", "toronto hydro"])
CATEGORY_RULES["utilities"].extend(["hydro quebec", "hydro-quebec", "paiement facture hydro"])
CATEGORY_RULES["phone"].extend(["bell mobility", "koodo", "phone bill", "virgin plus"])
CATEGORY_RULES["internet"].extend(["teksavvy", "internet provider"])
CATEGORY_RULES["subscriptions"].extend([
    "apple.com/bill",
    "anthropic",
    "chatgpt",
    "claude",
    "doordashdashpass",
    "microsoft*micro",
    "microsoft 365",
    "openai",
    "spotify",
])
CATEGORY_RULES["clothing"].extend(["gap.com", "lids"])
for expanded_category, expanded_keywords in CATEGORY_KEYWORD_EXPANSION.items():
    CATEGORY_RULES.setdefault(expanded_category, [])
    CATEGORY_RULES[expanded_category].extend(expanded_keywords)

CATEGORY_ALIASES = {
    "grocery": "groceries",
    "groceries": "groceries",
    "supermarket": "groceries",
    "transport": "transport",
    "transportation": "transport",
    "cafe": "cafe",
    "café": "cafe",
    "coffee": "cafe",
    "personal": "personal",
    "shopping": "shopping",
    "smoke": "smoking",
    "smokes": "smoking",
    "smoking": "smoking",
    "tobacco": "smoking",
    "weed": "smoking",
    "vape": "smoking",
    "alcohol": "alcohol",
    "liquor": "alcohol",
    "beer": "alcohol",
    "beauty": "beauty",
    "clothing": "clothing",
    "clothes": "clothing",
    "home": "home",
    "home improvement": "home",
    "electronics": "electronics",
    "pets": "pets",
    "pet": "pets",
    "shipping": "shipping",
    "transfer": "transfer",
    "transfers": "transfer",
    "utilities": "utilities",
    "utility": "utilities",
    "other": "other",
    "misc": "other",
    "miscellaneous": "other",
    "uncategorized": "other",
    "unknown": "other",
    "restaurant": "restaurant",
    "restaurants": "restaurant",
    "salary": "salary",
    "income": "income",
    "refund": "refund",
    "rent": "rent",
    "internet": "internet",
    "phone": "phone",
    "entertainment": "entertainment",
    "car maintenance": "car maintenance",
    "car_maintenance": "car maintenance",
    "health": "health",
    "medical": "health",
    "insurance": "insurance",
    "debt": "debt payments",
    "debt payment": "debt payments",
    "debt payments": "debt payments",
    "education": "education",
    "travel": "travel",
    "investment": "investment",
    "investments": "investment",
    "bank fees": "bank fees",
    "bank fee": "bank fees",
    "tax": "taxes",
    "taxes": "taxes",
    "donation": "donations",
    "donations": "donations",
    "subscriptions": "subscriptions",
    "subscription": "subscriptions",
}
CATEGORY_ALIASES.update(CATEGORY_ALIAS_EXPANSION)

CATEGORY_MEMORY_STOPWORDS = {
    "account",
    "authorized",
    "bank",
    "bill",
    "balance",
    "balances",
    "canada",
    "card",
    "cash",
    "chequing",
    "credit",
    "date",
    "dates",
    "debit",
    "deposit",
    "deposits",
    "description",
    "descriptions",
    "etransfer",
    "e",
    "fee",
    "from",
    "funds",
    "inc",
    "international",
    "interac",
    "internet",
    "ltd",
    "memo",
    "monthly",
    "online",
    "paid",
    "pay",
    "payee",
    "payer",
    "payment",
    "payroll",
    "period",
    "pos",
    "preauthorized",
    "purchase",
    "recurring",
    "ref",
    "refund",
    "sent",
    "service",
    "statement",
    "store",
    "time",
    "to",
    "transfer",
    "txn",
    "visa",
    "withdrawal",
    "withdrawals",
}

MERCHANT_PROFILE_STOPWORDS = CATEGORY_MEMORY_STOPWORDS | {
    "amex",
    "branch",
    "cd",
    "charge",
    "city",
    "contactless",
    "corp",
    "direct",
    "mastercard",
    "merchant",
    "preauth",
    "retail",
    "terminal",
    "toronto",
    "vancouver",
}
MERCHANT_PROFILE_STOPWORDS |= NORTH_AMERICA_LOCATION_STOPWORDS

MERCHANT_PHRASE_ALIASES = {
    "ambrosia": "ambrosia",
    "arzon": "arzon",
    "bagel nash": "bagel nash",
    "orange mart": "orange mart",
    "khorak": "khorak",
    "kourosh super": "kourosh super",
    "kourosh bakery": "kourosh bakery",
    "mr puffs": "mr puffs",
    "thai island": "thai island",
    "tim hortons": "tim hortons",
    "timhortons": "tim hortons",
    "shoppers drug mart": "shoppers drug mart",
    "no frills": "no frills",
    "uber eats": "uber eats",
    "skip the dishes": "skip the dishes",
    "apple music": "apple music",
    "apple store": "apple store",
    "prime video": "prime video",
    "youtube premium": "youtube premium",
    "moksha cannabis": "moksha cannabis",
    "the ups store": "the ups store",
}
MERCHANT_PHRASE_ALIASES.update(MERCHANT_ALIAS_EXPANSION)

AMBIGUOUS_PRIMARY_MERCHANTS = {"apple", "google", "amazon", "bell", "rogers", "td", "rbc"}
AMOUNT_SENSITIVE_MERCHANT_KEYS = {
    "amazon",
    "amazon marketplace",
    "apple",
    "apple com bill",
    "bell",
    "costco",
    "dollarama",
    "google",
    "orange mart",
    "paypal",
    "rogers",
    "shoppers drug mart",
    "walmart",
}
AMOUNT_PROFILE_SEPARATOR = "|amount:"
REPEATING_DESCRIPTION_STOPWORDS = MERCHANT_PROFILE_STOPWORDS - {
    "deposit",
    "direct",
    "insurance",
    "membership",
    "payroll",
    "rent",
    "salary",
}


@dataclass(frozen=True)
class CategoryDecision:
    category: str
    confidence: float
    matched_keyword: str | None
    reason: str
    source: str


@dataclass(frozen=True)
class SuspiciousAmountRepairCandidate:
    transaction_id: int
    date: date
    description: str
    type: str
    category: str
    current_amount: float
    suggested_amount: float
    confidence: float
    reason: str


@dataclass(frozen=True)
class DuplicateTransactionGroup:
    transaction_ids: list[int]
    date: date
    description: str
    type: str
    category: str
    amount: float
    account_id: int | None
    occurrence_count: int
    reason: str


@dataclass(frozen=True)
class CategoryLearningCandidate:
    merchant_key: str
    display_name: str
    type: str
    transaction_count: int
    current_category: str
    suggested_category: str
    confidence: float
    total_amount: float
    representative_amount: float | None
    amount_min: float
    amount_max: float
    example_descriptions: list[str]
    reason: str
    review_required: bool


def build_category_review_metadata(decision: CategoryDecision) -> tuple[bool, str | None]:
    category = normalize_category_name(decision.category)
    if category in UNCATEGORIZED_VALUES:
        return (
            True,
            "No reliable category was found. Choose the real category before importing this row.",
        )

    if decision.source in CATEGORY_REVIEW_REQUIRED_SOURCES:
        return (
            True,
            (
                "This category came from a weak or generic signal. Review the merchant and approve "
                "or edit the category before importing."
            ),
        )

    if float(decision.confidence or 0) < CATEGORY_REVIEW_CONFIDENCE_THRESHOLD:
        return (
            True,
            (
                f"Category confidence is below {int(CATEGORY_REVIEW_CONFIDENCE_THRESHOLD * 100)}%. "
                "Review or edit the category before importing."
            ),
        )

    return False, None


def decode_file_bytes(file_bytes: bytes) -> str:
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode file. Supported encodings failed.")


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower().replace(" ", "_")).strip("_")


def parse_date(value: str) -> date:
    return parse_date_with_context(value)


def parse_csv_month_context_label(value: str | None) -> str | None:
    text = sanitize_import_text(value or "").strip()
    if not text:
        return None

    month_names = "|".join(MONTH_NAME_TO_NUMBER)
    match = re.fullmatch(rf"({month_names})[\s,/-]+(\d{{4}})", text, flags=re.IGNORECASE)
    if match:
        month_number = MONTH_NAME_TO_NUMBER[match.group(1).lower()]
        year = int(match.group(2))
        return f"{year:04d}-{month_number:02d}"

    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text)
    if match:
        year = int(match.group(1))
        month_number = int(match.group(2))
        if 1 <= month_number <= 12:
            return f"{year:04d}-{month_number:02d}"

    return None


def detect_csv_month_context(raw_row: list[str]) -> str | None:
    non_empty_values = [
        sanitize_import_text(value).strip()
        for value in raw_row
        if sanitize_import_text(value).strip()
    ]
    if len(non_empty_values) > 2:
        return None

    for value in non_empty_values:
        month_context = parse_csv_month_context_label(value)
        if month_context:
            return month_context
    return None


def parse_date_with_context(value: str, month_context: str | None = None) -> date:
    value = value.strip()

    if month_context:
        year_text, month_text = month_context.split("-", 1)
        context_year = int(year_text)
        context_month = int(month_text)

        day_match = re.fullmatch(r"\d{1,2}", value)
        if day_match:
            return date(context_year, context_month, int(value))

        month_names = "|".join(MONTH_NAME_TO_NUMBER)
        month_day_match = re.fullmatch(
            rf"({month_names})[\s.-]+(\d{{1,2}})",
            value,
            flags=re.IGNORECASE,
        )
        if month_day_match:
            month_number = MONTH_NAME_TO_NUMBER[month_day_match.group(1).lower()]
            return date(context_year, month_number, int(month_day_match.group(2)))

        day_month_match = re.fullmatch(
            rf"(\d{{1,2}})[\s.-]+({month_names})",
            value,
            flags=re.IGNORECASE,
        )
        if day_month_match:
            month_number = MONTH_NAME_TO_NUMBER[day_month_match.group(2).lower()]
            return date(context_year, month_number, int(day_month_match.group(1)))

    date_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Invalid date format: {value}")


def month_date_bounds(month: str | None) -> tuple[date | None, date | None]:
    if not month:
        return None, None
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("Month filter must use YYYY-MM format.")

    year, month_number = (int(part) for part in month.split("-", 1))
    start = date(year, month_number, 1)
    if month_number == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month_number + 1, 1)
    return start, end


def parse_amount(value: str) -> float:
    cleaned = (
        str(value)
        .strip()
        .lstrip("'")
        .replace("\u2212", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace(",", "")
        .replace("$", "")
        .strip()
    )
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return float(cleaned)


def normalize_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"income", "credit", "deposit"}:
        return "income"
    if normalized in {"expense", "debit", "withdrawal"}:
        return "expense"
    raise ValueError(f"Invalid transaction type: {value}")


def strip_statement_header_noise(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = re.sub(
        r"(?i)^from\s+.+?\s+to\s+.+?\s+date\s+description\s*withdrawals\s*\(\$?\)\s*"
        r"deposits\s*\(\$?\)\s*balance\s*\(\$?\)\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)^date\s+description\s*withdrawals\s*\(\$?\)\s*deposits\s*\(\$?\)\s*balance\s*\(\$?\)\s*",
        "",
        cleaned,
    )
    return re.sub(r"\s+", " ", cleaned).strip(" -|")


def strip_statement_transaction_prefixes(value: str) -> str:
    cleaned = value.strip()
    replacements = (
        (r"(?i)^contactless\s+interac\s+purchase\s*-\s*\d+\s+", ""),
        (r"(?i)^interac\s+purchase\s*-\s*\d+\s+", ""),
        (
            r"(?i)^contactless\s+interac\s+transit\s*-\s*\d+\s+(?:pres/[a-z0-9]+)?\s*",
            "Transit",
        ),
        (r"(?i)^online\s+banking\s+payment\s*-\s*\d+\s+", ""),
        (r"(?i)^atm\s+deposit\s*-\s*[a-z0-9]+\s*", "ATM deposit"),
        (r"(?i)^achat\s+par\s+carte\s+de\s+d(?:è|é|e)bit,?\s*", ""),
        (r"(?i)^d(?:è|é|e)p(?:ô|o)t\s+direct,?\s*", "Direct deposit "),
        (r"(?i)^virement\s+interac\s+re(?:ç|c)u\s*", "Interac received "),
        (r"(?i)^virement\s+interac\s+envoy(?:è|é|e)\s*", "Interac sent "),
        (r"(?i)^r(?:è|e)gl\.\s+de\s+fact\.\s+en\s+ligne,?\s*(?:\d+\s*)?", "Online bill payment "),
        (r"(?i)^virement\s+en\s+ligne,\s*tf\s+[a-z0-9#-]+\s*", "Online transfer "),
        (r"(?i)^paiem(?:ent)?\s+periodiq(?:ue)?\s*", "Periodic payment "),
    )

    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned).strip()

    return re.sub(r"\s+", " ", cleaned).strip(" -|")


def normalize_category_name(value: str | None) -> str:
    if not value:
        return "other"

    cleaned = value.strip().lower()
    cleaned = (
        unicodedata.normalize("NFD", cleaned)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    cleaned = cleaned.replace("&", "and")
    cleaned = re.sub(r"[_\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return "other"

    if cleaned in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cleaned]

    singular_map = {
        "restaurants": "restaurant",
        "transfers": "transfer",
        "utilities": "utilities",
        "groceries": "groceries",
    }
    if cleaned in singular_map:
        return singular_map[cleaned]

    return cleaned


def get_category_filter_values(category: str | None) -> set[str]:
    normalized_category = normalize_category_name(category)
    raw_category = str(category or "").strip().lower()
    category_values = {normalized_category, raw_category}

    for alias, canonical in CATEGORY_ALIASES.items():
        if canonical == normalized_category:
            category_values.add(normalize_category_name(alias))
            category_values.add(alias.strip().lower())

    return {value for value in category_values if value}


def is_usable_category_name(value: str | None) -> bool:
    normalized = normalize_category_name(value)
    if normalized in UNCATEGORIZED_VALUES:
        return True

    compact = re.sub(r"[^a-z0-9]+", "", normalized)
    return len(compact) >= 2


def should_store_category_memory(category: str | None) -> bool:
    normalized = normalize_category_name(category)
    return normalized not in UNCATEGORIZED_VALUES and is_usable_category_name(normalized)


def keyword_matches_description(keyword: str, normalized_description: str, raw_description: str = "") -> bool:
    normalized_keyword = normalize_category_signal_text(keyword)
    if not normalized_keyword:
        return False

    padded_description = f" {normalized_description} "
    padded_keyword = f" {normalized_keyword} "
    if padded_keyword in padded_description:
        return True

    if raw_description:
        raw_keyword = keyword.lower().strip()
        if raw_keyword:
            return re.search(rf"(?<![a-z0-9]){re.escape(raw_keyword)}(?![a-z0-9])", raw_description) is not None

    return False


def derive_category_memory_keywords(description: str) -> list[str]:
    normalized_description = normalize_description(description).lower()
    normalized_description = re.sub(r"[^a-z0-9& ]+", " ", normalized_description)
    normalized_description = re.sub(r"\s+", " ", normalized_description).strip()
    if not normalized_description:
        return []

    tokens = normalized_description.split()
    significant_tokens = [
        token
        for token in tokens
        if len(token) >= 3 and not token.isdigit() and token not in CATEGORY_MEMORY_STOPWORDS
    ]
    if not significant_tokens:
        return []

    keywords: list[str] = []
    primary_keyword = significant_tokens[0]
    if len(significant_tokens) >= 2:
        combined = f"{significant_tokens[0]} {significant_tokens[1]}".strip()
        if len(combined) <= 40:
            keywords.append(combined)
    keywords.append(primary_keyword)

    deduped_keywords: list[str] = []
    seen = set()
    for keyword in keywords:
        cleaned_keyword = re.sub(r"\s+", " ", keyword).strip()
        if not cleaned_keyword or cleaned_keyword in seen:
            continue
        seen.add(cleaned_keyword)
        deduped_keywords.append(cleaned_keyword)

    return deduped_keywords


def is_valid_category_memory_keyword(keyword: str | None) -> bool:
    cleaned = re.sub(r"[^a-z0-9& ]+", " ", str(keyword or "").lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or cleaned in CATEGORY_MEMORY_STOPWORDS:
        return False

    tokens = cleaned.split()
    if not tokens:
        return False
    if all(token.isdigit() or token in CATEGORY_MEMORY_STOPWORDS for token in tokens):
        return False
    return any(len(token) >= 3 and not token.isdigit() for token in tokens)


def title_case_merchant_key(value: str) -> str:
    return " ".join(word.capitalize() for word in value.split())


def extract_merchant_fingerprint(description: str) -> tuple[str, str] | None:
    normalized_description = strip_location_and_bank_noise_tokens(normalize_description(description))

    if not normalized_description:
        return None

    for phrase, alias in MERCHANT_PHRASE_ALIASES.items():
        if phrase in normalized_description:
            return alias, title_case_merchant_key(alias)

    tokens = [
        token
        for token in normalized_description.split()
        if len(token) >= 2
        and not token.isdigit()
        and not re.fullmatch(r"\d+[a-z]*", token)
        and token not in MERCHANT_PROFILE_STOPWORDS
    ]
    if not tokens:
        return None

    if tokens[0] in AMBIGUOUS_PRIMARY_MERCHANTS and len(tokens) >= 2:
        merchant_key = f"{tokens[0]} {tokens[1]}"
    elif len(tokens[0]) <= 3 and len(tokens) >= 2:
        merchant_key = f"{tokens[0]} {tokens[1]}"
    else:
        merchant_key = tokens[0]

    merchant_key = re.sub(r"\s+", " ", merchant_key).strip()
    if not merchant_key:
        return None

    return merchant_key[:160], title_case_merchant_key(merchant_key)[:160]


def merchant_profile_confidence(confirmation_count: int) -> float:
    if confirmation_count >= 5:
        return 0.99
    if confirmation_count >= 3:
        return 0.97
    if confirmation_count >= 2:
        return 0.94
    return 0.9


def merchant_profile_base_key(merchant_key: str | None) -> str:
    if not merchant_key:
        return ""
    return merchant_key.split(AMOUNT_PROFILE_SEPARATOR, 1)[0]


def merchant_key_requires_amount_guard(merchant_key: str | None) -> bool:
    base_key = merchant_profile_base_key(merchant_key).strip().lower()
    return base_key in AMOUNT_SENSITIVE_MERCHANT_KEYS


def is_valid_merchant_learning_key(merchant_key: str | None) -> bool:
    base_key = merchant_profile_base_key(merchant_key).strip().lower()
    if not base_key or base_key in MERCHANT_PROFILE_STOPWORDS:
        return False

    cleaned = re.sub(r"[^a-z0-9& ]+", " ", base_key)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return False

    tokens = cleaned.split()
    if all(token.isdigit() or token in MERCHANT_PROFILE_STOPWORDS for token in tokens):
        return False
    return any(len(token) >= 3 and not token.isdigit() for token in tokens)


def normalize_amount_for_learning(amount: float | None) -> float | None:
    if amount is None:
        return None
    try:
        normalized_amount = abs(float(amount))
    except (TypeError, ValueError):
        return None
    if normalized_amount <= 0:
        return None
    return normalized_amount


def learned_amount_bucket(amount: float | None) -> str | None:
    normalized_amount = normalize_amount_for_learning(amount)
    if normalized_amount is None:
        return None

    if normalized_amount < 20:
        bucket = round(normalized_amount / 5) * 5
    elif normalized_amount < 100:
        bucket = round(normalized_amount / 10) * 10
    elif normalized_amount < 500:
        bucket = round(normalized_amount / 25) * 25
    else:
        bucket = round(normalized_amount / 100) * 100

    return str(int(max(1, bucket)))


def learned_profile_key_for_amount(merchant_key: str, amount: float | None) -> str:
    if not merchant_key_requires_amount_guard(merchant_key):
        return merchant_key

    amount_bucket = learned_amount_bucket(amount)
    if not amount_bucket:
        return merchant_key

    return f"{merchant_key}{AMOUNT_PROFILE_SEPARATOR}{amount_bucket}"[:160]


def amounts_are_similar_for_learning(
    known_amount: float | None,
    candidate_amount: float | None,
) -> bool:
    known = normalize_amount_for_learning(known_amount)
    candidate = normalize_amount_for_learning(candidate_amount)
    if known is None or candidate is None:
        return False

    smaller = min(known, candidate)
    difference = abs(known - candidate)
    if smaller < 20:
        tolerance = max(3.0, smaller * 0.25)
    elif smaller < 100:
        tolerance = max(6.0, smaller * 0.22)
    else:
        tolerance = max(15.0, smaller * 0.18)

    return difference <= tolerance


def merchant_category_amount_matches(
    merchant_key: str | None,
    learned_amount: float | None,
    candidate_amount: float | None,
) -> bool:
    if not merchant_key_requires_amount_guard(merchant_key):
        return True
    return amounts_are_similar_for_learning(learned_amount, candidate_amount)


def merchant_profile_amount_matches(
    profile: MerchantCategoryProfile,
    candidate_amount: float | None,
) -> bool:
    if not merchant_key_requires_amount_guard(profile.merchant_key):
        return True
    return amounts_are_similar_for_learning(profile.last_amount, candidate_amount)


def merchant_profile_table_available(db: Session) -> bool:
    # The app creates this table at startup through Base.metadata.create_all.
    # Avoid runtime SQLAlchemy inspection here: on SQLite it can rollback the
    # current transaction and discard pending learning changes.
    return True


def user_allows_community_learning(db: Session, owner_id: int) -> bool:
    preference = (
        db.query(UserLearningPreference)
        .filter(UserLearningPreference.owner_id == owner_id)
        .one_or_none()
    )
    return True if preference is None else bool(preference.community_learning_enabled)


def build_community_profile_decision(
    *,
    merchant_key: str,
    profiles: Iterable[MerchantCategoryProfile],
) -> CategoryDecision | None:
    category_owners: dict[str, set[int]] = {}
    category_confirmations: Counter[str] = Counter()

    for profile in profiles:
        normalized_category = normalize_category_name(profile.category)
        if normalized_category in UNCATEGORIZED_VALUES:
            continue
        if normalized_category in COMMUNITY_PROFILE_EXCLUDED_CATEGORIES:
            continue
        if int(profile.confirmation_count or 0) < COMMUNITY_PROFILE_MIN_OWNER_CONFIRMATIONS:
            continue
        category_owners.setdefault(normalized_category, set()).add(profile.owner_id)
        category_confirmations[normalized_category] += max(1, int(profile.confirmation_count or 1))

    if not category_owners:
        return None

    all_owner_ids = set().union(*category_owners.values())
    if len(all_owner_ids) < COMMUNITY_PROFILE_MIN_OWNER_COUNT:
        return None

    best_category = max(
        category_owners,
        key=lambda category: (
            len(category_owners[category]),
            category_confirmations[category],
            category,
        ),
    )
    best_owner_count = len(category_owners[best_category])
    category_share = best_owner_count / len(all_owner_ids)
    if (
        best_owner_count < COMMUNITY_PROFILE_MIN_OWNER_COUNT
        or category_share < COMMUNITY_PROFILE_MIN_CATEGORY_SHARE
    ):
        return None

    confirmation_count = category_confirmations[best_category]
    confidence = min(
        0.9,
        0.72 + (best_owner_count * 0.05) + (min(confirmation_count, 8) * 0.01),
    )
    has_category_conflict = len(category_owners) > 1
    if has_category_conflict and category_share < COMMUNITY_PROFILE_AUTO_TRUST_CATEGORY_SHARE:
        confidence = min(confidence, 0.74)

    if has_category_conflict:
        reason = (
            "Matched anonymized community merchant learning, but users do not fully "
            "agree on this merchant yet. Review this category before saving."
        )
    else:
        reason = (
            "Matched anonymized community merchant learning from multiple users who "
            "confirmed this merchant category. Personal memory still overrides this."
        )

    return CategoryDecision(
        category=best_category,
        confidence=round(confidence, 2),
        matched_keyword=merchant_key,
        reason=reason,
        source="community_profile",
    )


def get_cached_community_profile_decision(
    db: Session,
    merchant_key: str,
    tx_type: str,
) -> CategoryDecision | None:
    cached = (
        db.query(MerchantLookupCache)
        .filter(
            MerchantLookupCache.merchant_key == merchant_key,
            MerchantLookupCache.transaction_type == tx_type,
            MerchantLookupCache.provider == "community",
        )
        .first()
    )
    if not cached:
        return None

    category = normalize_category_name(cached.category)
    if category in UNCATEGORIZED_VALUES or category in COMMUNITY_PROFILE_EXCLUDED_CATEGORIES:
        return None

    return CategoryDecision(
        category=category,
        confidence=min(0.9, float(cached.confidence or 0.78)),
        matched_keyword=cached.matched_signal or merchant_key,
        reason=(
            "Matched stored anonymized community merchant consensus. "
            "Personal memory still overrides this."
        ),
        source="community_profile",
    )


def save_community_profile_decision(
    db: Session,
    merchant_key: str,
    tx_type: str,
    decision: CategoryDecision,
) -> None:
    existing = (
        db.query(MerchantLookupCache)
        .filter(
            MerchantLookupCache.merchant_key == merchant_key,
            MerchantLookupCache.transaction_type == tx_type,
        )
        .first()
    )
    if existing:
        existing.display_name = title_case_merchant_key(merchant_key)
        existing.category = decision.category
        existing.confidence = decision.confidence
        existing.matched_signal = decision.matched_keyword
        existing.provider = "community"
        return

    db.add(
        MerchantLookupCache(
            merchant_key=merchant_key,
            display_name=title_case_merchant_key(merchant_key),
            category=decision.category,
            transaction_type=tx_type,
            confidence=decision.confidence,
            matched_signal=decision.matched_keyword,
            provider="community",
        )
    )


def clear_stale_community_profile_decision(db: Session, merchant_key: str, tx_type: str) -> None:
    existing = (
        db.query(MerchantLookupCache)
        .filter(
            MerchantLookupCache.merchant_key == merchant_key,
            MerchantLookupCache.transaction_type == tx_type,
            MerchantLookupCache.provider == "community",
        )
        .first()
    )
    if existing:
        db.delete(existing)


def refresh_community_merchant_profile_cache(
    db: Session,
    merchant_key: str,
    tx_type: str,
) -> None:
    if tx_type != "expense":
        return
    if merchant_key_requires_amount_guard(merchant_key):
        # Amount-sensitive merchants can mean different things at different
        # price points. Keep those user-specific instead of global-cached.
        return

    profiles = (
        db.query(MerchantCategoryProfile)
        .filter(
            MerchantCategoryProfile.merchant_key == merchant_key,
            MerchantCategoryProfile.transaction_type == tx_type,
        )
        .all()
    )
    profiles = [
        profile
        for profile in profiles
        if user_allows_community_learning(db, profile.owner_id)
    ]
    decision = build_community_profile_decision(merchant_key=merchant_key, profiles=profiles)
    if decision:
        save_community_profile_decision(db, merchant_key, tx_type, decision)
    else:
        clear_stale_community_profile_decision(db, merchant_key, tx_type)


def rebuild_community_merchant_profile_cache(db: Session) -> dict[str, int]:
    """Rebuild anonymized community merchant consensus from allowed profiles.

    The app never stores raw bank statements in this cache. It only stores
    merchant keys and categories confirmed by enough opted-in users.
    """

    deleted_cache_count = (
        db.query(MerchantLookupCache)
        .filter(MerchantLookupCache.provider == "community")
        .delete(synchronize_session=False)
    )
    db.flush()

    profile_keys = (
        db.query(
            MerchantCategoryProfile.merchant_key,
            MerchantCategoryProfile.transaction_type,
        )
        .distinct()
        .all()
    )

    refresh_keys: set[tuple[str, str]] = set()
    skipped_non_expense = 0
    skipped_amount_sensitive = 0
    skipped_invalid = 0

    for merchant_key, tx_type in profile_keys:
        base_key = merchant_profile_base_key(merchant_key)
        if not is_valid_merchant_learning_key(base_key):
            skipped_invalid += 1
            continue
        if tx_type != "expense":
            skipped_non_expense += 1
            continue
        if merchant_key_requires_amount_guard(base_key):
            skipped_amount_sensitive += 1
            continue
        refresh_keys.add((base_key, tx_type))

    for merchant_key, tx_type in sorted(refresh_keys):
        refresh_community_merchant_profile_cache(db, merchant_key, tx_type)

    db.flush()
    rebuilt_cache_count = (
        db.query(MerchantLookupCache)
        .filter(MerchantLookupCache.provider == "community")
        .count()
    )

    return {
        "deleted_cache_count": int(deleted_cache_count or 0),
        "candidate_key_count": len(profile_keys),
        "refreshed_key_count": len(refresh_keys),
        "rebuilt_cache_count": int(rebuilt_cache_count or 0),
        "skipped_non_expense_count": skipped_non_expense,
        "skipped_amount_sensitive_count": skipped_amount_sensitive,
        "skipped_invalid_count": skipped_invalid,
    }


def save_merchant_category_profile(
    db: Session,
    owner_id: int,
    description: str,
    category: str,
    tx_type: str,
    amount: float | None = None,
) -> dict[str, int]:
    if not merchant_profile_table_available(db):
        return {"created": 0, "updated": 0}

    normalized_category = normalize_category_name(category)
    if not should_store_category_memory(normalized_category):
        return {"created": 0, "updated": 0}

    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return {"created": 0, "updated": 0}

    merchant_key, display_name = fingerprint
    if not is_valid_merchant_learning_key(merchant_key):
        return {"created": 0, "updated": 0}

    profile_key = learned_profile_key_for_amount(merchant_key, amount)
    existing = (
        db.query(MerchantCategoryProfile)
        .filter(
            MerchantCategoryProfile.owner_id == owner_id,
            MerchantCategoryProfile.merchant_key == profile_key,
            MerchantCategoryProfile.transaction_type == tx_type,
        )
        .first()
    )

    if existing:
        existing.display_name = display_name
        existing.last_amount = amount
        if existing.category != normalized_category:
            existing.category = normalized_category
        existing.confirmation_count = int(existing.confirmation_count or 0) + 1
        existing.confidence = merchant_profile_confidence(existing.confirmation_count)
        db.flush()
        if user_allows_community_learning(db, owner_id):
            refresh_community_merchant_profile_cache(db, merchant_key, tx_type)
        return {"created": 0, "updated": 1}

    db.add(
        MerchantCategoryProfile(
            merchant_key=profile_key,
            display_name=display_name,
            category=normalized_category,
            transaction_type=tx_type,
            confidence=merchant_profile_confidence(1),
            confirmation_count=1,
            last_amount=amount,
            owner_id=owner_id,
        )
    )
    db.flush()
    if user_allows_community_learning(db, owner_id):
        refresh_community_merchant_profile_cache(db, merchant_key, tx_type)
    return {"created": 1, "updated": 0}


def save_category_memory(
    db: Session,
    owner_id: int,
    description: str,
    category: str,
    tx_type: str,
    amount: float | None = None,
) -> dict[str, int]:
    normalized_category = normalize_category_name(category)
    if not should_store_category_memory(normalized_category):
        return {"created": 0, "updated": 0}

    keywords = derive_category_memory_keywords(description)
    profile_stats = save_merchant_category_profile(
        db=db,
        owner_id=owner_id,
        description=description,
        category=normalized_category,
        tx_type=tx_type,
        amount=amount,
    )
    if not keywords:
        return profile_stats

    created = profile_stats["created"]
    updated = profile_stats["updated"]

    for keyword in keywords:
        if not is_valid_category_memory_keyword(keyword):
            continue

        existing = (
            db.query(CategoryMemory)
            .filter(
                CategoryMemory.owner_id == owner_id,
                CategoryMemory.keyword == keyword,
                CategoryMemory.transaction_type == tx_type,
            )
            .first()
        )

        if existing:
            if existing.category != normalized_category:
                existing.category = normalized_category
                updated += 1
            continue

        db.add(
            CategoryMemory(
                keyword=keyword,
                category=normalized_category,
                transaction_type=tx_type,
                owner_id=owner_id,
            )
        )
        created += 1

    return {"created": created, "updated": updated}


def record_category_learning_event(
    db: Session,
    owner_id: int,
    description: str,
    category: str,
    tx_type: str,
    *,
    amount: float | None = None,
    account_id: int | None = None,
    signal_source: str = "manual",
    confidence: float = 1.0,
    affected_count: int = 1,
) -> bool:
    normalized_category = normalize_category_name(category)
    if not should_store_category_memory(normalized_category):
        return False

    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return False

    merchant_key, display_name = fingerprint
    if not is_valid_merchant_learning_key(merchant_key):
        return False

    amount_bucket = learned_amount_bucket(amount) if merchant_key_requires_amount_guard(merchant_key) else None
    db.add(
        CategoryLearningEvent(
            merchant_key=merchant_key,
            display_name=display_name,
            category=normalized_category,
            transaction_type=tx_type,
            signal_source=signal_source[:40],
            confidence=max(0.0, min(1.0, float(confidence or 0.0))),
            affected_count=max(1, int(affected_count or 1)),
            amount_bucket=amount_bucket,
            owner_id=owner_id,
            account_id=account_id,
        )
    )
    return True


def apply_category_to_similar_transactions(
    db: Session,
    owner_id: int,
    description: str,
    category: str,
    tx_type: str,
    amount: float | None = None,
    account_id: int | None = None,
    signal_source: str | None = None,
    category_source: str | None = None,
    category_confidence: float | None = None,
    category_reason: str | None = None,
) -> int:
    normalized_category = normalize_category_name(category)
    if not should_store_category_memory(normalized_category):
        return 0

    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return 0

    merchant_key, _ = fingerprint
    if not is_valid_merchant_learning_key(merchant_key):
        return 0

    query = db.query(Transaction).filter(
        Transaction.owner_id == owner_id,
        Transaction.type == tx_type,
    )
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    candidates = query.all()

    updated_count = 0
    for transaction in candidates:
        transaction_fingerprint = extract_merchant_fingerprint(transaction.description)
        if not transaction_fingerprint or transaction_fingerprint[0] != merchant_key:
            continue
        if not merchant_category_amount_matches(merchant_key, amount, transaction.amount):
            continue
        if normalize_category_name(transaction.category) == normalized_category:
            continue

        transaction.category = normalized_category
        transaction.category_source = category_source or signal_source or "similar_category_update"
        transaction.category_confidence = max(
            0.0,
            min(1.0, float(category_confidence if category_confidence is not None else 0.9)),
        )
        transaction.category_reason = (
            category_reason
            or "Applied because this transaction matched a merchant pattern the user corrected."
        )
        updated_count += 1

    return updated_count


def get_category_learning_candidates(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    limit: int = 12,
) -> list[CategoryLearningCandidate]:
    max_candidates = max(1, min(int(limit or 12), 50))
    scan_limit = max_review_scan_transactions()
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    transactions = (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(scan_limit)
        .all()
    )
    grouped: dict[tuple[str, str, int], list[Transaction]] = {}
    display_names: dict[tuple[str, str, int], str] = {}
    representative_amounts: dict[tuple[str, str, int], float | None] = {}
    cluster_counts: dict[tuple[str, str], int] = {}

    for transaction in transactions:
        fingerprint = extract_merchant_fingerprint(transaction.description)
        if not fingerprint:
            continue
        merchant_key, display_name = fingerprint
        group_base = (merchant_key, transaction.type)
        group_key: tuple[str, str, int] | None = None

        if merchant_key_requires_amount_guard(merchant_key):
            normalized_amount = normalize_amount_for_learning(transaction.amount)
            for existing_key, representative_amount in representative_amounts.items():
                if existing_key[:2] != group_base:
                    continue
                if amounts_are_similar_for_learning(representative_amount, normalized_amount):
                    group_key = existing_key
                    break

            if group_key is None:
                next_cluster = cluster_counts.get(group_base, 0) + 1
                cluster_counts[group_base] = next_cluster
                group_key = (merchant_key, transaction.type, next_cluster)
                representative_amounts[group_key] = normalized_amount
        else:
            group_key = (merchant_key, transaction.type, 0)
            representative_amounts.setdefault(group_key, None)

        grouped.setdefault(group_key, []).append(transaction)
        display_names.setdefault(group_key, display_name)

    candidates: list[CategoryLearningCandidate] = []
    for (merchant_key, tx_type, _cluster_index), items in grouped.items():
        candidate_group_key = (merchant_key, tx_type, _cluster_index)
        if len(items) < 2:
            continue

        category_counts = Counter(normalize_category_name(item.category) for item in items)
        current_category, _ = category_counts.most_common(1)[0]
        representative = next(
            (item for item in items if normalize_category_name(item.category) in UNCATEGORIZED_VALUES),
            items[0],
        )
        decision = categorize_transaction_details(
            db=db,
            owner_id=owner_id,
            description=representative.description,
            tx_type=representative.type,
            amount=representative.amount,
        )
        suggested_category = normalize_category_name(decision.category)
        review_required, review_reason = build_category_review_metadata(decision)

        has_uncategorized = any(category in UNCATEGORIZED_VALUES for category in category_counts)
        has_mixed_categories = len(category_counts) > 1
        would_change_category = (
            suggested_category not in UNCATEGORIZED_VALUES
            and suggested_category != current_category
        )
        should_surface = has_uncategorized or has_mixed_categories or would_change_category or review_required
        if not should_surface:
            continue

        amounts = [abs(float(item.amount or 0.0)) for item in items]
        examples: list[str] = []
        seen_examples = set()
        for item in items:
            description = normalize_description(item.description)
            if not description or description.lower() in seen_examples:
                continue
            examples.append(description)
            seen_examples.add(description.lower())
            if len(examples) >= 3:
                break

        reason_parts = []
        if has_uncategorized:
            reason_parts.append("some transactions are still Other")
        if has_mixed_categories:
            reason_parts.append("similar transactions currently use different categories")
        if would_change_category:
            reason_parts.append(f"the learning engine suggests {suggested_category}")
        if review_required and review_reason:
            reason_parts.append(review_reason)
        representative_amount = representative_amounts.get((merchant_key, tx_type, _cluster_index))
        if merchant_key_requires_amount_guard(merchant_key) and representative_amount is not None:
            reason_parts.append(
                f"amount-sensitive merchant grouped around ${representative_amount:.2f}"
            )

        candidates.append(
            CategoryLearningCandidate(
                merchant_key=merchant_key,
                display_name=display_names.get(candidate_group_key, title_case_merchant_key(merchant_key)),
                type=tx_type,
                transaction_count=len(items),
                current_category=current_category,
                suggested_category=(
                    suggested_category
                    if suggested_category not in UNCATEGORIZED_VALUES
                    else current_category
                ),
                confidence=float(decision.confidence or 0.0),
                total_amount=round(sum(amounts), 2),
                representative_amount=(
                    round(float(representative_amount), 2)
                    if representative_amount is not None
                    else None
                ),
                amount_min=round(min(amounts), 2) if amounts else 0.0,
                amount_max=round(max(amounts), 2) if amounts else 0.0,
                example_descriptions=examples,
                reason="; ".join(reason_parts) or decision.reason,
                review_required=(
                    has_uncategorized
                    or has_mixed_categories
                    or review_required
                    or suggested_category in UNCATEGORIZED_VALUES
                ),
            )
        )

    candidates.sort(
        key=lambda item: (
            item.current_category not in UNCATEGORIZED_VALUES,
            -item.transaction_count,
            -item.total_amount,
            item.display_name.lower(),
        )
    )
    return candidates[:max_candidates]


def get_category_learning_summary(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> dict:
    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    transaction_count = scope_query.count()
    uncategorized_count = (
        scope_query.filter(func.lower(Transaction.category).in_(tuple(UNCATEGORIZED_VALUES))).count()
    )
    personal_memory_count = (
        db.query(CategoryMemory)
        .filter(CategoryMemory.owner_id == owner_id)
        .count()
    )
    merchant_profile_count = (
        db.query(MerchantCategoryProfile)
        .filter(MerchantCategoryProfile.owner_id == owner_id)
        .count()
    )
    learning_candidate_count = min(int(uncategorized_count or 0), 50)
    community_learning_enabled = user_allows_community_learning(db, owner_id)
    community_pattern_count = (
        db.query(MerchantLookupCache)
        .filter(MerchantLookupCache.provider == "community")
        .count()
        if community_learning_enabled
        else 0
    )
    learning_event_count = (
        db.query(CategoryLearningEvent)
        .filter(CategoryLearningEvent.owner_id == owner_id)
        .count()
    )
    recent_learning_events = (
        db.query(CategoryLearningEvent)
        .filter(CategoryLearningEvent.owner_id == owner_id)
        .order_by(CategoryLearningEvent.created_at.desc(), CategoryLearningEvent.id.desc())
        .limit(5)
        .all()
    )

    if transaction_count == 0:
        confidence_level = "empty"
        confidence_score = 0.0
        message = "Start by adding transactions or importing this month's statement."
    else:
        uncategorized_share = uncategorized_count / max(transaction_count, 1)
        review_penalty = min(0.3, learning_candidate_count * 0.04)
        memory_bonus = min(0.18, (personal_memory_count + merchant_profile_count) * 0.015)
        confidence_score = max(
            0.05,
            min(0.98, 0.82 - (uncategorized_share * 0.65) - review_penalty + memory_bonus),
        )
        if confidence_score >= 0.82 and learning_candidate_count == 0:
            confidence_level = "high"
            message = "Category learning looks healthy. Keep correcting new merchants as they appear."
        elif confidence_score >= 0.62:
            confidence_level = "medium"
            message = "Learning is improving, but a few merchant groups still need review."
        else:
            confidence_level = "low"
            message = "The app needs more confirmed categories before suggestions become reliable."

    return {
        "transaction_count": transaction_count,
        "uncategorized_count": uncategorized_count,
        "learning_candidate_count": learning_candidate_count,
        "personal_memory_count": personal_memory_count,
        "merchant_profile_count": merchant_profile_count,
        "community_learning_enabled": community_learning_enabled,
        "community_pattern_count": community_pattern_count,
        "learning_event_count": learning_event_count,
        "recent_learning_events": [
            {
                "merchant_key": event.merchant_key,
                "display_name": event.display_name,
                "category": event.category,
                "type": event.transaction_type,
                "signal_source": event.signal_source,
                "confidence": round(float(event.confidence or 0.0), 2),
                "affected_count": int(event.affected_count or 1),
                "created_at": event.created_at,
            }
            for event in recent_learning_events
        ],
        "confidence_level": confidence_level,
        "confidence_score": round(confidence_score, 2),
        "message": message,
    }


def apply_category_to_merchant_learning_group(
    db: Session,
    owner_id: int,
    merchant_key: str,
    tx_type: str,
    category: str,
    account_id: int | None = None,
    representative_amount: float | None = None,
) -> dict[str, int]:
    normalized_category = normalize_category_name(category)
    if not should_store_category_memory(normalized_category):
        return {
            "matched_count": 0,
            "updated_count": 0,
            "memory_entries_created": 0,
            "memory_entries_updated": 0,
        }

    normalized_merchant_key = merchant_profile_base_key(
        re.sub(r"\s+", " ", merchant_key.strip().lower())[:160]
    )
    amount_guard_required = merchant_key_requires_amount_guard(normalized_merchant_key)
    normalized_representative_amount = normalize_amount_for_learning(representative_amount)
    if amount_guard_required and normalized_representative_amount is None:
        return {
            "matched_count": 0,
            "updated_count": 0,
            "memory_entries_created": 0,
            "memory_entries_updated": 0,
        }

    query = db.query(Transaction).filter(
        Transaction.owner_id == owner_id,
        Transaction.type == tx_type,
    )
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    matched_count = 0
    updated_count = 0
    memory_created = 0
    memory_updated = 0
    representative_transaction: Transaction | None = None

    for transaction in query.all():
        fingerprint = extract_merchant_fingerprint(transaction.description)
        if not fingerprint or fingerprint[0] != normalized_merchant_key:
            continue
        if amount_guard_required and not merchant_category_amount_matches(
            normalized_merchant_key,
            normalized_representative_amount,
            transaction.amount,
        ):
            continue

        matched_count += 1
        if representative_transaction is None:
            representative_transaction = transaction
        if normalize_category_name(transaction.category) != normalized_category:
            transaction.category = normalized_category
            transaction.category_source = "learning_apply"
            transaction.category_confidence = 1.0
            transaction.category_reason = (
                "Applied from a user-confirmed merchant learning group."
            )
            updated_count += 1

    if representative_transaction is not None:
        memory_stats = save_category_memory(
            db=db,
            owner_id=owner_id,
            description=representative_transaction.description,
            category=normalized_category,
            tx_type=tx_type,
            amount=representative_transaction.amount,
        )
        memory_created += memory_stats["created"]
        memory_updated += memory_stats["updated"]
        record_category_learning_event(
            db=db,
            owner_id=owner_id,
            description=representative_transaction.description,
            category=normalized_category,
            tx_type=tx_type,
            amount=representative_transaction.amount,
            account_id=representative_transaction.account_id,
            signal_source="learning_apply",
            confidence=1.0,
            affected_count=matched_count,
        )

    if matched_count > 0:
        db.commit()

    return {
        "matched_count": matched_count,
        "updated_count": updated_count,
        "memory_entries_created": memory_created,
        "memory_entries_updated": memory_updated,
    }


def apply_category_review_correction(
    db: Session,
    owner_id: int,
    transaction_id: int,
    category: str,
    *,
    apply_to_similar: bool = True,
) -> dict[str, int | str | bool] | None:
    transaction = (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id, Transaction.id == transaction_id)
        .one_or_none()
    )
    if not transaction:
        return None

    normalized_category = normalize_category_name(category)
    direct_was_changed = (
        normalize_category_name(transaction.category) != normalized_category
        or transaction.category_source != "category_review_apply"
        or float(transaction.category_confidence or 0.0) < 1.0
    )

    transaction.category = normalized_category
    transaction.category_source = "category_review_apply"
    transaction.category_confidence = 1.0
    transaction.category_reason = (
        "User reviewed this transaction category and taught the app this merchant pattern."
    )

    similar_updated_count = 0
    if apply_to_similar:
        similar_updated_count = apply_category_to_similar_transactions(
            db=db,
            owner_id=owner_id,
            description=transaction.description,
            category=normalized_category,
            tx_type=transaction.type,
            amount=transaction.amount,
            account_id=transaction.account_id,
            signal_source="category_review_apply",
            category_source="category_review_apply",
            category_confidence=1.0,
            category_reason=(
                "Applied from a user-reviewed category on a similar merchant transaction."
            ),
        )

    memory_stats = save_category_memory(
        db=db,
        owner_id=owner_id,
        description=transaction.description,
        category=normalized_category,
        tx_type=transaction.type,
        amount=transaction.amount,
    )
    learning_event_recorded = record_category_learning_event(
        db=db,
        owner_id=owner_id,
        description=transaction.description,
        category=normalized_category,
        tx_type=transaction.type,
        amount=transaction.amount,
        account_id=transaction.account_id,
        signal_source="category_review_apply",
        confidence=1.0,
        affected_count=similar_updated_count + 1,
    )

    db.commit()
    db.refresh(transaction)

    direct_updated_count = 1 if direct_was_changed else 0
    return {
        "transaction_id": transaction.id,
        "category": normalized_category,
        "matched_count": similar_updated_count + 1,
        "updated_count": direct_updated_count + similar_updated_count,
        "similar_updated_count": similar_updated_count,
        "memory_entries_created": memory_stats["created"],
        "memory_entries_updated": memory_stats["updated"],
        "learning_event_recorded": learning_event_recorded,
    }


def suggest_reference_code_amount_repair(transaction: Transaction) -> SuspiciousAmountRepairCandidate | None:
    description = normalize_description(transaction.description)
    suggestion = suggest_reference_code_amount_values(
        description=description,
        amount=transaction.amount,
    )
    if not suggestion:
        return None

    return SuspiciousAmountRepairCandidate(
        transaction_id=transaction.id,
        date=transaction.date,
        description=description,
        type=transaction.type,
        category=transaction.category,
        current_amount=abs(float(transaction.amount or 0)),
        suggested_amount=suggestion.suggested_amount,
        confidence=suggestion.confidence,
        reason=suggestion.reason,
    )


def get_suspicious_amount_repair_candidates(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> list[SuspiciousAmountRepairCandidate]:
    scan_limit = max_review_scan_transactions()
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    candidates: list[SuspiciousAmountRepairCandidate] = []
    for transaction in (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(scan_limit)
        .all()
    ):
        candidate = suggest_reference_code_amount_repair(transaction)
        if candidate:
            candidates.append(candidate)

    return candidates


def count_likely_duplicate_transactions(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> int:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    seen_counts: Counter[tuple] = Counter()
    for transaction in query.all():
        duplicate_key = (
            transaction.account_id or 0,
            transaction.date.isoformat(),
            normalize_description(transaction.description).lower(),
            round(abs(float(transaction.amount or 0.0)), 2),
            str(transaction.type or "").strip().lower(),
        )
        seen_counts[duplicate_key] += 1

    return sum(count - 1 for count in seen_counts.values() if count > 1)


def get_likely_duplicate_transaction_groups(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    limit: int = 10,
) -> list[DuplicateTransactionGroup]:
    max_groups = max(1, min(int(limit or 10), 50))
    scan_limit = max_review_scan_transactions()
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    grouped: dict[tuple, list[Transaction]] = {}
    for transaction in (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(scan_limit)
        .all()
    ):
        duplicate_key = (
            transaction.account_id or 0,
            transaction.date.isoformat(),
            normalize_description(transaction.description).lower(),
            round(abs(float(transaction.amount or 0.0)), 2),
            str(transaction.type or "").strip().lower(),
        )
        grouped.setdefault(duplicate_key, []).append(transaction)

    duplicate_groups: list[DuplicateTransactionGroup] = []
    for items in grouped.values():
        if len(items) < 2:
            continue

        first = items[0]
        amount = round(abs(float(first.amount or 0.0)), 2)
        duplicate_groups.append(
            DuplicateTransactionGroup(
                transaction_ids=[int(item.id) for item in items],
                date=first.date,
                description=normalize_description(first.description),
                type=str(first.type or "").strip().lower(),
                category=normalize_category_name(first.category),
                amount=amount,
                account_id=first.account_id,
                occurrence_count=len(items),
                reason=(
                    "These rows have the same account, date, description, type, and amount. "
                    "Review before trusting analytics totals."
                ),
            )
        )

    duplicate_groups.sort(
        key=lambda item: (
            -item.occurrence_count,
            -item.amount,
            item.date,
            item.description.lower(),
        )
    )
    return duplicate_groups[:max_groups]


def duplicate_keep_priority(transaction: Transaction) -> tuple:
    source = str(transaction.entry_source or "").strip().lower()
    source_priority = 0 if source == "manual" else 1
    confidence_priority = -float(transaction.category_confidence or 0.0)
    import_priority = 1 if transaction.imported_at else 0
    return (
        source_priority,
        confidence_priority,
        import_priority,
        int(transaction.id or 0),
    )


def apply_likely_duplicate_cleanup(
    db: Session,
    owner_id: int,
    transaction_ids: Iterable[int],
    account_id: int | None = None,
) -> dict:
    requested_ids = {int(transaction_id) for transaction_id in transaction_ids}
    if not requested_ids:
        return {
            "deleted_count": 0,
            "kept_transaction_ids": [],
            "deleted_transaction_ids": [],
            "skipped_transaction_ids": [],
        }

    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    grouped: dict[tuple, list[Transaction]] = {}
    scoped_transaction_ids: set[int] = set()
    for transaction in query.order_by(Transaction.id.asc()).all():
        scoped_transaction_ids.add(int(transaction.id))
        duplicate_key = (
            transaction.account_id or 0,
            transaction.date.isoformat(),
            normalize_description(transaction.description).lower(),
            round(abs(float(transaction.amount or 0.0)), 2),
            str(transaction.type or "").strip().lower(),
        )
        grouped.setdefault(duplicate_key, []).append(transaction)

    deleted_transaction_ids: list[int] = []
    kept_transaction_ids: set[int] = set()
    duplicate_member_ids: set[int] = set()

    for items in grouped.values():
        if len(items) < 2:
            continue

        duplicate_member_ids.update(int(item.id) for item in items)
        keep_transaction = sorted(items, key=duplicate_keep_priority)[0]
        kept_transaction_ids.add(int(keep_transaction.id))

        for transaction in items:
            transaction_id = int(transaction.id)
            if transaction_id == int(keep_transaction.id):
                continue
            if transaction_id not in requested_ids:
                continue

            db.delete(transaction)
            deleted_transaction_ids.append(transaction_id)

    skipped_transaction_ids = sorted(
        transaction_id
        for transaction_id in requested_ids
        if transaction_id not in deleted_transaction_ids
        and (
            transaction_id not in scoped_transaction_ids
            or transaction_id not in duplicate_member_ids
            or transaction_id in kept_transaction_ids
        )
    )

    if deleted_transaction_ids:
        db.commit()

    return {
        "deleted_count": len(deleted_transaction_ids),
        "kept_transaction_ids": sorted(kept_transaction_ids),
        "deleted_transaction_ids": sorted(deleted_transaction_ids),
        "skipped_transaction_ids": skipped_transaction_ids,
    }


def apply_suspicious_amount_repairs(
    db: Session,
    owner_id: int,
    transaction_ids: Iterable[int],
    account_id: int | None = None,
) -> dict:
    requested_ids = {int(transaction_id) for transaction_id in transaction_ids}
    if not requested_ids:
        return {"updated_count": 0, "repairs": []}

    query = db.query(Transaction).filter(
        Transaction.owner_id == owner_id,
        Transaction.id.in_(requested_ids),
    )
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    updated_repairs: list[dict] = []
    for transaction in query.all():
        candidate = suggest_reference_code_amount_repair(transaction)
        if not candidate:
            continue

        transaction.amount = candidate.suggested_amount
        updated_repairs.append(
            {
                "transaction_id": candidate.transaction_id,
                "previous_amount": candidate.current_amount,
                "updated_amount": candidate.suggested_amount,
                "description": candidate.description,
            }
        )

    if updated_repairs:
        db.commit()

    return {
        "updated_count": len(updated_repairs),
        "repairs": updated_repairs,
    }


def sniff_csv_dialect(text: str) -> csv.Dialect:
    sample = text[:5000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;|\t")
    except csv.Error:
        return csv.get_dialect("excel")


def resolve_header_mapping(fieldnames: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for canonical, aliases in HEADER_ALIASES.items():
        for header in fieldnames:
            if csv_header_base_name(header) in aliases:
                mapping[canonical] = header
                break

    if not mapping.get("date") or not mapping.get("description"):
        raise ValueError("Statement must include at least date and description columns.")

    if not (
        mapping.get("amount")
        or (mapping.get("debit") and mapping.get("credit"))
        or mapping.get("type")
    ):
        raise ValueError("Statement must include amount, or debit/credit columns.")

    category_key = mapping.get("category")
    if (
        category_key
        and csv_header_base_name(category_key) in TRACKER_EXPENSE_HEADER_ALIASES
        and mapping.get("amount")
        and not mapping.get("type")
    ):
        mapping["default_type"] = "expense"

    return mapping


def csv_header_base_name(header: str) -> str:
    return re.sub(r"__dup\d+$", "", header)


def normalize_csv_headers(fieldnames: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    normalized_headers: list[str] = []

    for index, fieldname in enumerate(fieldnames, start=1):
        base_header = normalize_header(fieldname) or f"column_{index}"
        counts[base_header] = counts.get(base_header, 0) + 1
        if counts[base_header] == 1:
            normalized_headers.append(base_header)
        else:
            normalized_headers.append(f"{base_header}__dup{counts[base_header]}")

    return normalized_headers


def find_csv_header_row(raw_rows: list[list[str]]) -> tuple[int, list[str], dict[str, str]]:
    for row_index, row in enumerate(raw_rows):
        normalized_headers = normalize_csv_headers(row)
        try:
            header_mapping = resolve_header_mapping(normalized_headers)
        except ValueError:
            continue
        return row_index, normalized_headers, header_mapping

    raise ValueError("Statement must include at least date and description columns.")


def read_csv_rows(text: str) -> tuple[list[dict], dict[str, str]]:
    dialect = sniff_csv_dialect(text)
    raw_rows = list(csv.reader(io.StringIO(text), dialect=dialect))

    if not raw_rows:
        raise ValueError("CSV file is missing headers.")

    header_index, normalized_headers, header_mapping = find_csv_header_row(raw_rows)

    current_month_context = None
    for raw_row in raw_rows[:header_index]:
        current_month_context = detect_csv_month_context(raw_row) or current_month_context

    rows = []
    for index, raw_row in enumerate(raw_rows[header_index + 1 :], start=1):
        if index > max_csv_rows():
            raise ValueError(f"CSV row limit exceeded. Maximum is {max_csv_rows()} rows per file.")

        detected_month_context = detect_csv_month_context(raw_row)
        if detected_month_context:
            current_month_context = detected_month_context
            continue

        padded_row = [*raw_row, *[""] * max(0, len(normalized_headers) - len(raw_row))]
        normalized_row = {
            header: sanitize_import_text(value)
            for header, value in zip(normalized_headers, padded_row[: len(normalized_headers)])
        }
        normalized_row[CSV_ROW_NUMBER_KEY] = str(header_index + index + 1)
        normalized_row[CSV_MONTH_CONTEXT_KEY] = current_month_context or ""
        rows.append(normalized_row)

    return rows, header_mapping


def infer_type_and_amount(row: dict, header_mapping: dict[str, str]) -> tuple[str, float]:
    amount_key = header_mapping.get("amount")
    debit_key = header_mapping.get("debit")
    credit_key = header_mapping.get("credit")
    type_key = header_mapping.get("type")

    if amount_key:
        amount = parse_amount(row.get(amount_key, "0"))
        if type_key and row.get(type_key):
            tx_type = normalize_type(row[type_key])
            return tx_type, abs(amount)

        default_type = header_mapping.get("default_type")
        if default_type in {"expense", "income"}:
            return default_type, abs(amount)

        if amount < 0:
            return "expense", abs(amount)
        return "income", abs(amount)

    debit_value = row.get(debit_key, "") if debit_key else ""
    credit_value = row.get(credit_key, "") if credit_key else ""

    if debit_value:
        return "expense", abs(parse_amount(debit_value))
    if credit_value:
        return "income", abs(parse_amount(credit_value))

    raise ValueError("Could not infer transaction amount/type.")


def normalize_description(value: str) -> str:
    text = re.sub(r"\s+", " ", sanitize_import_text(value).strip())
    text = strip_statement_header_noise(text)
    text = strip_statement_transaction_prefixes(text)
    text = strip_payment_processor_prefixes(text)
    text = re.sub(r"\bpos\b|\bpurchase\b|\bpayment\b|\bdebit\b|\bcredit\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text or sanitize_import_text(value)


def get_import_row_description_value(row: dict, header_mapping: dict[str, str]) -> str:
    description_key = header_mapping["description"]
    raw_description = row.get(description_key, "")
    if raw_description.strip():
        return raw_description

    category_key = header_mapping.get("category")
    if category_key and row.get(category_key, "").strip():
        return row[category_key]

    return raw_description


def csv_transaction_field_values(row: dict, header_mapping: dict[str, str]) -> list[str]:
    keys = [
        header_mapping.get("date"),
        header_mapping.get("description"),
        header_mapping.get("category"),
        header_mapping.get("amount"),
        header_mapping.get("debit"),
        header_mapping.get("credit"),
        header_mapping.get("type"),
    ]
    return [row.get(key, "").strip() for key in keys if key]


def is_structural_csv_row(row: dict, header_mapping: dict[str, str]) -> bool:
    values = csv_transaction_field_values(row, header_mapping)
    if not any(values):
        return True

    date_key = header_mapping["date"]
    amount_key = header_mapping.get("amount")
    description_key = header_mapping["description"]
    category_key = header_mapping.get("category")

    normalized_date_value = normalize_header(row.get(date_key, ""))
    normalized_amount_value = normalize_header(row.get(amount_key, "")) if amount_key else ""

    if normalized_date_value == csv_header_base_name(date_key):
        return True
    if amount_key and normalized_amount_value == csv_header_base_name(amount_key):
        return True

    has_money_value = any(
        row.get(key, "").strip()
        for key in (
            header_mapping.get("amount"),
            header_mapping.get("debit"),
            header_mapping.get("credit"),
        )
        if key
    )
    if not row.get(date_key, "").strip() and not has_money_value:
        return True

    if (
        not has_money_value
        and not row.get(description_key, "").strip()
        and not (category_key and row.get(category_key, "").strip())
    ):
        return True

    return False


def parse_import_csv_row_date(row: dict, header_mapping: dict[str, str]) -> date:
    return parse_date_with_context(
        row[header_mapping["date"]],
        row.get(CSV_MONTH_CONTEXT_KEY) or None,
    )


def csv_row_error_summary(error: Exception) -> str:
    message = str(error)
    if "Invalid date format" in message or isinstance(error, ValueError) and "day is out of range" in message:
        return "date is missing or uses an unsupported format"
    if "Could not infer transaction amount/type" in message:
        return "amount or transaction type is missing"
    if "could not convert string to float" in message:
        return "amount is missing or not a number"
    if "Invalid transaction type" in message:
        return "transaction type must be income, expense, credit, debit, deposit, or withdrawal"
    if "Description and category are required" in message:
        return "description or category is missing"
    return "row could not be parsed"


def build_invalid_csv_row_detail(row: dict, fallback_row_number: int, error: Exception) -> str:
    try:
        row_number = int(row.get(CSV_ROW_NUMBER_KEY, fallback_row_number))
    except (TypeError, ValueError):
        row_number = fallback_row_number
    return f"CSV row {row_number}: {csv_row_error_summary(error)}."


def normalize_repeating_description(value: str) -> str:
    fingerprint = extract_merchant_fingerprint(value)
    if fingerprint:
        return fingerprint[0]

    normalized = normalize_description(value).lower()
    normalized = re.sub(
        r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\b\d+\b", " ", normalized)
    normalized = " ".join(
        token
        for token in normalized.split()
        if token not in REPEATING_DESCRIPTION_STOPWORDS and len(token) >= 2
    )
    return normalized[:160]


def describe_repeating_pattern(
    *,
    description: str,
    tx_type: str,
    occurrences: int,
    average_amount: float,
    latest_date: date | None,
    cadence: str,
) -> str:
    label = "income" if tx_type == "income" else "expense"
    latest_text = f" Last seen on {latest_date.isoformat()}." if latest_date else ""
    return (
        f"Looks like a repeating {label}: {occurrences} similar occurrence"
        f"{'' if occurrences == 1 else 's'} already recorded, averaging ${average_amount:.2f}."
        f" Expected cadence: {cadence}.{latest_text}"
    )


def get_repeating_transaction_signal(
    db: Session,
    owner_id: int,
    account_id: int,
    description: str,
    tx_type: str,
    amount: float,
    tx_date: date,
) -> dict | None:
    normalized_description = normalize_repeating_description(description)
    if len(normalized_description) < 3:
        return None

    lowered_description = description.lower()
    candidate_types = [tx_type]
    if tx_type == "expense" and any(
        keyword in lowered_description
        for keyword in ("payroll", "salary", "direct deposit", "paycheque", "paycheck")
    ):
        candidate_types.append("income")

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.owner_id == owner_id,
            Transaction.account_id == account_id,
            Transaction.type.in_(candidate_types),
            Transaction.date < tx_date,
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    matches = [
        transaction
        for transaction in candidates
        if normalize_repeating_description(transaction.description) == normalized_description
    ]
    if not matches:
        return None

    detected_type = matches[-1].type

    amounts = [float(item.amount) for item in matches] + [float(amount)]
    average_amount = sum(amounts) / len(amounts)
    amount_variation = max(amounts) - min(amounts)
    variation_ratio = amount_variation / average_amount if average_amount > 0 else 0.0
    if variation_ratio > 0.45 and amount_variation > 25:
        return None

    previous_dates = [item.date for item in matches]
    latest_date = previous_dates[-1] if previous_dates else None
    intervals = [
        (previous_dates[index] - previous_dates[index - 1]).days
        for index in range(1, len(previous_dates))
    ]
    if latest_date:
        intervals.append((tx_date - latest_date).days)

    average_interval = sum(intervals) / len(intervals) if intervals else None
    cadence = "monthly"
    if average_interval is not None:
        if average_interval <= 10:
            cadence = "frequent"
        elif average_interval <= 20:
            cadence = "biweekly"
        elif average_interval <= 45:
            cadence = "monthly"
        elif average_interval <= 75:
            cadence = "every couple of months"
        else:
            cadence = "occasional"

    occurrence_count = len(matches) + 1
    confidence = min(
        0.96,
        0.62
        + 0.08 * min(occurrence_count, 4)
        + (0.1 if variation_ratio <= 0.15 else 0.0)
        + (0.08 if cadence in {"monthly", "biweekly"} else 0.0),
    )

    return {
        "is_repeating_pattern": True,
        "repeating_pattern_type": detected_type,
        "repeating_pattern_reason": describe_repeating_pattern(
            description=description,
            tx_type=detected_type,
            occurrences=len(matches),
            average_amount=average_amount,
            latest_date=latest_date,
            cadence=cadence,
        ),
        "repeating_pattern_occurrences": occurrence_count,
        "repeating_pattern_average_amount": round(average_amount, 2),
        "repeating_pattern_cadence": cadence,
        "repeating_pattern_confidence": round(confidence, 2),
    }


def learnable_category_from_merchant_profile(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    amount: float | None = None,
) -> MerchantCategoryProfile | None:
    if not merchant_profile_table_available(db):
        return None

    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return None

    merchant_key, _ = fingerprint
    if not is_valid_merchant_learning_key(merchant_key):
        return None

    candidate_query = (
        db.query(MerchantCategoryProfile)
        .filter(
            MerchantCategoryProfile.owner_id == owner_id,
            MerchantCategoryProfile.transaction_type == tx_type,
        )
    )

    if merchant_key_requires_amount_guard(merchant_key):
        candidate_profiles = (
            candidate_query.filter(
                or_(
                    MerchantCategoryProfile.merchant_key == merchant_key,
                    MerchantCategoryProfile.merchant_key.like(
                        f"{merchant_key}{AMOUNT_PROFILE_SEPARATOR}%"
                    ),
                )
            )
            .all()
        )
        candidate_profiles = [
            profile
            for profile in candidate_profiles
            if merchant_profile_amount_matches(profile, amount)
        ]
    else:
        candidate_profiles = (
            candidate_query.filter(MerchantCategoryProfile.merchant_key == merchant_key)
            .all()
        )

    if not candidate_profiles:
        return None

    return sorted(
        candidate_profiles,
        key=lambda profile: (
            merchant_profile_amount_matches(profile, amount),
            int(profile.confirmation_count or 0),
            float(profile.confidence or 0),
            (profile.updated_at or profile.created_at or datetime.min),
        ),
        reverse=True,
    )[0]


def category_memory_amount_matches(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    category: str,
    amount: float | None = None,
) -> bool:
    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return True

    merchant_key, _ = fingerprint
    if not merchant_key_requires_amount_guard(merchant_key):
        return True

    if not merchant_profile_table_available(db):
        return False

    normalized_category = normalize_category_name(category)
    profiles = (
        db.query(MerchantCategoryProfile)
        .filter(
            MerchantCategoryProfile.owner_id == owner_id,
            MerchantCategoryProfile.transaction_type == tx_type,
            MerchantCategoryProfile.category == normalized_category,
            or_(
                MerchantCategoryProfile.merchant_key == merchant_key,
                MerchantCategoryProfile.merchant_key.like(
                    f"{merchant_key}{AMOUNT_PROFILE_SEPARATOR}%"
                ),
            ),
        )
        .all()
    )

    return any(merchant_profile_amount_matches(profile, amount) for profile in profiles)


def learnable_category_from_memory(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    amount: float | None = None,
) -> tuple[str, str] | None:
    normalized_description = normalize_category_signal_text(description)
    raw_description = description.lower()

    memories = (
        db.query(CategoryMemory)
        .filter(
            CategoryMemory.owner_id == owner_id,
            CategoryMemory.transaction_type == tx_type,
        )
        .all()
    )

    best_match = None
    for item in memories:
        keyword = item.keyword.lower().strip()
        if keyword in CATEGORY_MEMORY_STOPWORDS:
            continue
        if keyword and keyword_matches_description(keyword, normalized_description, raw_description):
            normalized_category = normalize_category_name(item.category)
            if not category_memory_amount_matches(
                db=db,
                owner_id=owner_id,
                description=description,
                tx_type=tx_type,
                category=normalized_category,
                amount=amount,
            ):
                continue
            if best_match is None or len(keyword) > len(best_match[0]):
                best_match = (keyword, normalized_category)

    if not best_match:
        return None

    return normalize_category_name(best_match[1]), best_match[0]


def category_learning_event_amount_matches(
    event: CategoryLearningEvent,
    merchant_key: str,
    amount: float | None = None,
) -> bool:
    if not merchant_key_requires_amount_guard(merchant_key):
        return True

    candidate_bucket = learned_amount_bucket(amount)
    if not event.amount_bucket or not candidate_bucket:
        return False

    try:
        learned_bucket = float(event.amount_bucket)
        current_bucket = float(candidate_bucket)
    except (TypeError, ValueError):
        return event.amount_bucket == candidate_bucket

    tolerance = max(5.0, min(50.0, learned_bucket * 0.25))
    return abs(learned_bucket - current_bucket) <= tolerance


def learnable_category_from_learning_events(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    amount: float | None = None,
) -> CategoryDecision | None:
    """Use durable user-confirmed learning events when profile/memory rows are absent.

    Merchant profiles and keyword memory stay faster and stronger. This function
    is a safety net for historical corrections and bulk learning events, with
    enough confirmation required to avoid teaching the app from one noisy click.
    """

    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return None

    merchant_key, _ = fingerprint
    events = (
        db.query(CategoryLearningEvent)
        .filter(
            CategoryLearningEvent.owner_id == owner_id,
            CategoryLearningEvent.merchant_key == merchant_key,
            CategoryLearningEvent.transaction_type == tx_type,
        )
        .order_by(CategoryLearningEvent.created_at.desc(), CategoryLearningEvent.id.desc())
        .limit(40)
        .all()
    )
    if not events:
        return None

    category_weights: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    category_latest_ids: dict[str, int] = {}

    for event in events:
        category = normalize_category_name(event.category)
        if not should_store_category_memory(category):
            continue
        if not category_learning_event_amount_matches(event, merchant_key, amount):
            continue

        confidence = max(0.0, min(1.0, float(event.confidence or 0.0)))
        affected_count = max(1, int(event.affected_count or 1))
        if confidence < 0.7 and affected_count < 2:
            continue

        category_weights[category] += affected_count
        category_counts[category] += 1
        category_latest_ids[category] = max(category_latest_ids.get(category, 0), int(event.id or 0))

    if not category_weights:
        return None

    best_category, best_weight = max(
        category_weights.items(),
        key=lambda item: (
            item[1],
            category_counts[item[0]],
            category_latest_ids.get(item[0], 0),
        ),
    )
    total_weight = sum(category_weights.values())
    best_count = category_counts[best_category]

    if best_weight < 2 and best_count < 2:
        return None
    if total_weight > best_weight and best_weight / total_weight < 0.6:
        return None

    confidence = min(
        0.96,
        0.76
        + 0.04 * min(best_weight, 5)
        + 0.02 * min(best_count, 4)
        + (0.04 if best_weight == total_weight else 0.0),
    )

    return CategoryDecision(
        category=best_category,
        confidence=round(confidence, 2),
        matched_keyword=merchant_key,
        reason=(
            "Matched your confirmed category learning history for this merchant "
            f"({best_weight} saved signal{'' if best_weight == 1 else 's'})."
        ),
        source="learning_event",
    )


def learnable_category_from_community_profiles(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    amount: float | None = None,
) -> CategoryDecision | None:
    """Use anonymized merchant consensus when personal memory is unavailable.

    This reads only learned merchant profile rows, not raw statement files or
    full transaction histories. A single user cannot train the global behavior:
    at least two other owners must agree on the same category.
    """

    if tx_type != "expense" or not merchant_profile_table_available(db):
        return None

    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return None

    merchant_key, _ = fingerprint
    if not merchant_key_requires_amount_guard(merchant_key):
        cached = get_cached_community_profile_decision(db, merchant_key, tx_type)
        if cached:
            return cached

    profile_query = (
        db.query(MerchantCategoryProfile)
        .filter(
            MerchantCategoryProfile.owner_id != owner_id,
            MerchantCategoryProfile.transaction_type == tx_type,
        )
    )

    if merchant_key_requires_amount_guard(merchant_key):
        profiles = (
            profile_query.filter(
                or_(
                    MerchantCategoryProfile.merchant_key == merchant_key,
                    MerchantCategoryProfile.merchant_key.like(
                        f"{merchant_key}{AMOUNT_PROFILE_SEPARATOR}%"
                    ),
                )
            )
            .all()
        )
        profiles = [
            profile
            for profile in profiles
            if merchant_profile_base_key(profile.merchant_key) == merchant_key
            and merchant_profile_amount_matches(profile, amount)
            and user_allows_community_learning(db, profile.owner_id)
        ]
    else:
        profiles = (
            profile_query.filter(MerchantCategoryProfile.merchant_key == merchant_key)
            .all()
        )
        profiles = [
            profile
            for profile in profiles
            if user_allows_community_learning(db, profile.owner_id)
        ]

    decision = build_community_profile_decision(merchant_key=merchant_key, profiles=profiles)
    if decision and not merchant_key_requires_amount_guard(merchant_key):
        save_community_profile_decision(db, merchant_key, tx_type, decision)

    return decision


def protected_income_category_decision(description: str, tx_type: str) -> CategoryDecision | None:
    """Apply hard safety rules before user memory for cashflow-neutral income.

    A user may teach SQDC or Orange Mart as a personal category, but bank
    funding language like e-Transfer received should not be learned as earned
    income just because old imports created stale memory rows.
    """

    if tx_type != "income":
        return None

    lowered = normalize_category_signal_text(description)
    raw_lowered = description.lower()

    for keyword in CATEGORY_RULES["salary"]:
        if keyword_matches_description(keyword, lowered, raw_lowered):
            return CategoryDecision(
                category="salary",
                confidence=0.94,
                matched_keyword=keyword,
                reason="Matched an income rule in the transaction description.",
                source="rule",
            )

    for keyword in CATEGORY_RULES["refund"]:
        if keyword_matches_description(keyword, lowered, raw_lowered):
            return CategoryDecision(
                category="refund",
                confidence=0.91,
                matched_keyword=keyword,
                reason="Matched a refund or statement-credit rule in the transaction description.",
                source="rule",
            )

    for keyword in CATEGORY_RULES["transfer"]:
        if keyword_matches_description(keyword, lowered, raw_lowered):
            return CategoryDecision(
                category="transfer",
                confidence=0.93,
                matched_keyword=keyword,
                reason="Matched a transfer/funding rule before learned memory, so this is not treated as earned income.",
                source="protected_rule",
            )

    return None


def categorize_transaction_details(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    amount: float | None = None,
) -> CategoryDecision:
    protected_decision = protected_income_category_decision(description, tx_type)
    if protected_decision:
        return protected_decision

    merchant_profile = learnable_category_from_merchant_profile(
        db,
        owner_id,
        description,
        tx_type,
        amount,
    )
    if merchant_profile:
        matched_merchant = merchant_profile_base_key(merchant_profile.merchant_key)
        return CategoryDecision(
            category=normalize_category_name(merchant_profile.category),
            confidence=float(merchant_profile.confidence or merchant_profile_confidence(1)),
            matched_keyword=matched_merchant,
            reason=(
                "Matched learned category memory from your learned merchant profile "
                "and previous confirmed categories "
                f"({merchant_profile.confirmation_count} confirmation"
                f"{'' if merchant_profile.confirmation_count == 1 else 's'})."
            ),
            source="merchant_profile",
        )

    memory_match = learnable_category_from_memory(db, owner_id, description, tx_type, amount)
    if memory_match:
        category, matched_keyword = memory_match
        return CategoryDecision(
            category=category,
            confidence=0.98,
            matched_keyword=matched_keyword,
            reason="Matched learned category memory from your previous confirmed edits or imports.",
            source="memory",
        )

    learning_event_decision = learnable_category_from_learning_events(
        db,
        owner_id,
        description,
        tx_type,
        amount,
    )
    if learning_event_decision:
        return learning_event_decision

    lowered = normalize_category_signal_text(description)
    raw_lowered = description.lower()

    if tx_type == "income":
        for keyword in CATEGORY_RULES["salary"]:
            if keyword_matches_description(keyword, lowered, raw_lowered):
                return CategoryDecision(
                    category="salary",
                    confidence=0.94,
                    matched_keyword=keyword,
                    reason="Matched an income rule in the transaction description.",
                    source="rule",
                )
        for keyword in CATEGORY_RULES["refund"]:
            if keyword_matches_description(keyword, lowered, raw_lowered):
                return CategoryDecision(
                    category="refund",
                    confidence=0.91,
                    matched_keyword=keyword,
                    reason="Matched a refund or statement-credit rule in the transaction description.",
                    source="rule",
                )
        for keyword in CATEGORY_RULES["transfer"]:
            if keyword_matches_description(keyword, lowered, raw_lowered):
                return CategoryDecision(
                    category="transfer",
                    confidence=0.91,
                    matched_keyword=keyword,
                    reason="Matched a transfer/funding rule, so this is not treated as earned income.",
                    source="rule",
                )
        for keyword in ("interest",):
            if keyword_matches_description(keyword, lowered, raw_lowered):
                return CategoryDecision(
                    category="income",
                    confidence=0.86,
                    matched_keyword=keyword,
                    reason="Matched a general income/deposit rule in the transaction description.",
                    source="rule",
                )
        if "refund" in lowered or "refund" in raw_lowered:
            return CategoryDecision(
                category="refund",
                confidence=0.9,
                matched_keyword="refund",
                reason="Matched a refund keyword in the transaction description.",
                source="rule",
            )
        return CategoryDecision(
            category="income",
            confidence=0.62,
            matched_keyword=None,
            reason="Defaulted to income because the transaction type is income and no stronger rule matched.",
            source="fallback",
        )

    priority_expense_rules = (
        ("subscriptions", ("doordashdashpass",)),
        ("restaurant", ("ubereats", "uber eats", "doordash", "skip the dishes")),
    )
    for category, keywords in priority_expense_rules:
        for keyword in keywords:
            if keyword_matches_description(keyword, lowered, raw_lowered):
                return CategoryDecision(
                    category=normalize_category_name(category),
                    confidence=0.9,
                    matched_keyword=keyword,
                    reason="Matched a high-priority merchant rule before generic keyword matching.",
                    source="rule",
                )

    merchant_override = match_merchant_category_override(description)
    if merchant_override:
        category, confidence, matched_phrase = merchant_override
        return CategoryDecision(
            category=normalize_category_name(category),
            confidence=confidence,
            matched_keyword=matched_phrase,
            reason=(
                "Matched a verified merchant override for a known business whose name can be "
                "misclassified by generic similarity rules."
            ),
            source="merchant_override",
        )

    for category, keywords in CATEGORY_RULES.items():
        if category == "salary":
            continue
        for keyword in keywords:
            if keyword_matches_description(keyword, lowered, raw_lowered):
                return CategoryDecision(
                    category=normalize_category_name(category),
                    confidence=0.88,
                    matched_keyword=keyword,
                    reason="Matched a normalized merchant/category rule in the transaction description.",
                    source="rule",
                )

    community_profile = learnable_category_from_community_profiles(
        db,
        owner_id,
        description,
        tx_type,
        amount,
    )
    if community_profile:
        return community_profile

    merchant_enrichment = enrich_merchant_category(db, description, tx_type)
    if merchant_enrichment:
        return CategoryDecision(
            category=normalize_category_name(merchant_enrichment.category),
            confidence=merchant_enrichment.confidence,
            matched_keyword=merchant_enrichment.matched_keyword,
            reason=merchant_enrichment.reason,
            source=merchant_enrichment.source,
        )

    return CategoryDecision(
        category="other",
        confidence=0.24,
        matched_keyword=None,
        reason="No learned memory or built-in category rule matched this description yet.",
        source="fallback",
    )


def categorize_transaction(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    amount: float | None = None,
) -> str:
    return categorize_transaction_details(
        db=db,
        owner_id=owner_id,
        description=description,
        tx_type=tx_type,
        amount=amount,
    ).category


def resolve_import_category_for_transaction(
    db: Session,
    owner_id: int,
    description: str,
    tx_type: str,
    category: str | None,
    amount: float | None = None,
) -> str:
    normalized_category = normalize_category_name(category)
    if tx_type == "expense" and normalized_category in EXPENSE_INCOMPATIBLE_CATEGORIES:
        decision = categorize_transaction_details(
            db=db,
            owner_id=owner_id,
            description=description,
            tx_type=tx_type,
            amount=amount,
        )
        if decision.category not in EXPENSE_INCOMPATIBLE_CATEGORIES:
            return decision.category
        return "other"

    return normalized_category


def build_duplicate_key(
    owner_id: int,
    account_id: int,
    tx_date: date,
    description: str,
    amount: float,
    tx_type: str,
    category: str,
) -> tuple:
    return (
        owner_id,
        account_id,
        tx_date.isoformat(),
        description.strip().lower(),
        round(amount, 2),
        tx_type.strip().lower(),
        normalize_category_name(category),
    )


def build_statement_match_key(
    owner_id: int,
    account_id: int,
    tx_date: date,
    amount: float,
    tx_type: str,
) -> tuple:
    return (
        owner_id,
        account_id,
        tx_date.isoformat(),
        round(abs(float(amount)), 2),
        tx_type.strip().lower(),
    )


def get_existing_duplicate_keys(db: Session, owner_id: int, account_id: int | None = None) -> set[tuple]:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    existing_transactions = query.all()

    return {
        build_duplicate_key(
            owner_id=transaction.owner_id,
            account_id=transaction.account_id or 0,
            tx_date=transaction.date,
            description=transaction.description,
            amount=transaction.amount,
            tx_type=transaction.type,
            category=transaction.category,
        )
        for transaction in existing_transactions
    }


def get_existing_statement_match_map(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> dict[tuple, Transaction]:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    existing_transactions = query.all()
    match_map: dict[tuple, Transaction] = {}
    for transaction in existing_transactions:
        if transaction.account_id is None:
            continue
        key = build_statement_match_key(
            owner_id=transaction.owner_id,
            account_id=transaction.account_id,
            tx_date=transaction.date,
            amount=transaction.amount,
            tx_type=transaction.type,
        )
        match_map.setdefault(key, transaction)

    return match_map


def find_likely_statement_match(
    db: Session,
    owner_id: int,
    account_id: int,
    tx_date: date,
    amount: float,
    tx_type: str,
) -> Transaction | None:
    """Find one safe near-date match for month-end statement reconciliation.

    Bank posted dates often drift 1-3 days from the day a user manually wrote a
    transaction. We only auto-match when there is exactly one same-account,
    same-type, same-amount candidate in the nearby date window.
    """

    window_start = tx_date - timedelta(days=STATEMENT_RECONCILIATION_DATE_WINDOW_DAYS)
    window_end = tx_date + timedelta(days=STATEMENT_RECONCILIATION_DATE_WINDOW_DAYS)
    target_amount = round(abs(float(amount)), 2)

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.owner_id == owner_id,
            Transaction.account_id == account_id,
            Transaction.type == tx_type,
            Transaction.date >= window_start,
            Transaction.date <= window_end,
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    amount_matches = [
        transaction
        for transaction in candidates
        if abs(round(abs(float(transaction.amount)), 2) - target_amount)
        <= STATEMENT_RECONCILIATION_AMOUNT_TOLERANCE
    ]

    if len(amount_matches) != 1:
        return None

    return amount_matches[0]


def describe_likely_statement_match(statement_date: date, transaction: Transaction) -> str:
    days_apart = abs((statement_date - transaction.date).days)
    day_text = "same day" if days_apart == 0 else f"{days_apart} day{'' if days_apart == 1 else 's'} apart"
    return f"Likely already written as {transaction.description} ({day_text}, same amount)."


def import_transactions_from_csv(
    db: Session,
    owner_id: int,
    account_id: int,
    file_bytes: bytes,
) -> dict:
    text = decode_file_bytes(file_bytes)
    rows, header_mapping = read_csv_rows(text)

    existing_keys = get_existing_duplicate_keys(db, owner_id, account_id=account_id)
    seen_in_file = set()

    to_insert: list[Transaction] = []
    imported = 0
    duplicates_skipped = 0
    invalid_rows_skipped = 0
    invalid_row_details: list[str] = []

    for fallback_row_number, row in enumerate(rows, start=2):
        if is_structural_csv_row(row, header_mapping):
            continue

        try:
            tx_date = parse_import_csv_row_date(row, header_mapping)
            raw_description = get_import_row_description_value(row, header_mapping)
            description = normalize_description(raw_description)

            tx_type, amount = infer_type_and_amount(row, header_mapping)

            if header_mapping.get("category") and row.get(header_mapping["category"]):
                supplied_category = normalize_category_name(row[header_mapping["category"]])
                category = resolve_import_category_for_transaction(
                    db=db,
                    owner_id=owner_id,
                    description=description,
                    tx_type=tx_type,
                    category=supplied_category,
                    amount=amount,
                )
                if category != supplied_category:
                    category_confidence = 0.88
                    category_source = "rule"
                    category_reason = (
                        "Corrected a statement category that conflicted with the transaction direction."
                    )
                else:
                    category_confidence = 1.0
                    category_source = "statement"
                    category_reason = "Used the category supplied by the statement file."
            else:
                category_decision = categorize_transaction_details(
                    db=db,
                    owner_id=owner_id,
                    description=description,
                    tx_type=tx_type,
                    amount=amount,
                )
                category = category_decision.category
                category_confidence = category_decision.confidence
                category_source = category_decision.source
                category_reason = category_decision.reason

            if not description or not category:
                raise ValueError("Description and category are required.")

            duplicate_key = build_duplicate_key(
                owner_id=owner_id,
                account_id=account_id,
                tx_date=tx_date,
                description=description,
                amount=amount,
                tx_type=tx_type,
                category=category,
            )

            if duplicate_key in existing_keys or duplicate_key in seen_in_file:
                duplicates_skipped += 1
                continue

            seen_in_file.add(duplicate_key)

            to_insert.append(
                Transaction(
                    amount=amount,
                    category=category,
                    category_confidence=category_confidence,
                    category_source=category_source,
                    category_reason=category_reason,
                    description=description,
                    date=tx_date,
                    type=tx_type,
                    entry_source="csv_import",
                    import_file_type="csv_statement",
                    imported_at=datetime.now(timezone.utc),
                    owner_id=owner_id,
                    account_id=account_id,
                )
            )
            save_category_memory(
                db=db,
                owner_id=owner_id,
                description=description,
                category=category,
                tx_type=tx_type,
                amount=amount,
            )
            imported += 1

        except Exception as exc:
            invalid_rows_skipped += 1
            if len(invalid_row_details) < 10:
                invalid_row_details.append(
                    build_invalid_csv_row_detail(row, fallback_row_number, exc)
                )

    if to_insert:
        db.bulk_save_objects(to_insert)
        db.commit()

    return {
        "message": "Statement import completed",
        "imported": imported,
        "duplicates_skipped": duplicates_skipped,
        "invalid_rows_skipped": invalid_rows_skipped,
        "invalid_row_details": invalid_row_details,
    }


def parse_csv_statement_preview(
    db: Session,
    owner_id: int,
    file_bytes: bytes,
) -> dict:
    text = decode_file_bytes(file_bytes)
    rows, header_mapping = read_csv_rows(text)

    preview_rows: list[StatementPreviewRow] = []
    invalid_rows_skipped = 0
    invalid_row_details: list[str] = []

    for fallback_row_number, row in enumerate(rows, start=2):
        if is_structural_csv_row(row, header_mapping):
            continue

        try:
            row_number = int(row.get(CSV_ROW_NUMBER_KEY, fallback_row_number))
            tx_date = parse_import_csv_row_date(row, header_mapping)
            raw_description = get_import_row_description_value(row, header_mapping)
            description = normalize_description(raw_description)
            tx_type, amount = infer_type_and_amount(row, header_mapping)

            if header_mapping.get("category") and row.get(header_mapping["category"]):
                supplied_category = normalize_category_name(row[header_mapping["category"]])
                category = resolve_import_category_for_transaction(
                    db=db,
                    owner_id=owner_id,
                    description=description,
                    tx_type=tx_type,
                    category=supplied_category,
                    amount=amount,
                )
                if category != supplied_category:
                    category_confidence = 0.88
                    category_source = "rule"
                    category_reason = (
                        "Corrected a statement category that conflicted with the transaction direction."
                    )
                else:
                    category_confidence = 1.0
                    category_source = "statement"
                    category_reason = "Used the category supplied by the statement file."
                category_review_required = False
                category_review_reason = None
            else:
                decision = categorize_transaction_details(
                    db=db,
                    owner_id=owner_id,
                    description=description,
                    tx_type=tx_type,
                    amount=amount,
                )
                category = decision.category
                category_confidence = decision.confidence
                category_source = decision.source
                category_reason = decision.reason
                category_review_required, category_review_reason = build_category_review_metadata(decision)

            if not description or not category:
                raise ValueError("Description and category are required.")

            preview_rows.append(
                StatementPreviewRow(
                    date=tx_date.isoformat(),
                    description=description,
                    amount=amount,
                    type=tx_type,
                    category=category,
                    source_line=f"CSV row {row_number}: {raw_description}",
                    confidence=0.94,
                    review_reason=None,
                    category_confidence=category_confidence,
                    category_source=category_source,
                    category_reason=category_reason,
                    category_review_required=category_review_required,
                    category_review_reason=category_review_reason,
                )
            )
        except Exception as exc:
            invalid_rows_skipped += 1
            if len(invalid_row_details) < 10:
                invalid_row_details.append(
                    build_invalid_csv_row_detail(row, fallback_row_number, exc)
                )

    if not preview_rows:
        detail = "No transaction rows were recognized in this CSV statement."
        if invalid_rows_skipped:
            examples = " ".join(invalid_row_details[:3])
            detail = (
                f"{detail} Skipped {invalid_rows_skipped} invalid row"
                f"{'' if invalid_rows_skipped == 1 else 's'}."
                f"{f' Examples: {examples}' if examples else ''}"
            )
        raise ValueError(detail)

    return {
        "preview_rows": preview_rows,
        "invalid_rows_skipped": invalid_rows_skipped,
        "invalid_row_details": invalid_row_details,
    }


def build_transaction_scope_query(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
):
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    return query


def apply_transaction_filters(
    query,
    *,
    transaction_type: str | None = None,
    month: str | None = None,
    category: str | None = None,
    entry_source: str | None = None,
    description: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    amount_min_exclusive: bool = False,
):
    if transaction_type in {"income", "expense"}:
        query = query.filter(Transaction.type == transaction_type)

    month_start, month_end = month_date_bounds(month)
    if month_start and month_end:
        query = query.filter(Transaction.date >= month_start, Transaction.date < month_end)

    if category:
        category_values = get_category_filter_values(category)
        query = query.filter(func.lower(Transaction.category).in_(tuple(category_values)))

    if entry_source:
        normalized_source = str(entry_source).strip().lower()
        if normalized_source:
            query = query.filter(func.lower(Transaction.entry_source) == normalized_source)

    if description:
        normalized_description = re.sub(r"\s+", " ", description.strip().lower())
        if normalized_description:
            query = query.filter(func.lower(Transaction.description).like(f"%{normalized_description}%"))

    absolute_amount = func.abs(Transaction.amount)
    if amount_min is not None:
        if amount_min_exclusive:
            query = query.filter(absolute_amount > amount_min)
        else:
            query = query.filter(absolute_amount >= amount_min)
    if amount_max is not None:
        query = query.filter(absolute_amount < amount_max)

    return query


def transaction_month_bucket_expression(db: Session):
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    if getattr(dialect, "name", None) == "sqlite":
        return func.strftime("%Y-%m", Transaction.date)
    return func.to_char(Transaction.date, "YYYY-MM")


def get_transaction_filter_options(db: Session, owner_id: int, account_id: int | None = None) -> dict:
    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    month_expr = transaction_month_bucket_expression(db)
    month_rows = (
        scope_query.with_entities(month_expr.label("month"))
        .filter(Transaction.date.is_not(None))
        .distinct()
        .order_by(month_expr.desc())
        .all()
    )
    category_rows = scope_query.with_entities(Transaction.category).distinct().all()

    months = [str(row[0]) for row in month_rows if row[0]]
    categories = sorted(
        {
            normalize_category_name(row[0])
            for row in category_rows
            if row[0]
        }
    )

    return {
        "available_months": months,
        "available_categories": categories,
    }


def get_transaction_source_summary(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> dict:
    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    source_expression = func.coalesce(Transaction.entry_source, "manual")
    income_amount = case((Transaction.type == "income", func.abs(Transaction.amount)), else_=0.0)
    expense_amount = case((Transaction.type == "expense", func.abs(Transaction.amount)), else_=0.0)
    income_count = case((Transaction.type == "income", 1), else_=0)
    expense_count = case((Transaction.type == "expense", 1), else_=0)

    rows = (
        scope_query.with_entities(
            source_expression.label("entry_source"),
            func.count(Transaction.id).label("transaction_count"),
            func.coalesce(func.sum(income_count), 0).label("income_count"),
            func.coalesce(func.sum(expense_count), 0).label("expense_count"),
            func.coalesce(func.sum(income_amount), 0.0).label("total_income"),
            func.coalesce(func.sum(expense_amount), 0.0).label("total_expenses"),
            func.count(func.distinct(Transaction.import_file_name)).label("imported_file_count"),
            func.max(Transaction.date).label("latest_transaction_date"),
            func.max(Transaction.imported_at).label("latest_imported_at"),
        )
        .group_by(source_expression)
        .all()
    )

    source_order = {
        "manual": 0,
        "manual_import_review": 1,
        "pdf_import": 2,
        "csv_import": 3,
        "receipt_import": 4,
        "statement_import": 5,
        "seed": 6,
    }
    sources: list[dict] = []
    total_transactions = 0
    manual_count = 0
    imported_count = 0
    seed_count = 0
    total_income = 0.0
    total_expenses = 0.0
    imported_file_count = 0
    latest_imported_at = None

    for row in rows:
        entry_source = str(row.entry_source or "manual").strip().lower() or "manual"
        transaction_count = int(row.transaction_count or 0)
        row_income = round(float(row.total_income or 0.0), 2)
        row_expenses = round(float(row.total_expenses or 0.0), 2)
        row_file_count = int(row.imported_file_count or 0)
        row_latest_imported_at = row.latest_imported_at

        total_transactions += transaction_count
        total_income += row_income
        total_expenses += row_expenses
        imported_file_count += row_file_count

        if entry_source == "manual":
            manual_count += transaction_count
        elif entry_source == "seed":
            seed_count += transaction_count
        elif entry_source in IMPORTED_TRANSACTION_SOURCES:
            imported_count += transaction_count

        if row_latest_imported_at and (
            latest_imported_at is None or row_latest_imported_at > latest_imported_at
        ):
            latest_imported_at = row_latest_imported_at

        sources.append(
            {
                "entry_source": entry_source,
                "label": TRANSACTION_SOURCE_LABELS.get(entry_source, entry_source.replace("_", " ").title()),
                "transaction_count": transaction_count,
                "income_count": int(row.income_count or 0),
                "expense_count": int(row.expense_count or 0),
                "total_income": row_income,
                "total_expenses": row_expenses,
                "balance": round(row_income - row_expenses, 2),
                "imported_file_count": row_file_count,
                "latest_transaction_date": row.latest_transaction_date,
                "latest_imported_at": row_latest_imported_at,
            }
        )

    sources.sort(
        key=lambda item: (
            source_order.get(item["entry_source"], 99),
            -int(item["transaction_count"]),
            item["entry_source"],
        )
    )

    return {
        "total_transactions": total_transactions,
        "manual_count": manual_count,
        "imported_count": imported_count,
        "seed_count": seed_count,
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expenses, 2),
        "balance": round(total_income - total_expenses, 2),
        "imported_file_count": imported_file_count,
        "latest_imported_at": latest_imported_at,
        "sources": sources,
    }


def get_fast_transaction_quality_summary(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> dict:
    source_summary = get_transaction_source_summary(db, owner_id, account_id=account_id)
    transaction_count = int(source_summary["total_transactions"])
    manual_count = int(source_summary["manual_count"])
    imported_count = int(source_summary["imported_count"])

    if transaction_count == 0:
        return {
            "transaction_count": 0,
            "manual_count": 0,
            "imported_count": 0,
            "uncategorized_count": 0,
            "category_review_count": 0,
            "learning_candidate_count": 0,
            "suspicious_amount_count": 0,
            "likely_duplicate_count": 0,
            "quality_level": "empty",
            "quality_score": 0.0,
            "message": "No transaction data yet. Start with daily entries or import a statement.",
            "actions": [
                {
                    "key": "start_tracking",
                    "label": "Add or import transactions",
                    "detail": "Add daily transactions or import a statement before analytics can become useful.",
                    "severity": "high",
                    "count": 0,
                }
            ],
            "source_summary": source_summary,
        }

    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    uncategorized_count = int(
        scope_query.filter(func.lower(Transaction.category).in_(tuple(UNCATEGORIZED_VALUES))).count()
    )
    learning_candidate_count = min(uncategorized_count, 50)

    actions: list[dict] = []
    if uncategorized_count:
        actions.append(
            {
                "key": "review_uncategorized",
                "label": "Review uncategorized transactions",
                "detail": "Reducing Other/uncategorized rows makes charts and budgets more trustworthy.",
                "severity": "medium",
                "count": uncategorized_count,
            }
        )
    if imported_count > 0 and manual_count == 0:
        actions.append(
            {
                "key": "add_manual_entries",
                "label": "Add daily written entries",
                "detail": "Manual entries let the app reconcile bank statements against what you remembered to write.",
                "severity": "info",
                "count": imported_count,
            }
        )

    uncategorized_share = uncategorized_count / transaction_count
    learning_penalty = min(0.12, learning_candidate_count * 0.015)
    score = 0.92
    score -= min(0.42, uncategorized_share * 0.55)
    score -= learning_penalty
    score = round(max(0.05, min(0.98, score)), 2)

    if score >= 0.82 and not actions:
        quality_level = "high"
        message = "Transaction data looks clean enough for reliable analytics and budget guidance."
    elif score >= 0.62:
        quality_level = "medium"
        message = "Transaction data is usable, but a few review items can improve accuracy."
    else:
        quality_level = "low"
        message = "Review transaction quality before trusting analytics, budgets, or simulator output."

    return {
        "transaction_count": transaction_count,
        "manual_count": manual_count,
        "imported_count": imported_count,
        "uncategorized_count": uncategorized_count,
        "category_review_count": 0,
        "learning_candidate_count": learning_candidate_count,
        "suspicious_amount_count": 0,
        "likely_duplicate_count": 0,
        "quality_level": quality_level,
        "quality_score": score,
        "message": message,
        "actions": actions,
        "source_summary": source_summary,
    }


def get_transaction_import_history(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    limit: int = 25,
) -> dict:
    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    import_query = scope_query.filter(
        or_(
            Transaction.entry_source.in_(tuple(IMPORTED_TRANSACTION_SOURCES)),
            Transaction.import_file_name.is_not(None),
        )
    )
    file_name_expression = func.coalesce(Transaction.import_file_name, "Unknown import")
    file_type_expression = func.coalesce(Transaction.import_file_type, "statement")
    source_expression = func.coalesce(Transaction.entry_source, "statement_import")
    income_amount = case((Transaction.type == "income", func.abs(Transaction.amount)), else_=0.0)
    expense_amount = case((Transaction.type == "expense", func.abs(Transaction.amount)), else_=0.0)
    income_count = case((Transaction.type == "income", 1), else_=0)
    expense_count = case((Transaction.type == "expense", 1), else_=0)

    rows = (
        import_query.with_entities(
            file_name_expression.label("import_file_name"),
            file_type_expression.label("import_file_type"),
            source_expression.label("entry_source"),
            Transaction.account_id.label("account_id"),
            func.count(Transaction.id).label("transaction_count"),
            func.coalesce(func.sum(income_count), 0).label("income_count"),
            func.coalesce(func.sum(expense_count), 0).label("expense_count"),
            func.coalesce(func.sum(income_amount), 0.0).label("total_income"),
            func.coalesce(func.sum(expense_amount), 0.0).label("total_expenses"),
            func.min(Transaction.date).label("first_transaction_date"),
            func.max(Transaction.date).label("latest_transaction_date"),
            func.min(Transaction.imported_at).label("first_imported_at"),
            func.max(Transaction.imported_at).label("latest_imported_at"),
        )
        .group_by(
            file_name_expression,
            file_type_expression,
            source_expression,
            Transaction.account_id,
        )
        .all()
    )

    items: list[dict] = []
    total_imported_transactions = 0
    total_income = 0.0
    total_expenses = 0.0
    latest_imported_at = None
    imported_file_names: set[str] = set()

    for row in rows:
        transaction_count = int(row.transaction_count or 0)
        row_income = round(float(row.total_income or 0.0), 2)
        row_expenses = round(float(row.total_expenses or 0.0), 2)
        import_file_name = str(row.import_file_name or "Unknown import")
        row_latest_imported_at = row.latest_imported_at

        total_imported_transactions += transaction_count
        total_income += row_income
        total_expenses += row_expenses
        if import_file_name and import_file_name != "Unknown import":
            imported_file_names.add(import_file_name.lower())
        if row_latest_imported_at and (
            latest_imported_at is None or row_latest_imported_at > latest_imported_at
        ):
            latest_imported_at = row_latest_imported_at

        items.append(
            {
                "import_file_name": import_file_name,
                "import_file_type": row.import_file_type,
                "entry_source": str(row.entry_source or "statement_import").strip().lower(),
                "account_id": row.account_id,
                "transaction_count": transaction_count,
                "income_count": int(row.income_count or 0),
                "expense_count": int(row.expense_count or 0),
                "total_income": row_income,
                "total_expenses": row_expenses,
                "balance": round(row_income - row_expenses, 2),
                "first_transaction_date": row.first_transaction_date,
                "latest_transaction_date": row.latest_transaction_date,
                "first_imported_at": row.first_imported_at,
                "latest_imported_at": row_latest_imported_at,
            }
        )

    items.sort(
        key=lambda item: (
            item["latest_imported_at"] is None,
            -(item["latest_imported_at"].timestamp() if item["latest_imported_at"] else 0),
            item["import_file_name"].lower(),
        )
    )
    limited_items = items[:limit]

    return {
        "import_batch_count": len(items),
        "imported_file_count": len(imported_file_names),
        "total_imported_transactions": total_imported_transactions,
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expenses, 2),
        "balance": round(total_income - total_expenses, 2),
        "latest_imported_at": latest_imported_at,
        "items": limited_items,
    }


def build_category_review_query(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
):
    query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    return query.filter(
        Transaction.entry_source.in_(tuple(IMPORTED_TRANSACTION_SOURCES)),
        or_(
            Transaction.category_confidence.is_(None),
            and_(
                Transaction.category_source.isnot(None),
                Transaction.category_confidence < CATEGORY_REVIEW_CONFIDENCE_THRESHOLD,
            ),
            func.lower(Transaction.category_source).in_(tuple(CATEGORY_REVIEW_REQUIRED_SOURCES)),
            func.lower(Transaction.category).in_(tuple(UNCATEGORIZED_VALUES)),
        ),
    )


def count_category_review_transactions(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> int:
    return build_category_review_query(db, owner_id, account_id=account_id).count()


def get_category_review_transactions(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    limit: int = 5,
) -> list[Transaction]:
    max_items = max(1, min(int(limit or 5), 25))
    return (
        build_category_review_query(db, owner_id, account_id=account_id)
        .order_by(
            Transaction.category_confidence.asc(),
            Transaction.date.desc(),
            Transaction.id.desc(),
        )
        .limit(max_items)
        .all()
    )


def category_review_reason(transaction: Transaction) -> str:
    normalized_category = normalize_category_name(transaction.category)
    confidence = float(transaction.category_confidence or 0.0)
    source = str(transaction.category_source or "").strip()

    if normalized_category in UNCATEGORIZED_VALUES:
        return "This imported row is still in Other/uncategorized, so analytics will be less precise until it is taught."
    if not source:
        return "This imported row was saved before category audit metadata existed, so it should be reviewed once."
    if confidence < CATEGORY_REVIEW_CONFIDENCE_THRESHOLD:
        return (
            f"This category came from {source} with {round(confidence * 100)}% confidence, "
            "which is below the automatic-trust threshold."
        )
    return "This imported category has incomplete review metadata and should be checked once."


def get_transaction_data_quality_report(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> dict:
    source_summary = get_transaction_source_summary(db, owner_id, account_id=account_id)
    transaction_count = int(source_summary["total_transactions"])
    manual_count = int(source_summary["manual_count"])
    imported_count = int(source_summary["imported_count"])

    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    uncategorized_count = (
        scope_query.filter(func.lower(Transaction.category).in_(tuple(UNCATEGORIZED_VALUES))).count()
    )
    learning_candidate_count = len(
        get_category_learning_candidates(
            db=db,
            owner_id=owner_id,
            account_id=account_id,
            limit=50,
        )
    )
    suspicious_amount_count = len(
        get_suspicious_amount_repair_candidates(
            db=db,
            owner_id=owner_id,
            account_id=account_id,
        )
    )
    likely_duplicate_count = count_likely_duplicate_transactions(
        db=db,
        owner_id=owner_id,
        account_id=account_id,
    )
    category_review_count = count_category_review_transactions(
        db=db,
        owner_id=owner_id,
        account_id=account_id,
    )

    actions: list[dict] = []
    if transaction_count == 0:
        actions.append(
            {
                "key": "start_tracking",
                "label": "Add or import transactions",
                "detail": "Add daily transactions or import a statement before analytics can become useful.",
                "severity": "high",
                "count": 0,
            }
        )
        return {
            "transaction_count": 0,
            "manual_count": 0,
            "imported_count": 0,
            "uncategorized_count": 0,
            "category_review_count": 0,
            "learning_candidate_count": 0,
            "suspicious_amount_count": 0,
            "likely_duplicate_count": 0,
            "quality_level": "empty",
            "quality_score": 0.0,
            "message": "No transaction data yet. Start with daily entries or import a statement.",
            "actions": actions,
            "source_summary": source_summary,
        }

    if suspicious_amount_count:
        actions.append(
            {
                "key": "repair_amounts",
                "label": "Review suspicious amounts",
                "detail": "Some amounts look like statement reference digits were merged into the real amount.",
                "severity": "high",
                "count": suspicious_amount_count,
            }
        )
    if category_review_count:
        actions.append(
            {
                "key": "review_category_confidence",
                "label": "Review uncertain categories",
                "detail": "Some imported rows were saved as Other or with low-confidence category metadata.",
                "severity": "medium",
                "count": category_review_count,
            }
        )
    if likely_duplicate_count:
        actions.append(
            {
                "key": "review_duplicates",
                "label": "Review likely duplicates",
                "detail": "Some transactions have the same date, amount, type, and description.",
                "severity": "medium",
                "count": likely_duplicate_count,
            }
        )
    if learning_candidate_count:
        actions.append(
            {
                "key": "teach_categories",
                "label": "Teach merchant categories",
                "detail": "Confirm merchant groups once so similar transactions use the same category.",
                "severity": "medium",
                "count": learning_candidate_count,
            }
        )
    if uncategorized_count:
        actions.append(
            {
                "key": "review_uncategorized",
                "label": "Review uncategorized transactions",
                "detail": "Reducing Other/uncategorized rows makes charts and budgets more trustworthy.",
                "severity": "medium",
                "count": uncategorized_count,
            }
        )
    if imported_count > 0 and manual_count == 0:
        actions.append(
            {
                "key": "add_manual_entries",
                "label": "Add daily written entries",
                "detail": "Manual entries let the app reconcile bank statements against what you remembered to write.",
                "severity": "info",
                "count": imported_count,
            }
        )

    uncategorized_share = uncategorized_count / transaction_count
    duplicate_share = likely_duplicate_count / transaction_count
    suspicious_share = suspicious_amount_count / transaction_count
    category_review_share = category_review_count / transaction_count
    learning_penalty = min(0.18, learning_candidate_count * 0.025)
    score = 0.92
    score -= min(0.42, uncategorized_share * 0.55)
    score -= min(0.25, suspicious_share * 1.2)
    score -= min(0.18, category_review_share * 0.7)
    score -= min(0.18, duplicate_share * 0.9)
    score -= learning_penalty
    score = round(max(0.05, min(0.98, score)), 2)

    if score >= 0.82 and not actions:
        quality_level = "high"
        message = "Transaction data looks clean enough for reliable analytics and budget guidance."
    elif score >= 0.62:
        quality_level = "medium"
        message = "Transaction data is usable, but a few review items can improve accuracy."
    else:
        quality_level = "low"
        message = "Review transaction quality before trusting analytics, budgets, or simulator output."

    return {
        "transaction_count": transaction_count,
        "manual_count": manual_count,
        "imported_count": imported_count,
        "uncategorized_count": uncategorized_count,
        "category_review_count": category_review_count,
        "learning_candidate_count": learning_candidate_count,
        "suspicious_amount_count": suspicious_amount_count,
        "likely_duplicate_count": likely_duplicate_count,
        "quality_level": quality_level,
        "quality_score": score,
        "message": message,
        "actions": actions,
        "source_summary": source_summary,
    }


def get_transaction_review_queue(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    limit: int = 5,
) -> dict:
    max_items = max(1, min(int(limit or 5), 25))
    quality_report = get_transaction_data_quality_report(
        db,
        owner_id,
        account_id=account_id,
    )
    amount_repair_candidates = get_suspicious_amount_repair_candidates(
        db=db,
        owner_id=owner_id,
        account_id=account_id,
    )
    category_learning_candidates = get_category_learning_candidates(
        db=db,
        owner_id=owner_id,
        account_id=account_id,
        limit=max_items,
    )
    category_review_candidates = get_category_review_transactions(
        db=db,
        owner_id=owner_id,
        account_id=account_id,
        limit=max_items,
    )
    duplicate_groups = get_likely_duplicate_transaction_groups(
        db=db,
        owner_id=owner_id,
        account_id=account_id,
        limit=max_items,
    )

    amount_repair_items = [
        {
            "transaction_id": item.transaction_id,
            "date": item.date,
            "description": item.description,
            "type": item.type,
            "category": item.category,
            "current_amount": item.current_amount,
            "suggested_amount": item.suggested_amount,
            "confidence": item.confidence,
            "reason": item.reason,
        }
        for item in amount_repair_candidates[:max_items]
    ]
    category_review_items = []
    for transaction in category_review_candidates[:max_items]:
        decision = categorize_transaction_details(
            db=db,
            owner_id=owner_id,
            description=transaction.description,
            tx_type=transaction.type,
            amount=transaction.amount,
        )
        fingerprint = extract_merchant_fingerprint(transaction.description)
        suggested_category = normalize_category_name(decision.category)
        current_category = normalize_category_name(transaction.category)
        category_review_items.append(
            {
                "transaction_id": transaction.id,
                "date": transaction.date,
                "description": transaction.description,
                "type": transaction.type,
                "category": transaction.category,
                "amount": transaction.amount,
                "account_id": transaction.account_id,
                "category_confidence": float(transaction.category_confidence or 0.0),
                "category_source": transaction.category_source,
                "category_reason": transaction.category_reason,
                "reason": category_review_reason(transaction),
                "merchant_key": fingerprint[0] if fingerprint else None,
                "suggested_category": suggested_category,
                "suggestion_confidence": round(float(decision.confidence or 0.0), 2),
                "suggestion_source": decision.source,
                "suggestion_reason": decision.reason,
                "apply_to_similar_recommended": bool(
                    fingerprint
                    and (
                        current_category in UNCATEGORIZED_VALUES
                        or suggested_category != current_category
                    )
                ),
            }
        )
    category_learning_items = [
        {
            "merchant_key": item.merchant_key,
            "display_name": item.display_name,
            "type": item.type,
            "transaction_count": item.transaction_count,
            "current_category": item.current_category,
            "suggested_category": item.suggested_category,
            "confidence": item.confidence,
            "total_amount": item.total_amount,
            "representative_amount": item.representative_amount,
            "amount_min": item.amount_min,
            "amount_max": item.amount_max,
            "example_descriptions": item.example_descriptions,
            "reason": item.reason,
            "review_required": item.review_required,
        }
        for item in category_learning_candidates[:max_items]
    ]
    duplicate_group_items = [
        {
            "transaction_ids": item.transaction_ids,
            "date": item.date,
            "description": item.description,
            "type": item.type,
            "category": item.category,
            "amount": item.amount,
            "account_id": item.account_id,
            "occurrence_count": item.occurrence_count,
            "reason": item.reason,
        }
        for item in duplicate_groups[:max_items]
    ]

    return {
        "quality_report": quality_report,
        "next_action": quality_report["actions"][0] if quality_report["actions"] else None,
        "amount_repair_count": len(amount_repair_candidates),
        "amount_repairs": amount_repair_items,
        "category_review_count": len(category_review_candidates),
        "category_review_candidates": category_review_items,
        "category_learning_count": len(category_learning_candidates),
        "category_learning_candidates": category_learning_items,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_groups": duplicate_group_items,
    }


def get_transactions_page_for_user(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    transaction_type: str | None = None,
    month: str | None = None,
    category: str | None = None,
    entry_source: str | None = None,
    description: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    amount_min_exclusive: bool = False,
    page: int = 1,
    page_size: int = 12,
) -> dict:
    safe_page = max(1, int(page or 1))
    safe_page_size = min(MAX_TRANSACTION_PAGE_SIZE, max(1, int(page_size or 12)))

    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    scope_total = scope_query.count()
    filtered_query = apply_transaction_filters(
        scope_query,
        transaction_type=transaction_type,
        month=month,
        category=category,
        entry_source=entry_source,
        description=description,
        amount_min=amount_min,
        amount_max=amount_max,
        amount_min_exclusive=amount_min_exclusive,
    )

    total = filtered_query.count()
    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    safe_page = min(safe_page, total_pages)
    offset = (safe_page - 1) * safe_page_size
    items = (
        filtered_query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(safe_page_size)
        .all()
    )
    filter_options = get_transaction_filter_options(db, owner_id, account_id=account_id)

    return {
        "items": items,
        "total": total,
        "scope_total": scope_total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
        **filter_options,
    }


def get_transactions_for_user(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    *,
    limit: int = 500,
    offset: int = 0,
) -> list[Transaction]:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    safe_limit = max(1, min(int(limit or 500), 1000))
    safe_offset = max(0, int(offset or 0))
    return (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )


def get_uncategorized_candidates(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    *,
    limit: int = MAX_BULK_CATEGORY_CANDIDATES,
    transaction_ids: Iterable[int] | None = None,
) -> list[Transaction]:
    query = (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id)
        .filter(Transaction.category.in_(UNCATEGORIZED_VALUES))
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    if transaction_ids is not None:
        requested_ids = [int(item) for item in transaction_ids if item]
        if not requested_ids:
            return []
        query = query.filter(Transaction.id.in_(requested_ids))
        safe_limit = min(len(set(requested_ids)), 1000)
    else:
        safe_limit = max(1, min(int(limit or MAX_BULK_CATEGORY_CANDIDATES), MAX_BULK_CATEGORY_CANDIDATES))

    return (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(safe_limit)
        .all()
    )


def apply_bulk_categories(
    db: Session,
    owner_id: int,
    transaction_ids: Iterable[int],
    suggested_category_map: dict[int, str],
) -> int:
    updated_count = 0
    memory_created = 0
    memory_updated = 0
    learning_events_created = 0

    transactions = (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id, Transaction.id.in_(list(transaction_ids)))
        .all()
    )

    for transaction in transactions:
        new_category = normalize_category_name(suggested_category_map.get(transaction.id))
        if new_category and transaction.category != new_category:
            transaction.category = new_category
            transaction.category_source = "bulk_apply"
            transaction.category_confidence = 0.88
            transaction.category_reason = "Applied from the smart categorization bulk review workflow."
            updated_count += 1
            memory_stats = save_category_memory(
                db=db,
                owner_id=owner_id,
                description=transaction.description,
                category=new_category,
                tx_type=transaction.type,
                amount=transaction.amount,
            )
            memory_created += memory_stats["created"]
            memory_updated += memory_stats["updated"]
            if record_category_learning_event(
                db=db,
                owner_id=owner_id,
                description=transaction.description,
                category=new_category,
                tx_type=transaction.type,
                amount=transaction.amount,
                account_id=transaction.account_id,
                signal_source="bulk_apply",
                confidence=0.88,
                affected_count=1,
            ):
                learning_events_created += 1

    if updated_count > 0 or memory_created > 0 or memory_updated > 0 or learning_events_created > 0:
        db.commit()

    return updated_count


def repair_category_learning_artifacts(db: Session, owner_id: int) -> dict[str, int]:
    """Normalize stored learning data and remove corrupted category signals.

    Older UI bugs could accidentally save one-letter categories such as "S".
    Transactions can be repaired separately, but learned memories also need
    cleanup so bad labels do not keep influencing future imports.
    """

    deleted_memories = 0
    updated_memories = 0
    deleted_profiles = 0
    updated_profiles = 0
    deleted_events = 0
    updated_events = 0
    profile_keys_to_refresh: set[tuple[str, str]] = set()

    memories = db.query(CategoryMemory).filter(CategoryMemory.owner_id == owner_id).all()
    for memory in memories:
        normalized_category = normalize_category_name(memory.category)
        if (
            not should_store_category_memory(normalized_category)
            or not is_valid_category_memory_keyword(memory.keyword)
        ):
            db.delete(memory)
            deleted_memories += 1
            continue
        if memory.category != normalized_category:
            memory.category = normalized_category
            updated_memories += 1

    profiles = (
        db.query(MerchantCategoryProfile)
        .filter(MerchantCategoryProfile.owner_id == owner_id)
        .all()
    )
    for profile in profiles:
        normalized_category = normalize_category_name(profile.category)
        base_merchant_key = merchant_profile_base_key(profile.merchant_key)
        if base_merchant_key:
            profile_keys_to_refresh.add((base_merchant_key, profile.transaction_type))
        if (
            not should_store_category_memory(normalized_category)
            or not is_valid_merchant_learning_key(profile.merchant_key)
        ):
            db.delete(profile)
            deleted_profiles += 1
            continue
        if profile.category != normalized_category:
            profile.category = normalized_category
            updated_profiles += 1

    learning_events = (
        db.query(CategoryLearningEvent)
        .filter(CategoryLearningEvent.owner_id == owner_id)
        .all()
    )
    for event in learning_events:
        normalized_category = normalize_category_name(event.category)
        if (
            not should_store_category_memory(normalized_category)
            or not is_valid_merchant_learning_key(event.merchant_key)
        ):
            db.delete(event)
            deleted_events += 1
            continue
        if event.category != normalized_category:
            event.category = normalized_category
            updated_events += 1

    if profile_keys_to_refresh:
        db.flush()
        for merchant_key, tx_type in profile_keys_to_refresh:
            if merchant_key and tx_type:
                refresh_community_merchant_profile_cache(db, merchant_key, tx_type)

    return {
        "learning_memories_deleted": deleted_memories,
        "learning_memories_updated": updated_memories,
        "merchant_profiles_deleted": deleted_profiles,
        "merchant_profiles_updated": updated_profiles,
        "learning_events_deleted": deleted_events,
        "learning_events_updated": updated_events,
    }


def normalize_existing_categories_for_user(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> dict:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    transactions = query.all()

    updated_count = 0
    changes: dict[str, str] = {}
    memory_created = 0
    memory_updated = 0
    artifact_stats = repair_category_learning_artifacts(db, owner_id)

    for transaction in transactions:
        old_category = transaction.category or "other"
        new_category = normalize_category_name(old_category)
        category_is_usable = is_usable_category_name(new_category)
        category_decision = categorize_transaction_details(
            db=db,
            owner_id=owner_id,
            description=transaction.description,
            tx_type=transaction.type,
            amount=transaction.amount,
        )
        suggested_category = normalize_category_name(category_decision.category)
        should_apply_suggestion = (
            (category_decision.confidence >= 0.88 or not category_is_usable)
            and suggested_category != new_category
            and (
                new_category in UNCATEGORIZED_VALUES
                or not category_is_usable
                or (
                    new_category == "income"
                    and suggested_category in {"refund", "transfer"}
                )
            )
        )

        if should_apply_suggestion:
            new_category = suggested_category
        elif not category_is_usable:
            new_category = "other"

        if old_category != new_category:
            transaction.category = new_category
            transaction.category_source = "normalize_existing"
            transaction.category_confidence = (
                category_decision.confidence if should_apply_suggestion else 0.8
            )
            transaction.category_reason = (
                category_decision.reason
                if should_apply_suggestion
                else "Normalized a legacy category label into the supported category taxonomy."
            )
            updated_count += 1
            if old_category not in changes:
                changes[old_category] = new_category

        memory_stats = save_category_memory(
            db=db,
            owner_id=owner_id,
            description=transaction.description,
            category=new_category,
            tx_type=transaction.type,
            amount=transaction.amount,
        )
        memory_created += memory_stats["created"]
        memory_updated += memory_stats["updated"]

    final_artifact_stats = repair_category_learning_artifacts(db, owner_id)
    artifact_stats = {
        key: artifact_stats.get(key, 0) + final_artifact_stats.get(key, 0)
        for key in set(artifact_stats) | set(final_artifact_stats)
    }
    artifact_change_count = sum(artifact_stats.values())
    if updated_count > 0 or memory_created > 0 or memory_updated > 0 or artifact_change_count > 0:
        db.commit()

    return {
        "updated_count": updated_count,
        "changes": changes,
        "memory_entries_created": memory_created,
        "memory_entries_updated": memory_updated,
        **artifact_stats,
    }
