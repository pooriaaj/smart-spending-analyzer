"""How the app decides whether money was earned, spent, or only moved.

Kept apart from analytics_service and transaction_service on purpose: import,
categorisation and reporting all need these rules, and a shared module is what
stops three copies of "is this a transfer?" drifting away from each other.

Nothing here imports another service, so anything may import it.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.models import CashflowRoleMemory, Transaction


# What the owner told us a row really was. Stored on the transaction and always
# beating the automatic rules below, because no rule can tell a paycheque from a
# repaid loan when the bank prints the same words for both.
CASHFLOW_ROLE_INCOME = "income"
CASHFLOW_ROLE_EXPENSE = "expense"
CASHFLOW_ROLE_NEUTRAL = "neutral"
CASHFLOW_ROLES = (CASHFLOW_ROLE_INCOME, CASHFLOW_ROLE_EXPENSE, CASHFLOW_ROLE_NEUTRAL)
DIRECTIONAL_CASHFLOW_ROLES = (CASHFLOW_ROLE_INCOME, CASHFLOW_ROLE_EXPENSE)

# Money that mechanically cannot be earned or spent, for anybody. Paying a credit
# card moves money to the account where the purchases are already counted, a refund
# gives back part of a purchase already counted, and a cancelled transfer is the
# bank handing the money straight back. Nothing here is a judgement call, so these
# stay automatic and are never raised for review.
INTERNAL_MOVEMENT_CATEGORIES = {
    "refund",
    "refunds",
    "credit card payment",
    "credit card payments",
}
INTERNAL_MOVEMENT_DESCRIPTION_MARKERS = (
    "online transfer",
    "online banking transfer",
    "transfer to deposit account",
    "credit card payment",
    "payment - thank you",
    "payment thank you",
    "paiement - merci",
    "payback with points",
    "atm deposit",
    "virement en ligne",
    "e-transfer cancel",
    "etransfer cancel",
    "transfer cancel",
    "virement annule",
)

# Money whose meaning only the owner knows. An incoming e-Transfer is a paycheque
# for one person and their own savings moving for another; an outgoing one is rent
# to a landlord for one and a loan to a sibling for another. Guessing here is what
# put one household's habits into everybody's totals, so the app stops guessing:
# these are held out of income and spending until the owner says what they were.
AMBIGUOUS_TRANSFER_CATEGORIES = {
    "transfer",
    "transfers",
}
AMBIGUOUS_TRANSFER_DESCRIPTION_MARKERS = (
    "e-transfer",
    "etransfer",
    "interac sent",
    "interac received",
    "virement interac",
    "transfer from",
    "transfer to",
)

CASHFLOW_NEUTRAL_CATEGORIES = INTERNAL_MOVEMENT_CATEGORIES | AMBIGUOUS_TRANSFER_CATEGORIES
CASHFLOW_NEUTRAL_DESCRIPTION_MARKERS = (
    INTERNAL_MOVEMENT_DESCRIPTION_MARKERS + AMBIGUOUS_TRANSFER_DESCRIPTION_MARKERS
)


def normalize_cashflow_category(value: str | None) -> str:
    cleaned = str(value or "").strip().lower().replace("&", "and")
    cleaned = (
        unicodedata.normalize("NFD", cleaned)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    cleaned = re.sub(r"[_\-]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned)


def normalize_cashflow_role(role: str | None) -> str | None:
    """Accept a stored role, or None for "let the automatic rules decide again"."""

    if role is None:
        return None

    cleaned = str(role).strip().lower()
    if not cleaned:
        return None
    if cleaned not in CASHFLOW_ROLES:
        raise ValueError(f"Unsupported cashflow role: {role}")
    return cleaned


# --- Python rules, for rows that are not in the database yet ------------------


def description_matches_markers(description: str | None, markers) -> bool:
    normalized_description = str(description or "").strip().lower()
    return any(marker in normalized_description for marker in markers)


def is_cashflow_neutral_category(category: str | None) -> bool:
    return normalize_cashflow_category(category) in CASHFLOW_NEUTRAL_CATEGORIES


def is_internal_movement(description: str | None, category: str | None = None) -> bool:
    return description_matches_markers(description, INTERNAL_MOVEMENT_DESCRIPTION_MARKERS) or (
        normalize_cashflow_category(category) in INTERNAL_MOVEMENT_CATEGORIES
    )


def is_ambiguous_transfer(description: str | None, category: str | None = None) -> bool:
    """Whether the automatic rules must not label this row on the owner's behalf.

    Import needs this before a transaction exists, so it cannot ask the database.
    This and ``ambiguous_transfer_filter`` must stay in step, which is why they
    read off the same markers.
    """

    if is_internal_movement(description, category):
        return False

    return description_matches_markers(description, AMBIGUOUS_TRANSFER_DESCRIPTION_MARKERS) or (
        normalize_cashflow_category(category) in AMBIGUOUS_TRANSFER_CATEGORIES
    )


# --- SQL rules, for rows already stored ---------------------------------------


def normalized_category_expression():
    return func.lower(
        func.replace(
            func.replace(func.coalesce(Transaction.category, ""), "_", " "),
            "-",
            " ",
        )
    )


def owner_cashflow_role_expression():
    """The owner's stored answer for a row, blank when they have not given one."""

    return func.lower(func.coalesce(Transaction.cashflow_role, ""))


