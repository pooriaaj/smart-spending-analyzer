from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import CashflowRoleMemory, Transaction
from app.services.cashflow_rules import (
    ambiguous_transfer_filter,
    expense_amount_expression,
    income_amount_expression,
    normalize_cashflow_role,
    pending_cashflow_review_filter,
    recall_role_for_merchant,
)
from app.services.transaction_service import (
    counterparty_fingerprint,
    recall_learned_cashflow_role,
)

logger = logging.getLogger(__name__)


REVIEW_LIMIT = 200
# How many rows one answer may reclassify. High enough to settle years of a
# recurring counterparty in one click, low enough that a bad fingerprint match
# cannot quietly rewrite an entire history.
SIMILAR_APPLY_LIMIT = 500


def recall_cashflow_role(
    db: Session,
    owner_id: int,
    description: str | None,
    tx_type: str | None,
) -> str | None:
    """The owner's standing answer for this counterparty, if they gave one."""

    fingerprint = counterparty_fingerprint(description)
    if not fingerprint:
        return None
    return recall_role_for_merchant(db, owner_id, fingerprint[0], tx_type)


def remember_cashflow_role(
    db: Session,
    owner_id: int,
    description: str | None,
    tx_type: str | None,
    role: str | None,
) -> bool:
    """Store the answer so this counterparty is never asked about again.

    Clearing an answer forgets the rule too, otherwise the row would be handed
    back to the automatic pass and immediately reclassified from memory.
    """

    fingerprint = counterparty_fingerprint(description)
    if not fingerprint:
        return False

    merchant_key, display_name = fingerprint
    normalized_type = str(tx_type or "").strip().lower()

    memory = (
        db.query(CashflowRoleMemory)
        .filter(
            CashflowRoleMemory.owner_id == owner_id,
            CashflowRoleMemory.merchant_key == merchant_key,
            CashflowRoleMemory.transaction_type == normalized_type,
        )
        .first()
    )

    if role is None:
        if memory is None:
            return False
        db.delete(memory)
        return True

    if memory is None:
        db.add(
            CashflowRoleMemory(
                merchant_key=merchant_key,
                display_name=display_name,
                transaction_type=normalized_type,
                role=role,
                confirmation_count=1,
                owner_id=owner_id,
            )
        )
        return True

    memory.display_name = display_name
    memory.confirmation_count = int(memory.confirmation_count or 0) + 1
    if memory.role != role:
        memory.role = role
    return True


def apply_cashflow_role_to_similar(
    db: Session,
    owner_id: int,
    description: str | None,
    tx_type: str | None,
    role: str | None,
    exclude_transaction_ids: set[int] | None = None,
) -> int:
    """Give every other unanswered transfer from this counterparty the same answer.

    Only rows the owner has not personally answered are touched. An earlier
    deliberate choice on one transfer must survive a later choice on another.
    """

    fingerprint = counterparty_fingerprint(description)
    if not fingerprint:
        return 0

    merchant_key = fingerprint[0]
    normalized_type = str(tx_type or "").strip().lower()
    skip_ids = exclude_transaction_ids or set()

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.owner_id == owner_id,
            Transaction.type == normalized_type,
            Transaction.cashflow_role.is_(None),
            ambiguous_transfer_filter(),
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(SIMILAR_APPLY_LIMIT)
        .all()
    )

    updated_count = 0
    for transaction in candidates:
        if transaction.id in skip_ids:
            continue

        transaction_fingerprint = counterparty_fingerprint(transaction.description)
        if not transaction_fingerprint or transaction_fingerprint[0] != merchant_key:
            continue

        transaction.cashflow_role = role
        updated_count += 1

    return updated_count


def count_similar_pending_transfers(
    db: Session,
    owner_id: int,
    description: str | None,
    tx_type: str | None,
) -> int:
    """How many other transfers the same answer would settle."""

    fingerprint = counterparty_fingerprint(description)
    if not fingerprint:
        return 0

    merchant_key = fingerprint[0]
    candidates = (
        db.query(Transaction.id, Transaction.description)
        .filter(
            Transaction.owner_id == owner_id,
            Transaction.type == str(tx_type or "").strip().lower(),
            Transaction.cashflow_role.is_(None),
            ambiguous_transfer_filter(),
        )
        .limit(SIMILAR_APPLY_LIMIT)
        .all()
    )

    return sum(
        1
        for candidate in candidates
        if (candidate_fingerprint := counterparty_fingerprint(candidate.description))
        and candidate_fingerprint[0] == merchant_key
    )


