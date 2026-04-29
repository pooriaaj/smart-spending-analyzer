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
        "ambrosia",
        "asian grocery",
        "arzon",
        "butcher",
        "convenience store",
        "discount supermarket",
        "farmers market",
        "food market",
        "food basics",
        "foodbasics",
        "food store",
        "freshco",
        "galleria",
        "grocer",
        "grocery",
        "h mart",
        "health food",
        "health food store",
        "khorak",
        "loblaws",
        "market",
        "metro",
        "nofrills",
        "no frills",
        "rabba",
        "supermarket",
        "t and t",
        "tnt supermarket",
        "walmart",
        "whole foods",
    ),
    "restaurant": (
        "bagel",
        "bar and grill",
        "bbq",
        "bistro",
        "breakfast",
        "brunch",
        "burger",
        "burrito",
        "catering",
        "chicken",
        "chipotle",
        "deli",
        "dessert",
        "diner",
        "donut",
        "falafel",
        "fast food",
        "food court",
        "grill",
        "island restaurant",
        "kitchen",
        "meal delivery",
        "meal takeaway",
        "mr puffs",
        "noodle",
        "pastry",
        "pizza",
        "puffs",
        "ramen",
        "restaurant",
        "sandwich",
        "shawarma",
        "snack bar",
        "sushi",
        "taco",
        "thai",
    ),
    "cafe": (
        "cafe",
        "coffee",
        "coffee shop",
        "espresso",
        "latte",
        "second cup",
        "starbucks",
        "tea",
        "tea house",
        "tim hortons",
    ),
    "transport": (
        "bus station",
        "light rail",
        "parking",
        "park and ride",
        "presto",
        "subway station",
        "taxi",
        "train station",
        "transit",
        "transit station",
        "transportation service",
        "uber",
    ),
    "gas": (
        "esso",
        "gas station",
        "petro canada",
        "shell",
        "ultramar",
    ),
    "health": (
        "clinic",
        "dental",
        "dentist",
        "doctor",
        "drugstore",
        "hospital",
        "medical",
        "medical clinic",
        "medical lab",
        "pharmacy",
        "shoppers drug",
        "walk in clinic",
    ),
    "smoking": (
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
        "smokers",
        "tobacco",
        "vape",
        "weed",
    ),
    "alcohol": (
        "beer store",
        "brewery",
        "distillery",
        "lcbo",
        "liquor",
        "liquor store",
        "wine rack",
        "winery",
    ),
    "beauty": (
        "barber",
        "beauty",
        "beauty salon",
        "cosmetics",
        "hair care",
        "hair salon",
        "makeup",
        "nail salon",
        "sephora",
        "spa",
    ),
    "clothing": (
        "clothing",
        "clothing store",
        "foot locker",
        "h and m",
        "shoe store",
        "uniqlo",
        "winners",
        "zara",
    ),
    "home": (
        "building materials",
        "furniture",
        "garden center",
        "hardware",
        "home depot",
        "home goods",
        "home improvement",
        "ikea",
        "rona",
    ),
    "electronics": (
        "best buy",
        "cell phone store",
        "computer",
        "electronics",
        "electronics store",
        "memory express",
    ),
    "pets": (
        "pet care",
        "pet food",
        "pet store",
        "petsmart",
        "veterinary",
    ),
    "shipping": (
        "canada post",
        "courier",
        "fedex",
        "post office",
        "purolator",
        "shipping",
        "ups store",
    ),
    "utilities": (
        "alectra",
        "enbridge",
        "ez pay",
        "hydro",
        "metergy",
        "toronto hydro",
        "utility",
        "water bill",
    ),
    "phone": (
        "bell mobility",
        "fido",
        "freedom mobile",
        "koodo",
        "phone bill",
        "telus",
    ),
    "internet": (
        "bell internet",
        "internet provider",
        "rogers",
        "teksavvy",
    ),
    "insurance": (
        "aviva",
        "belair",
        "economical insurance",
        "insurance",
        "insurance agency",
        "intact",
        "td insurance",
    ),
    "investment": (
        "broker",
        "investment",
        "qtrade",
        "questrade",
        "wealthsimple",
        "ws investments",
    ),
    "bank fees": (
        "bank fee",
        "monthly fee",
        "overdraft",
        "service fee",
    ),
    "education": (
        "college",
        "concordia",
        "course",
        "school",
        "tuition",
        "university",
    ),
    "entertainment": (
        "amusement",
        "cinema",
        "movie",
        "playstation",
        "spotify",
        "theatre",
        "youtube",
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

GOOGLE_PLACE_TYPE_CATEGORY_MAP.update(
    {
        "asian_grocery_store": ("groceries", 0.94),
        "auto_parts_store": ("car maintenance", 0.86),
        "bagel_shop": ("restaurant", 0.9),
        "bar_and_grill": ("restaurant", 0.9),
        "barbecue_restaurant": ("restaurant", 0.9),
        "beauty_salon": ("beauty", 0.9),
        "book_store": ("education", 0.76),
        "breakfast_restaurant": ("restaurant", 0.9),
        "brunch_restaurant": ("restaurant", 0.9),
        "bus_station": ("transport", 0.9),
        "cell_phone_store": ("phone", 0.84),
        "chinese_restaurant": ("restaurant", 0.92),
        "clothing_store": ("clothing", 0.9),
        "coffee_shop": ("cafe", 0.92),
        "cosmetics_store": ("beauty", 0.9),
        "deli": ("restaurant", 0.86),
        "department_store": ("shopping", 0.86),
        "dessert_restaurant": ("restaurant", 0.86),
        "dessert_shop": ("restaurant", 0.82),
        "diner": ("restaurant", 0.9),
        "discount_store": ("shopping", 0.84),
        "discount_supermarket": ("groceries", 0.94),
        "electronics_store": ("electronics", 0.9),
        "farmers_market": ("groceries", 0.92),
        "fitness_center": ("health", 0.78),
        "food_court": ("restaurant", 0.82),
        "food_delivery": ("restaurant", 0.82),
        "food_store": ("groceries", 0.88),
        "furniture_store": ("home", 0.86),
        "gift_shop": ("shopping", 0.78),
        "gym": ("health", 0.78),
        "hair_care": ("beauty", 0.9),
        "hair_salon": ("beauty", 0.9),
        "hardware_store": ("home", 0.86),
        "health_food_store": ("groceries", 0.88),
        "home_goods_store": ("home", 0.86),
        "home_improvement_store": ("home", 0.88),
        "hospital": ("health", 0.9),
        "hotel": ("travel", 0.9),
        "ice_cream_shop": ("restaurant", 0.78),
        "indian_restaurant": ("restaurant", 0.92),
        "italian_restaurant": ("restaurant", 0.92),
        "japanese_restaurant": ("restaurant", 0.92),
        "jewelry_store": ("shopping", 0.82),
        "juice_shop": ("restaurant", 0.78),
        "korean_restaurant": ("restaurant", 0.92),
        "laundry": ("personal", 0.78),
        "lebanese_restaurant": ("restaurant", 0.92),
        "liquor_store": ("alcohol", 0.92),
        "medical_clinic": ("health", 0.9),
        "medical_lab": ("health", 0.88),
        "mexican_restaurant": ("restaurant", 0.92),
        "middle_eastern_restaurant": ("restaurant", 0.92),
        "nail_salon": ("beauty", 0.9),
        "pet_store": ("pets", 0.9),
        "pizza_restaurant": ("restaurant", 0.92),
        "post_office": ("shipping", 0.84),
        "pub": ("restaurant", 0.82),
        "ramen_restaurant": ("restaurant", 0.92),
        "sandwich_shop": ("restaurant", 0.88),
        "shoe_store": ("clothing", 0.86),
        "shopping_mall": ("shopping", 0.84),
        "spa": ("beauty", 0.84),
        "sporting_goods_store": ("shopping", 0.82),
        "steak_house": ("restaurant", 0.92),
        "sushi_restaurant": ("restaurant", 0.92),
        "tailor": ("clothing", 0.76),
        "tea_house": ("cafe", 0.82),
        "thrift_store": ("shopping", 0.78),
        "toy_store": ("shopping", 0.78),
        "train_station": ("transport", 0.9),
        "transit_station": ("transport", 0.9),
        "travel_agency": ("travel", 0.82),
        "veterinary_care": ("pets", 0.88),
        "warehouse_store": ("shopping", 0.78),
        "wine_bar": ("alcohol", 0.84),
        "winery": ("alcohol", 0.9),
    }
)


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


def infer_payment_processor_category(description: str) -> MerchantEnrichmentResult | None:
    lowered = description.lower()
    if "paypal" not in lowered:
        return None

    merchant_key = normalize_merchant_lookup_query(description)
    if merchant_key:
        return None

    return MerchantEnrichmentResult(
        category="transfer",
        confidence=0.58,
        matched_keyword="paypal",
        reason=(
            "Only a payment processor was visible, not the final merchant. "
            "Classified as transfer with low confidence so the user can review it."
        ),
        source="payment_processor",
    )


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

    processor_only = infer_payment_processor_category(description)
    if processor_only:
        return processor_only

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