def description_marker_filter(markers):
    normalized_description = func.lower(func.coalesce(Transaction.description, ""))
    return or_(*[normalized_description.like(f"%{marker}%") for marker in markers])


def internal_movement_filter():
    """Rows that moved money without earning or spending it, for any user."""

    return or_(
        description_marker_filter(INTERNAL_MOVEMENT_DESCRIPTION_MARKERS),
        normalized_category_expression().in_(tuple(INTERNAL_MOVEMENT_CATEGORIES)),
    )


def ambiguous_transfer_filter():
    """Rows the automatic rules must not label on the owner's behalf.

    A description that is mechanically internal wins, so "Online transfer to
    deposit account" is settled rather than put on the review pile.
    """

    return and_(
        or_(
            description_marker_filter(AMBIGUOUS_TRANSFER_DESCRIPTION_MARKERS),
            normalized_category_expression().in_(tuple(AMBIGUOUS_TRANSFER_CATEGORIES)),
        ),
        ~internal_movement_filter(),
    )


def cashflow_neutral_filter():
    """Rows kept out of both income and spending.

    The owner's answer is final: calling a transfer income or spending pulls it
    back into the totals no matter what the description looks like. Without an
    answer, a transfer counts as neither, which is the only honest default when
    the same words cover a paycheque, a repaid debt and money moved between the
    owner's own accounts.
    """

    role = owner_cashflow_role_expression()
    return and_(
        ~role.in_(DIRECTIONAL_CASHFLOW_ROLES),
        or_(
            role == CASHFLOW_ROLE_NEUTRAL,
            internal_movement_filter(),
            ambiguous_transfer_filter(),
        ),
    )


def pending_cashflow_review_filter():
    """Ambiguous transfers still waiting for the owner to say what they were."""

    return and_(
        owner_cashflow_role_expression() == "",
        ambiguous_transfer_filter(),
    )


def transaction_amount_magnitude_expression():
    return func.abs(func.coalesce(Transaction.amount, 0.0))


def effective_direction_expression():
    """Whether a row counts as income or spending, the owner's answer first."""

    role = owner_cashflow_role_expression()
    return case(
        (role.in_(DIRECTIONAL_CASHFLOW_ROLES), role),
        else_=func.lower(func.coalesce(Transaction.type, "")),
    )


def income_amount_expression():
    return case(
        (
            effective_direction_expression() == CASHFLOW_ROLE_INCOME,
            transaction_amount_magnitude_expression(),
        ),
        else_=0.0,
    )


def expense_amount_expression():
    return case(
        (
            effective_direction_expression() == CASHFLOW_ROLE_EXPENSE,
            transaction_amount_magnitude_expression(),
        ),
        else_=0.0,
    )


# --- Learned answers ----------------------------------------------------------


def recall_role_for_merchant(
    db: Session,
    owner_id: int,
    merchant_key: str | None,
    tx_type: str | None,
) -> str | None:
    """The owner's standing answer for this counterparty, if they gave one.

    Takes an already-computed merchant key rather than a description, so callers
    that own the fingerprinting can use this without depending on each other.
    """

    if not merchant_key:
        return None

    memory = (
        db.query(CashflowRoleMemory)
        .filter(
            CashflowRoleMemory.owner_id == owner_id,
            CashflowRoleMemory.merchant_key == merchant_key,
            CashflowRoleMemory.transaction_type == str(tx_type or "").strip().lower(),
        )
        .first()
    )
    return memory.role if memory else None