def list_transfers_awaiting_decision(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
    include_answered: bool = False,
    limit: int = REVIEW_LIMIT,
) -> dict:
    """The transfers the app deliberately refuses to classify on its own.

    A bank statement prints the same words for a paycheque paid by e-Transfer, a
    friend settling an old debt, and the owner moving their own savings. Only the
    owner can tell those apart, so they are listed here instead of being guessed at.
    """

    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    query = query.filter(
        ambiguous_transfer_filter() if include_answered else pending_cashflow_review_filter()
    )

    totals = query.with_entities(
        func.coalesce(func.sum(income_amount_expression()), 0.0).label("income_amount"),
        func.coalesce(func.sum(expense_amount_expression()), 0.0).label("expense_amount"),
        func.count(Transaction.id).label("total"),
    ).one()

    transactions = (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(max(1, min(int(limit or REVIEW_LIMIT), REVIEW_LIMIT)))
        .all()
    )

    items = []
    for transaction in transactions:
        fingerprint = counterparty_fingerprint(transaction.description)
        similar_count = (
            count_similar_pending_transfers(
                db,
                owner_id,
                transaction.description,
                transaction.type,
            )
            if fingerprint
            else 0
        )
        items.append(
            {
                "id": transaction.id,
                "amount": float(transaction.amount or 0.0),
                "category": transaction.category,
                "description": transaction.description,
                "date": transaction.date,
                "type": transaction.type,
                "cashflow_role": transaction.cashflow_role,
                "account_id": transaction.account_id,
                "counterparty": fingerprint[1] if fingerprint else None,
                # Includes this row, so the UI can offer "answer all 4 at once".
                "similar_pending_count": similar_count,
            }
        )

    return {
        "items": items,
        "total": int(totals.total or 0),
        "pending_income_amount": float(totals.income_amount or 0.0),
        "pending_expense_amount": float(totals.expense_amount or 0.0),
    }


def set_cashflow_role(
    db: Session,
    owner_id: int,
    transaction_ids: list[int],
    role: str | None,
    apply_to_similar: bool = True,
) -> dict:
    """Record what the owner says these rows were, and learn from the answer.

    Clearing an answer stays scoped to the named rows. It forgets the rule, so
    nothing new is classified from it, but it leaves other rows alone: there is
    no way to tell which of them were auto-applied and which the owner chose
    one by one, and silently undoing a deliberate choice is the worse mistake.
    """

    normalized_role = normalize_cashflow_role(role)
    unique_ids = {int(value) for value in transaction_ids or []}
    if not unique_ids:
        return {"updated_count": 0, "similar_updated_count": 0, "counterparties": []}

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.owner_id == owner_id,
            Transaction.id.in_(tuple(unique_ids)),
        )
        .all()
    )
    if not transactions:
        return {"updated_count": 0, "similar_updated_count": 0, "counterparties": []}

    answered_ids = {transaction.id for transaction in transactions}
    counterparties: list[str] = []
    similar_updated_count = 0

    for transaction in transactions:
        transaction.cashflow_role = normalized_role

        fingerprint = counterparty_fingerprint(transaction.description)
        if not fingerprint:
            continue

        remember_cashflow_role(
            db=db,
            owner_id=owner_id,
            description=transaction.description,
            tx_type=transaction.type,
            role=normalized_role,
        )
        if fingerprint[1] not in counterparties:
            counterparties.append(fingerprint[1])

        if apply_to_similar and normalized_role is not None:
            similar_updated_count += apply_cashflow_role_to_similar(
                db=db,
                owner_id=owner_id,
                description=transaction.description,
                tx_type=transaction.type,
                role=normalized_role,
                exclude_transaction_ids=answered_ids,
            )

    db.commit()
    logger.info(
        "Cashflow role %s applied to %d transaction(s) and %d similar row(s) for owner %s",
        normalized_role or "cleared",
        len(transactions),
        similar_updated_count,
        owner_id,
    )

    return {
        "updated_count": len(transactions),
        "similar_updated_count": similar_updated_count,
        "counterparties": counterparties,
    }


# The route layer creates transactions too, and reaches for the same rule the CSV
# importer uses. Named for the caller's intent rather than re-implemented.
resolve_imported_cashflow_role = recall_learned_cashflow_role
