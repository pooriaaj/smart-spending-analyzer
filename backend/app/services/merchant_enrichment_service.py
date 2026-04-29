from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import MerchantLookupCache


GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
MERCHANT_LOOKUP_REGION = os.getenv("MERCHANT_LOOKUP_REGION", "Toronto, Canada")
MERCHANT_LOOKUP_REGION_CODE = os.getenv("MERCHANT_LOOKUP_REGION_CODE", "CA")
MERCHANT_LOOKUP_TIMEOUT_SECONDS = float(os.getenv("MERCHANT_LOOKUP_TIMEOUT_SECONDS", "2.5"))

LOOKUP_STOPWORDS = {
    "authorized",
    "bank",
    "card",
    "contactless",
    "credit",
    "debit",
    "interac",
    "misc",
    "online",
    "payment",
    "paypal",
    "pos",
    "purchase",
    "pymt",
    "pmt",
    "transaction",
    "visa",
}

SEMANTIC_CATEGORY_MARKERS: dict[str, tuple[str, ...]] = {
    "groceries": (
        "food basics",
        "foodbasics",
        "freshco",
        "grocer",
        "grocery",
        "loblaws",
        "market",
        "metro",
        "nofrills",
        "no frills",
        "supermarket",
        "walmart",
    ),
    "restaurant": (
        "bagel",
        "bistro",
        "burger",
        "chicken",
        "deli",
        "dessert",
        "diner",
        "grill",
        "island restaurant",
        "kitchen",
        "pastry",
        "pizza",
        "puffs",
        "restaurant",
        "shawarma",
        "sushi",
        "thai",
    ),
    "cafe": (
        "cafe",
        "coffee",
        "espresso",
        "latte",
        "tea",
    ),
    "transport": (
        "parking",
        "presto",
        "taxi",
        "transit",
        "uber",
    ),
    "health": (
        "clinic",
        "dental",
        "dentist",
        "doctor",
        "pharmacy",
    ),
}

GOOGLE_PLACE_TYPE_CATEGORY_MAP: dict[str, tuple[str, float]] = {
    "bakery": ("restaurant", 0.86),
    "bar": ("restaurant", 0.86),
    "cafe": ("cafe", 0.9),
    "convenience_store": ("groceries", 0.82),
    "drugstore": ("health", 0.88),
    "fast_food_restaurant": ("restaurant", 0.9),
    "food": ("restaurant", 0.76),
    "gas_station": ("transport", 0.9),
    "grocery_store": ("groceries", 0.94),
    "meal_delivery": ("restaurant", 0.88),
    "meal_takeaway": ("restaurant", 0.88),
    "parking": ("transport", 0.9),
    "pharmacy": ("health", 0.9),
    "restaurant": ("restaurant", 0.92),
    "supermarket": ("groceries", 0.94),
    "thai_restaurant": ("restaurant", 0.94),
}


@dataclass(frozen=True)
class MerchantEnrichmentResult:
    category: str
    confidence: float
    matched_keyword: str | None
    reason: str
    source: str


def merchant_lookup_cache_table_available(db: Session) -> bool:
    try:
        return inspect(db.get_bind()).has_table(MerchantLookupCache.__tablename__)
    except Exception:
        return False


