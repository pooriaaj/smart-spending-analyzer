from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.transaction_service import categorize_transaction
from app.services.vision_ocr_service import (
    build_input_image_part,
    is_vision_ocr_enabled,
    run_vision_prompt,
)

SUPPORTED_RECEIPT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}


def _clean_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    return json.loads(cleaned)


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return value


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None

    try:
        cleaned = str(value).replace(",", "").replace("$", "").strip()
        return abs(float(cleaned))
    except Exception:
        return None


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except Exception:
        confidence = 0.0

    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def _compute_confidence(merchant: str | None, date_value: str | None, amount: float | None, model_confidence: float) -> float:
    score = model_confidence

    if merchant:
        score += 0.12
    if date_value:
        score += 0.12
    if amount is not None:
        score += 0.18

    return round(min(score, 0.99), 2)


def scan_receipt_file(
    db: Session,
    owner_id: int,
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
) -> dict[str, Any]:
    if content_type not in SUPPORTED_RECEIPT_TYPES:
        raise ValueError("Only JPG, PNG, and WEBP receipt images are supported right now.")

    if not is_vision_ocr_enabled():
        raise ValueError(
            "Receipt OCR is not enabled yet. Add a valid OPENAI_API_KEY to enable vision scanning."
        )

    mime_type = content_type or "image/png"

    prompt = """
You are extracting receipt information from a shopping or payment receipt image.

Return ONLY valid JSON with this exact structure:
{
  "merchant": "string or null",
  "date": "YYYY-MM-DD or null",
  "amount": 0.0,
  "transaction_type": "expense",
  "category_hint": "string or null",
  "confidence": 0.0,
  "raw_text_preview": "short text preview",
  "notes": ["note 1", "note 2"]
}

Rules:
- extract the FINAL paid total, not subtotal or tax-only
- merchant should be the business name, short and clean
- date should be normalized if visible
- transaction_type should be "expense" unless the receipt clearly shows a refund
- confidence should be 0 to 1
- raw_text_preview should be short, max 300 chars
- notes should explain uncertainty or ambiguity
- do not include markdown
""".strip()

    response_text = run_vision_prompt(
        prompt,
        [build_input_image_part(file_bytes, mime_type)],
    )
    parsed = _clean_json_text(response_text)

    merchant = parsed.get("merchant")
    date_value = _normalize_date(parsed.get("date"))
    amount = _safe_float(parsed.get("amount"))
    transaction_type = str(parsed.get("transaction_type") or "expense").lower().strip()
    if transaction_type not in {"income", "expense"}:
        transaction_type = "expense"

    raw_text_preview = parsed.get("raw_text_preview")
    notes = parsed.get("notes") or []
    if not isinstance(notes, list):
        notes = [str(notes)]

    category_hint = str(parsed.get("category_hint") or "").strip()
    description_for_category = " ".join(
        part for part in [merchant or "", category_hint, raw_text_preview or ""] if part
    ).strip()

    category = categorize_transaction(
        db=db,
        owner_id=owner_id,
        description=description_for_category or (merchant or filename),
        tx_type=transaction_type,
        amount=amount,
    )

    confidence = _compute_confidence(
        merchant=merchant,
        date_value=date_value,
        amount=amount,
        model_confidence=_safe_confidence(parsed.get("confidence")),
    )

    if amount is None:
        notes = ["Total amount could not be extracted reliably."] + notes

    return {
        "merchant": merchant,
        "date": date_value,
        "amount": amount,
        "category": category,
        "type": transaction_type,
        "confidence": confidence,
        "raw_text_preview": raw_text_preview,
        "notes": notes[:5],
    }
