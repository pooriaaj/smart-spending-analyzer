from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CategoryMemory, MerchantCategoryProfile, Transaction
from app.services.analytics_service import (
    get_category_breakdown,
    get_recurring_expense_patterns,
    get_summary,
)
from app.services.transaction_service import (
    UNCATEGORIZED_VALUES,
    categorize_transaction_details,
    get_uncategorized_candidates,
    merchant_profile_table_available,
)


def get_money_map_transactions(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> list[Transaction]:
    query = db.query(Transaction).filter(Transaction.owner_id == user_id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    return query.order_by(Transaction.date.asc(), Transaction.id.asc()).all()


def get_money_map_confidence_level(score: float) -> str:
    if score >= 0.72:
        return "High"
    if score >= 0.42:
        return "Medium"
    return "Low"


def build_money_map_confidence(
    *,
    transaction_count: int,
    month_count: int,
    categorized_ratio: float,
    learned_merchant_count: int,
) -> float:
    if transaction_count <= 0:
        return 0.0

    score = 0.18
    score += min(month_count, 3) * 0.16
    score += min(transaction_count, 60) / 60 * 0.2
    score += categorized_ratio * 0.22
    score += min(learned_merchant_count, 20) / 20 * 0.18
    return round(min(score, 0.98), 2)


def build_money_map_narrative(
    *,
    transaction_count: int,
    month_count: int,
    confidence_level: str,
    top_category: dict[str, Any] | None,
    recurring_count: int,
    uncategorized_count: int,
) -> str:
    if transaction_count <= 0:
        return (
            "Upload one bank statement to build your first Money Map. The app will learn "
            "merchant patterns, detect recurring bills, and turn the statement into budgets "
            "and simulator assumptions."
        )

    category_text = (
        f" Your biggest expense category is {top_category['category']}."
        if top_category
        else ""
    )
    recurring_text = (
        f" I found {recurring_count} recurring pattern{'s' if recurring_count != 1 else ''} worth tracking."
        if recurring_count > 0
        else " Add more statement history to unlock recurring bill detection."
    )
    review_text = (
        f" {uncategorized_count} transaction{'s' if uncategorized_count != 1 else ''} still need category review."
        if uncategorized_count > 0
        else " Category coverage looks clean so far."
    )

    return (
        f"Money Map confidence is {confidence_level.lower()} from {transaction_count} transaction"
        f"{'s' if transaction_count != 1 else ''} across {month_count} month"
        f"{'s' if month_count != 1 else ''}.{category_text}{recurring_text}{review_text}"
    )


def build_money_map_actions(
    *,
    transaction_count: int,
    month_count: int,
    uncategorized_count: int,
    recurring_count: int,
) -> list[dict[str, str]]:
    if transaction_count <= 0:
        return [
            {
                "label": "Upload a statement",
                "detail": "Fastest way to build a personalized Money Map from real history.",
                "page": "import",
                "priority": "high",
            },
            {
                "label": "Add one transaction manually",
                "detail": "Useful for testing the learning system before importing a full statement.",
                "page": "dashboard",
                "priority": "medium",
            },
        ]

    actions: list[dict[str, str]] = []
    if uncategorized_count > 0:
        actions.append(
            {
                "label": "Review category guesses",
                "detail": "Confirming uncertain categories teaches the app your naming habits.",
                "page": "transactions",
                "priority": "high",
            }
        )
    if month_count < 3:
        actions.append(
            {
                "label": "Upload more history",
                "detail": "Two to three months of statements makes simulator and recurring detection stronger.",
                "page": "import",
                "priority": "high" if month_count <= 1 else "medium",
            }
        )
    if recurring_count > 0:
        actions.append(
            {
                "label": "Simulate recurring cuts",
                "detail": "Turn detected subscriptions and repeat charges into future balance scenarios.",
                "page": "simulator",
                "priority": "medium",
            }
        )
    actions.append(
        {
            "label": "Build starter budgets",
            "detail": "Use the learned spending map as the starting point for monthly targets.",
            "page": "budgets",
            "priority": "medium",
        }
    )
    return actions[:4]


def get_money_map_payload(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    *,
    scope_label: str = "All accounts combined",
) -> dict[str, Any]:
    transactions = get_money_map_transactions(db, user_id, account_id=account_id)
    transaction_count = len(transactions)
    month_count = len({item.date.strftime("%Y-%m") for item in transactions})
    uncategorized_count = sum(
        1 for item in transactions if str(item.category or "").lower() in UNCATEGORIZED_VALUES
    )
    categorized_ratio = (
        (transaction_count - uncategorized_count) / transaction_count
        if transaction_count > 0
        else 0.0
    )

    memory_query = db.query(CategoryMemory).filter(CategoryMemory.owner_id == user_id)
    can_use_merchant_profiles = merchant_profile_table_available(db)
    merchant_query = (
        db.query(MerchantCategoryProfile).filter(MerchantCategoryProfile.owner_id == user_id)
        if can_use_merchant_profiles
        else None
    )
    if account_id is not None:
        transaction_ids = [item.id for item in transactions]
        # Category memories are user-level, but merchant profiles are learned from the
        # user's confirmed transactions. Keep counts user-level when the scope has no rows.
        if transaction_ids and merchant_query is not None:
            merchant_keys = {
                profile.merchant_key
                for profile in merchant_query.all()
                if any(profile.merchant_key in item.description.lower() for item in transactions)
            }
            learned_merchant_count = len(merchant_keys)
        else:
            learned_merchant_count = 0
    else:
        learned_merchant_count = merchant_query.count() if merchant_query is not None else 0

    memory_count = memory_query.count()
    confidence_score = build_money_map_confidence(
        transaction_count=transaction_count,
        month_count=month_count,
        categorized_ratio=categorized_ratio,
        learned_merchant_count=learned_merchant_count,
    )
    confidence_level = get_money_map_confidence_level(confidence_score)
    summary = get_summary(db, user_id, account_id=account_id)

    raw_categories = get_category_breakdown(db, user_id, account_id=account_id)
    total_expenses = sum(float(item["total"] or 0.0) for item in raw_categories)
    top_categories = [
        {
            "category": item["category"],
            "total": round(float(item["total"] or 0.0), 2),
            "share_percent": round((float(item["total"] or 0.0) / total_expenses) * 100, 1)
            if total_expenses > 0
            else 0.0,
        }
        for item in raw_categories[:6]
    ]

    recurring_patterns = get_recurring_expense_patterns(
        db,
        user_id,
        account_id=account_id,
        limit=4,
    )
    uncategorized_candidates = get_uncategorized_candidates(
        db,
        user_id,
        account_id=account_id,
    )[:6]
    category_suggestions = []
    for transaction in uncategorized_candidates:
        decision = categorize_transaction_details(
            db=db,
            owner_id=user_id,
            description=transaction.description,
            tx_type=transaction.type,
        )
        if decision.source == "fallback":
            continue
        category_suggestions.append(
            {
                "description": transaction.description,
                "current_category": transaction.category,
                "suggested_category": decision.category,
                "confidence": decision.confidence,
                "source": decision.source,
                "matched_keyword": decision.matched_keyword,
                "reason": decision.reason,
            }
        )

    learning_signals = [
        {
            "label": "History depth",
            "value": f"{month_count} month{'s' if month_count != 1 else ''}",
            "detail": "Two to three months makes forecasts and recurring detection much stronger.",
            "severity": "positive" if month_count >= 3 else "watch",
        },
        {
            "label": "Learned merchants",
            "value": str(learned_merchant_count),
            "detail": "Confirmed merchant patterns help the app use your personal category language.",
            "severity": "positive" if learned_merchant_count >= 5 else "info",
        },
        {
            "label": "Category review",
            "value": str(uncategorized_count),
            "detail": "Uncategorized rows are the best teaching opportunities for the Money Map.",
            "severity": "watch" if uncategorized_count else "positive",
        },
    ]

    top_category = top_categories[0] if top_categories else None
    status = "empty" if transaction_count == 0 else "learning" if confidence_score < 0.72 else "mapped"

    return {
        "scope_label": scope_label,
        "status": status,
        "confidence_level": confidence_level,
        "confidence_score": confidence_score,
        "transaction_count": transaction_count,
        "month_count": month_count,
        "learned_merchant_count": learned_merchant_count,
        "memory_count": memory_count,
        "uncategorized_count": uncategorized_count,
        "summary": summary,
        "top_categories": top_categories,
        "recurring_highlights": [
            {
                "description": item["description"],
                "category": item["category"],
                "average_amount": item["average_amount"],
                "annualized_amount": item["annualized_amount"],
                "review_priority": item["review_priority"],
                "review_reason": item["review_reason"],
            }
            for item in recurring_patterns
        ],
        "category_suggestions": category_suggestions,
        "learning_signals": learning_signals,
        "actions": build_money_map_actions(
            transaction_count=transaction_count,
            month_count=month_count,
            uncategorized_count=uncategorized_count,
            recurring_count=len(recurring_patterns),
        ),
        "narrative": build_money_map_narrative(
            transaction_count=transaction_count,
            month_count=month_count,
            confidence_level=confidence_level,
            top_category=top_category,
            recurring_count=len(recurring_patterns),
            uncategorized_count=uncategorized_count,
        ),
    }
