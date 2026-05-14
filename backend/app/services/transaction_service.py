from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, or_
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
from app.services.merchant_enrichment_service import enrich_merchant_category
from app.schemas import StatementPreviewRow


SUPPORTED_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
UNCATEGORIZED_VALUES = {"other", "misc", "uncategorized", "unknown"}
STATEMENT_RECONCILIATION_DATE_WINDOW_DAYS = 3
STATEMENT_RECONCILIATION_AMOUNT_TOLERANCE = 0.01
CATEGORY_REVIEW_CONFIDENCE_THRESHOLD = 0.75
CATEGORY_REVIEW_REQUIRED_SOURCES = {"fallback", "payment_processor"}
EXPENSE_INCOMPATIBLE_CATEGORIES = {"income", "salary", "refund"}
COMMUNITY_PROFILE_MIN_OWNER_COUNT = 2
COMMUNITY_PROFILE_MIN_CATEGORY_SHARE = 0.67
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

HEADER_ALIASES = {
    "date": {"date", "transaction_date", "posted_date"},
    "description": {"description", "details", "memo", "merchant", "transaction_description"},
    "amount": {"amount", "transaction_amount"},
    "debit": {"debit", "withdrawal", "money_out"},
    "credit": {"credit", "deposit", "money_in"},
    "type": {"type", "transaction_type"},
    "category": {"category"},
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


REFERENCE_CODE_AMOUNT_DESCRIPTORS = (
    "e transfer",
    "interac received",
    "interac sent",
    "virement interac",
)
SUSPICIOUS_REFERENCE_AMOUNT_MINIMUM = 5000.0
SUSPICIOUS_REFERENCE_REPAIRED_MAXIMUM = 1000.0


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
    value = value.strip()

    date_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%b %d, %Y",
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
    cleaned = value.replace(",", "").replace("$", "").strip()
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

    return CategoryDecision(
        category=best_category,
        confidence=round(confidence, 2),
        matched_keyword=merchant_key,
        reason=(
            "Matched anonymized community merchant learning from multiple users who "
            "confirmed this merchant category. Personal memory still overrides this."
        ),
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
) -> int:
    normalized_category = normalize_category_name(category)
    if not should_store_category_memory(normalized_category):
        return 0

    fingerprint = extract_merchant_fingerprint(description)
    if not fingerprint:
        return 0

    merchant_key, _ = fingerprint
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
        updated_count += 1

    return updated_count


def get_category_learning_candidates(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    limit: int = 12,
) -> list[CategoryLearningCandidate]:
    max_candidates = max(1, min(int(limit or 12), 50))
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    transactions = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
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
    learning_candidates = get_category_learning_candidates(
        db=db,
        owner_id=owner_id,
        account_id=account_id,
        limit=50,
    )
    learning_candidate_count = len(learning_candidates)
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


def suggest_reference_code_amount_repair(transaction: Transaction) -> SuspiciousAmountRepairCandidate | None:
    description = normalize_description(transaction.description)
    normalized_description = normalize_category_signal_text(description)
    if not any(marker in normalized_description for marker in REFERENCE_CODE_AMOUNT_DESCRIPTORS):
        return None

    current_amount = abs(float(transaction.amount or 0))
    if current_amount < SUSPICIOUS_REFERENCE_AMOUNT_MINIMUM:
        return None

    if abs(current_amount - round(current_amount)) > 0.005:
        return None

    amount_digits = str(int(round(current_amount)))
    if len(amount_digits) < 4:
        return None

    repaired_digits = amount_digits[1:]
    if not repaired_digits or set(repaired_digits) == {"0"}:
        return None

    suggested_amount = float(int(repaired_digits))
    if not (0 < suggested_amount <= SUSPICIOUS_REFERENCE_REPAIRED_MAXIMUM):
        return None

    return SuspiciousAmountRepairCandidate(
        transaction_id=transaction.id,
        date=transaction.date,
        description=description,
        type=transaction.type,
        category=transaction.category,
        current_amount=current_amount,
        suggested_amount=suggested_amount,
        confidence=0.86,
        reason=(
            "This looks like a legacy statement-parser issue where one reference-code digit "
            "was merged with the real transfer amount. Review before applying."
        ),
    )


def get_suspicious_amount_repair_candidates(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> list[SuspiciousAmountRepairCandidate]:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    candidates: list[SuspiciousAmountRepairCandidate] = []
    for transaction in query.order_by(Transaction.date.desc(), Transaction.id.desc()).all():
        candidate = suggest_reference_code_amount_repair(transaction)
        if candidate:
            candidates.append(candidate)

    return candidates


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
    normalized = [normalize_header(name) for name in fieldnames]
    mapping: dict[str, str] = {}

    for canonical, aliases in HEADER_ALIASES.items():
        for header in normalized:
            if header in aliases:
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

    return mapping


def read_csv_rows(text: str) -> tuple[list[dict], dict[str, str]]:
    dialect = sniff_csv_dialect(text)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    if not reader.fieldnames:
        raise ValueError("CSV file is missing headers.")

    normalized_headers = [normalize_header(field) for field in reader.fieldnames]
    reader.fieldnames = normalized_headers
    header_mapping = resolve_header_mapping(normalized_headers)

    rows = []
    for row in reader:
        normalized_row = {normalize_header(k): (v or "").strip() for k, v in row.items()}
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
    text = re.sub(r"\s+", " ", value.strip())
    text = strip_statement_header_noise(text)
    text = strip_statement_transaction_prefixes(text)
    text = strip_payment_processor_prefixes(text)
    text = re.sub(r"\bpos\b|\bpurchase\b|\bpayment\b|\bdebit\b|\bcredit\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text or value.strip()


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

    community_profile = learnable_category_from_community_profiles(
        db,
        owner_id,
        description,
        tx_type,
        amount,
    )
    if community_profile:
        return community_profile

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

    for row in rows:
        try:
            tx_date = parse_date(row[header_mapping["date"]])
            raw_description = row[header_mapping["description"]]
            description = normalize_description(raw_description)

            tx_type, amount = infer_type_and_amount(row, header_mapping)

            if header_mapping.get("category") and row.get(header_mapping["category"]):
                category = resolve_import_category_for_transaction(
                    db=db,
                    owner_id=owner_id,
                    description=description,
                    tx_type=tx_type,
                    category=row[header_mapping["category"]],
                    amount=amount,
                )
            else:
                category = categorize_transaction(db, owner_id, description, tx_type, amount=amount)

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

        except Exception:
            invalid_rows_skipped += 1

    if to_insert:
        db.bulk_save_objects(to_insert)
        db.commit()

    return {
        "message": "Statement import completed",
        "imported": imported,
        "duplicates_skipped": duplicates_skipped,
        "invalid_rows_skipped": invalid_rows_skipped,
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

    for row_number, row in enumerate(rows, start=2):
        try:
            tx_date = parse_date(row[header_mapping["date"]])
            raw_description = row[header_mapping["description"]]
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
        except Exception:
            invalid_rows_skipped += 1

    if not preview_rows:
        raise ValueError("No transaction rows were recognized in this CSV statement.")

    return {
        "preview_rows": preview_rows,
        "invalid_rows_skipped": invalid_rows_skipped,
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


def get_transaction_filter_options(db: Session, owner_id: int, account_id: int | None = None) -> dict:
    scope_query = build_transaction_scope_query(db, owner_id, account_id=account_id)
    date_rows = scope_query.with_entities(Transaction.date).distinct().all()
    category_rows = scope_query.with_entities(Transaction.category).distinct().all()

    months = sorted(
        {
            row[0].isoformat()[:7]
            for row in date_rows
            if row[0] is not None
        },
        reverse=True,
    )
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


def get_transactions_for_user(db: Session, owner_id: int, account_id: int | None = None) -> list[Transaction]:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()


def get_uncategorized_candidates(db: Session, owner_id: int, account_id: int | None = None) -> list[Transaction]:
    query = (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id)
        .filter(Transaction.category.in_(UNCATEGORIZED_VALUES))
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()


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

    if updated_count > 0 or memory_created > 0 or memory_updated > 0:
        db.commit()

    return {
        "updated_count": updated_count,
        "changes": changes,
        "memory_entries_created": memory_created,
        "memory_entries_updated": memory_updated,
    }
