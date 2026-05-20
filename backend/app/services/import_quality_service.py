from __future__ import annotations

from dataclasses import dataclass

from app.security import sanitize_import_text
from app.services.category_taxonomy import normalize_category_signal_text


REFERENCE_CODE_AMOUNT_DESCRIPTORS = (
    "e transfer",
    "interac received",
    "interac sent",
    "virement interac",
)
SUSPICIOUS_REFERENCE_AMOUNT_MINIMUM = 5000.0
SUSPICIOUS_REFERENCE_REPAIRED_MAXIMUM = 1000.0


@dataclass(frozen=True)
class SuspiciousAmountSuggestion:
    suggested_amount: float
    confidence: float
    reason: str


def suggest_reference_code_amount_values(
    *,
    description: str,
    amount: float | None,
) -> SuspiciousAmountSuggestion | None:
    """Detect likely parser mistakes where a reference digit merged into an amount.

    Example: some bank PDFs can turn a real $200 e-transfer into $5,200 when a
    statement/reference digit is visually adjacent to the amount column. We do
    not silently change the amount; we mark it for review before saving.
    """

    cleaned_description = sanitize_import_text(description)
    normalized_description = normalize_category_signal_text(cleaned_description)
    if not any(marker in normalized_description for marker in REFERENCE_CODE_AMOUNT_DESCRIPTORS):
        return None

    current_amount = abs(float(amount or 0))
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

    return SuspiciousAmountSuggestion(
        suggested_amount=suggested_amount,
        confidence=0.86,
        reason=(
            "This looks like a statement-parser issue where one reference-code digit "
            "may have been merged with the real transfer amount. Review before saving."
        ),
    )