def title_case_merchant(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def normalize_merchant_lookup_query(description: str) -> str | None:
    value = description.lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\bpaypal\s*[*#:-]?\s*", " ", value)
    value = re.sub(r"\b(?:misc(?:ellaneous)?\s+)?payment\b", " ", value)
    value = re.sub(r"\bsupermar\w*\b", "supermarket", value)
    value = re.sub(r"\bsuper\s*$", "supermarket", value)
    value = re.sub(r"\bres\b", "restaurant", value)
    value = re.sub(r"\brest\b", "restaurant", value)
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    value = re.sub(r"\b\d+[a-z]*\b", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    if not value:
        return None

    tokens = [
        token
        for token in value.split()
        if token not in LOOKUP_STOPWORDS and not token.isdigit() and len(token) >= 2
    ]
    if not tokens:
        return None

    query = re.sub(r"\s+", " ", " ".join(tokens)).strip()
    return query[:160] or None


def infer_semantic_category(query: str) -> MerchantEnrichmentResult | None:
    padded_query = f" {query.lower()} "

    for category, markers in SEMANTIC_CATEGORY_MARKERS.items():
        for marker in markers:
            padded_marker = f" {marker.lower()} "
            if padded_marker in padded_query or marker.lower() in query.lower():
                confidence = 0.84
                if marker in {"grocery", "grocer", "supermarket", "restaurant", "thai"}:
                    confidence = 0.88
                return MerchantEnrichmentResult(
                    category=category,
                    confidence=confidence,
                    matched_keyword=marker,
                    reason=(
                        "Matched merchant wording that strongly indicates a spending category. "
                        "This does not send the full transaction, amount, date, or account data anywhere."
                    ),
                    source="merchant_semantic",
                )

    return None


def get_cached_merchant_enrichment(
    db: Session,
    merchant_key: str,
    tx_type: str,
) -> MerchantEnrichmentResult | None:
    if not merchant_lookup_cache_table_available(db):
        return None

    cached = (
        db.query(MerchantLookupCache)
        .filter(
            MerchantLookupCache.merchant_key == merchant_key,
            MerchantLookupCache.transaction_type == tx_type,
        )
        .first()
    )
    if not cached:
        return None

    return MerchantEnrichmentResult(
        category=cached.category,
        confidence=float(cached.confidence or 0.78),
        matched_keyword=cached.matched_signal,
        reason=f"Matched cached merchant enrichment from {cached.provider}.",
        source="merchant_lookup_cache",
    )


def save_cached_merchant_enrichment(
    db: Session,
    merchant_key: str,
    tx_type: str,
    result: MerchantEnrichmentResult,
    provider: str,
) -> None:
    if not merchant_lookup_cache_table_available(db):
        return

    for pending in db.new:
        if not isinstance(pending, MerchantLookupCache):
            continue
        if pending.merchant_key != merchant_key or pending.transaction_type != tx_type:
            continue
        pending.display_name = title_case_merchant(merchant_key)
        pending.category = result.category
        pending.confidence = result.confidence
        pending.matched_signal = result.matched_keyword
        pending.provider = provider
        return

    existing = (
        db.query(MerchantLookupCache)
        .filter(
            MerchantLookupCache.merchant_key == merchant_key,
            MerchantLookupCache.transaction_type == tx_type,
        )
        .first()
    )
    if existing:
        existing.display_name = title_case_merchant(merchant_key)
        existing.category = result.category
        existing.confidence = result.confidence
        existing.matched_signal = result.matched_keyword
        existing.provider = provider
        return

    db.add(
        MerchantLookupCache(
            merchant_key=merchant_key,
            display_name=title_case_merchant(merchant_key),
            category=result.category,
            transaction_type=tx_type,
            confidence=result.confidence,
            matched_signal=result.matched_keyword,
            provider=provider,
        )
    )


def google_places_lookup_enabled() -> bool:
    return bool(GOOGLE_PLACES_API_KEY)


def build_google_places_query(merchant_key: str) -> str:
    if not MERCHANT_LOOKUP_REGION:
        return merchant_key
    if MERCHANT_LOOKUP_REGION.lower() in merchant_key.lower():
        return merchant_key
    return f"{merchant_key} {MERCHANT_LOOKUP_REGION}"


def fetch_google_places_text_search(merchant_key: str) -> dict[str, Any] | None:
    if not google_places_lookup_enabled():
        return None

    payload = {
        "textQuery": build_google_places_query(merchant_key),
        "pageSize": 1,
        "regionCode": MERCHANT_LOOKUP_REGION_CODE,
    }
    request = urllib.request.Request(
        GOOGLE_PLACES_TEXT_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": "places.displayName,places.primaryType,places.types",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=MERCHANT_LOOKUP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def infer_google_places_category(merchant_key: str) -> MerchantEnrichmentResult | None:
    response = fetch_google_places_text_search(merchant_key)
    if not response:
        return None

    places = response.get("places") or []
    if not places:
        return None

    place = places[0]
    place_types = [
        place_type.lower().strip()
        for place_type in [place.get("primaryType"), *(place.get("types") or [])]
        if isinstance(place_type, str) and place_type.strip()
    ]

    for place_type in place_types:
        mapped = GOOGLE_PLACE_TYPE_CATEGORY_MAP.get(place_type)
        if not mapped:
            continue

        category, confidence = mapped
        display_name = (place.get("displayName") or {}).get("text") or merchant_key
        return MerchantEnrichmentResult(
            category=category,
            confidence=confidence,
            matched_keyword=place_type,
            reason=(
                f"Matched merchant lookup result for {display_name} using Google Places business type "
                f"'{place_type}'. Only the cleaned merchant name was searched."
            ),
            source="merchant_lookup",
        )

    return None


def enrich_merchant_category(
    db: Session,
    description: str,
    tx_type: str,
) -> MerchantEnrichmentResult | None:
    if tx_type != "expense":
        return None

    merchant_key = normalize_merchant_lookup_query(description)
    if not merchant_key:
        return None

    cached = get_cached_merchant_enrichment(db, merchant_key, tx_type)
    if cached:
        return cached

    semantic = infer_semantic_category(merchant_key)
    if semantic:
        save_cached_merchant_enrichment(db, merchant_key, tx_type, semantic, provider="semantic")
        return semantic

    google_result = infer_google_places_category(merchant_key)
    if google_result:
        save_cached_merchant_enrichment(db, merchant_key, tx_type, google_result, provider="google_places")
        return google_result

    return None
