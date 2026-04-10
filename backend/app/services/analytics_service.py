from __future__ import annotations

from datetime import date
import re
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Query, Session

from app.models import Transaction
from app.services.llm_service import generate_llm_assistant_response


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def month_bucket_expression(db: Session):
    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    if getattr(dialect_name, "name", None) == "sqlite":
        return func.strftime("%Y-%m", Transaction.date)
    return func.to_char(Transaction.date, "YYYY-MM")


def build_filtered_query(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> Query:
    query = db.query(Transaction).filter(Transaction.owner_id == user_id)
    month_expr = month_bucket_expression(db)

    parsed_start = parse_iso_date(start_date)
    parsed_end = parse_iso_date(end_date)

    if month:
        query = query.filter(month_expr == month)
    if parsed_start:
        query = query.filter(Transaction.date >= parsed_start)
    if parsed_end:
        query = query.filter(Transaction.date <= parsed_end)
    if transaction_type:
        query = query.filter(Transaction.type == transaction_type)
    if category:
        query = query.filter(Transaction.category == category)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return query


def get_summary(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> dict[str, float]:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    ).with_entities(
        func.coalesce(
            func.sum(case((Transaction.type == "income", Transaction.amount), else_=0.0)),
            0.0,
        ).label("total_income"),
        func.coalesce(
            func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0.0)),
            0.0,
        ).label("total_expenses"),
    )

    totals = query.one()
    total_income = float(totals.total_income or 0.0)
    total_expenses = float(totals.total_expenses or 0.0)

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": total_income - total_expenses,
    }


def get_category_breakdown(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    ).filter(Transaction.type == "expense")

    rows = (
        query.with_entities(
            Transaction.category.label("category"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    return [{"category": row.category, "total": float(row.total)} for row in rows]


def get_monthly_summary(
    db: Session,
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    query = build_filtered_query(
        db,
        user_id,
        month=None,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )

    month_expr = month_bucket_expression(db)

    rows = (
        query.with_entities(
            month_expr.label("month"),
            func.coalesce(
                func.sum(case((Transaction.type == "income", Transaction.amount), else_=0.0)),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0.0)),
                0.0,
            ).label("expenses"),
        )
        .group_by(month_expr)
        .order_by(month_expr)
        .all()
    )

    result = []
    for row in rows:
        income = float(row.income or 0.0)
        expenses = float(row.expenses or 0.0)
        result.append(
            {
                "month": row.month,
                "income": income,
                "expenses": expenses,
                "balance": income - expenses,
            }
        )
    return result


def get_recent_transactions(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
    limit: int = 5,
):
    return (
        build_filtered_query(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .all()
    )


def get_top_expense_categories(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    query = db.query(
        Transaction.category.label("category"),
        func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
    ).filter(
        Transaction.owner_id == user_id,
        Transaction.type == "expense",
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    rows = (
        query.group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
        .all()
    )

    return [{"category": row.category, "total": float(row.total)} for row in rows]


def get_transactions_for_category(
    db: Session,
    user_id: int,
    category: str,
    account_id: int | None = None,
    limit: int = 5,
) -> list[Transaction]:
    query = db.query(Transaction).filter(
        Transaction.owner_id == user_id,
        Transaction.category == category,
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .all()
    )


def get_top_categories_with_transactions(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    category_limit: int = 3,
    transaction_limit: int = 3,
) -> list[dict[str, Any]]:
    top_categories = get_top_expense_categories(
        db,
        user_id,
        account_id=account_id,
        limit=category_limit,
    )

    result = []
    for item in top_categories:
        txs = get_transactions_for_category(
            db,
            user_id,
            item["category"],
            account_id=account_id,
            limit=transaction_limit,
        )
        result.append(
            {
                "category": item["category"],
                "total": item["total"],
                "transactions": txs,
            }
        )

    return result


def get_top_expense_category(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any] | None:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    ).filter(Transaction.type == "expense")

    row = (
        query.with_entities(
            Transaction.category.label("category"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .first()
    )

    if not row:
        return None

    return {
        "category": row.category,
        "total": float(row.total),
    }


def build_financial_snapshot(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    summary = get_summary(db, user_id, account_id=account_id)
    monthly_summary = get_monthly_summary(db, user_id, account_id=account_id)
    top_category = get_top_expense_category(db, user_id, account_id=account_id)

    total_income = float(summary["total_income"])
    total_expenses = float(summary["total_expenses"])
    balance = float(summary["balance"])

    current_month = monthly_summary[-1]["month"] if monthly_summary else None
    previous_month = monthly_summary[-2]["month"] if len(monthly_summary) >= 2 else None

    current_month_expenses = monthly_summary[-1]["expenses"] if monthly_summary else 0.0
    previous_month_expenses = monthly_summary[-2]["expenses"] if len(monthly_summary) >= 2 else 0.0

    expense_change_percent = None
    if previous_month_expenses > 0:
        expense_change_percent = (
            (current_month_expenses - previous_month_expenses) / previous_month_expenses
        ) * 100

    top_category_name = top_category["category"] if top_category else None
    top_category_amount = float(top_category["total"]) if top_category else 0.0

    top_category_share_percent = None
    if total_expenses > 0 and top_category_amount > 0:
        top_category_share_percent = (top_category_amount / total_expenses) * 100

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": balance,
        "top_category": top_category_name,
        "top_category_amount": top_category_amount,
        "top_category_share_percent": top_category_share_percent,
        "current_month": current_month,
        "previous_month": previous_month,
        "current_month_expenses": current_month_expenses,
        "previous_month_expenses": previous_month_expenses,
        "expense_change_percent": expense_change_percent,
    }


def get_spending_insights(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)

    total_expenses = snapshot["total_expenses"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    top_category_share_percent = snapshot["top_category_share_percent"]
    current_month = snapshot["current_month"]
    current_month_expenses = snapshot["current_month_expenses"]
    previous_month_expenses = snapshot["previous_month_expenses"]
    expense_change_percent = snapshot["expense_change_percent"]

    if total_expenses == 0:
        return {
            "current_month": None,
            "current_month_expenses": 0.0,
            "previous_month_expenses": 0.0,
            "expense_change_percent": None,
            "top_category": None,
            "top_category_amount": 0.0,
            "top_category_share_percent": None,
            "insights": ["No expense data available yet."],
            "recommendations": ["Add more transactions to unlock spending insights."],
        }

    insights: list[str] = []
    recommendations: list[str] = []

    insights.append(
        f"Your latest expense month is {current_month} with ${current_month_expenses:.2f} in spending."
    )

    if previous_month_expenses > 0 and expense_change_percent is not None:
        if expense_change_percent > 0:
            insights.append(
                f"Spending is up by {expense_change_percent:.1f}% compared with the previous month."
            )
        elif expense_change_percent < 0:
            insights.append(
                f"Spending is down by {abs(expense_change_percent):.1f}% compared with the previous month."
            )
        else:
            insights.append("Spending is unchanged compared with the previous month.")

    insights.append(
        f"Your top expense category is {top_category} at ${top_category_amount:.2f}."
    )

    if top_category_share_percent is not None:
        insights.append(
            f"{top_category} represents {top_category_share_percent:.1f}% of all recorded expenses."
        )

    if top_category_share_percent is not None and top_category_share_percent >= 40:
        recommendations.append(
            f"{top_category} is dominating your spending. Review whether some of these costs can be reduced or planned better."
        )

    if expense_change_percent is not None and expense_change_percent >= 20:
        recommendations.append(
            "Your monthly spending increased noticeably. Review recent transactions for unusual or one-time costs."
        )

    if current_month_expenses > 0 and top_category_amount / current_month_expenses >= 0.3:
        recommendations.append(
            f"Start with {top_category}: even a small cut there could have the biggest impact on your budget."
        )

    if not recommendations:
        recommendations.append(
            "Your spending pattern looks relatively stable right now. Keep tracking consistently to unlock stronger recommendations."
        )

    return {
        "current_month": current_month,
        "current_month_expenses": current_month_expenses,
        "previous_month_expenses": previous_month_expenses,
        "expense_change_percent": expense_change_percent,
        "top_category": top_category,
        "top_category_amount": top_category_amount,
        "top_category_share_percent": top_category_share_percent,
        "insights": insights,
        "recommendations": recommendations,
    }


def get_overspending_alerts(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    monthly_summary = get_monthly_summary(db, user_id, account_id=account_id)
    monthly_breakdowns = {
        item["month"]: get_category_breakdown(
            db,
            user_id,
            month=item["month"],
            account_id=account_id,
        )
        for item in monthly_summary
    }

    if not monthly_summary:
        return {"current_month": None, "alerts": []}

    current = monthly_summary[-1]
    current_month = current["month"]
    current_total = current["expenses"]

    alerts: list[dict[str, str]] = []

    if len(monthly_summary) >= 2:
        previous = monthly_summary[-2]
        previous_total = previous["expenses"]

        if previous_total > 0:
            change_percent = ((current_total - previous_total) / previous_total) * 100

            if change_percent >= 25:
                alerts.append(
                    {
                        "level": "high",
                        "title": "Monthly spending spike",
                        "message": f"Your spending in {current_month} is up {change_percent:.1f}% compared with {previous['month']}.",
                    }
                )
            elif change_percent >= 15:
                alerts.append(
                    {
                        "level": "medium",
                        "title": "Monthly spending increase",
                        "message": f"Your spending in {current_month} is up {change_percent:.1f}% compared with {previous['month']}.",
                    }
                )

    current_categories = monthly_breakdowns.get(current_month, [])
    current_total_expenses = sum(item["total"] for item in current_categories)

    if current_total_expenses > 0:
        for item in current_categories:
            share = (item["total"] / current_total_expenses) * 100

            if share >= 45:
                alerts.append(
                    {
                        "level": "high",
                        "title": f"{item['category']} is dominating spending",
                        "message": f"{item['category']} makes up {share:.1f}% of your expenses in {current_month}.",
                    }
                )
            elif share >= 30:
                alerts.append(
                    {
                        "level": "medium",
                        "title": f"{item['category']} is a major spending category",
                        "message": f"{item['category']} makes up {share:.1f}% of your expenses in {current_month}.",
                    }
                )

    if not alerts:
        alerts.append(
            {
                "level": "low",
                "title": "No major overspending alert",
                "message": "Your latest spending pattern does not show a strong overspending signal right now.",
            }
        )

    return {"current_month": current_month, "alerts": alerts}


def get_category_trends(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    monthly_summary = get_monthly_summary(db, user_id, account_id=account_id)

    if not monthly_summary:
        return {
            "current_month": None,
            "previous_month": None,
            "top_increases": [],
            "top_decreases": [],
            "summary": ["No expense trend data available yet."],
        }

    if len(monthly_summary) < 2:
        return {
            "current_month": monthly_summary[-1]["month"],
            "previous_month": None,
            "top_increases": [],
            "top_decreases": [],
            "summary": ["At least two months of expense data are needed for category trend comparison."],
        }

    previous_month = monthly_summary[-2]["month"]
    current_month = monthly_summary[-1]["month"]

    previous_categories = {
        item["category"]: item["total"]
        for item in get_category_breakdown(
            db,
            user_id,
            month=previous_month,
            account_id=account_id,
        )
    }
    current_categories = {
        item["category"]: item["total"]
        for item in get_category_breakdown(
            db,
            user_id,
            month=current_month,
            account_id=account_id,
        )
    }

    all_categories = sorted(set(previous_categories.keys()) | set(current_categories.keys()))
    trend_items = []

    for category in all_categories:
        previous_amount = float(previous_categories.get(category, 0.0))
        current_amount = float(current_categories.get(category, 0.0))
        change_amount = current_amount - previous_amount

        change_percent = None
        if previous_amount > 0:
            change_percent = (change_amount / previous_amount) * 100

        trend_items.append(
            {
                "category": category,
                "current_amount": current_amount,
                "previous_amount": previous_amount,
                "change_amount": change_amount,
                "change_percent": change_percent,
            }
        )

    increases = sorted(
        [item for item in trend_items if item["change_amount"] > 0],
        key=lambda item: item["change_amount"],
        reverse=True,
    )[:5]

    decreases = sorted(
        [item for item in trend_items if item["change_amount"] < 0],
        key=lambda item: item["change_amount"],
    )[:5]

    summary: list[str] = []

    if increases:
        top_up = increases[0]
        summary.append(
            f"The biggest increase from {previous_month} to {current_month} was {top_up['category']}, up ${top_up['change_amount']:.2f}."
        )

    if decreases:
        top_down = decreases[0]
        summary.append(
            f"The biggest decrease from {previous_month} to {current_month} was {top_down['category']}, down ${abs(top_down['change_amount']):.2f}."
        )

    if not summary:
        summary.append(
            f"No category-level increase or decrease was detected between {previous_month} and {current_month}."
        )

    return {
        "current_month": current_month,
        "previous_month": previous_month,
        "top_increases": increases,
        "top_decreases": decreases,
        "summary": summary,
    }


def extract_recent_context(history: list[Any]) -> str:
    context_lines: list[str] = []

    for message in history[-8:]:
        role = getattr(message, "role", "").lower()
        content = getattr(message, "content", "").strip()

        if not content:
            continue

        if role == "user":
            context_lines.append(f"User: {content}")
        elif role == "assistant":
            context_lines.append(f"Assistant: {content}")

    return "\n".join(context_lines)


def format_currency(value: float) -> str:
    return f"${value:.2f}"


def normalize_text_for_matching(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def get_distinct_categories(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> list[str]:
    query = db.query(Transaction.category).filter(Transaction.owner_id == user_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    categories = {
        (row[0] or "").strip()
        for row in query.distinct().all()
        if row[0] and str(row[0]).strip()
    }

    return sorted(
        categories,
        key=lambda item: (-len(normalize_text_for_matching(item)), item.lower()),
    )


def detect_focus_category(
    question: str,
    context_text: str,
    categories: list[str],
) -> str | None:
    normalized_text = f" {normalize_text_for_matching(f'{context_text} {question}')} "

    for category in categories:
        normalized_category = normalize_text_for_matching(category)
        if not normalized_category:
            continue

        variants = {normalized_category}
        if normalized_category.endswith("ies") and len(normalized_category) > 3:
            variants.add(f"{normalized_category[:-3]}y")
        elif normalized_category.endswith("s") and len(normalized_category) > 1:
            variants.add(normalized_category[:-1])

        if any(f" {variant} " in normalized_text for variant in variants if variant):
            return category

    return None


def build_category_focus_snapshot(
    db: Session,
    user_id: int,
    category: str,
    snapshot: dict[str, Any],
    account_id: int | None = None,
) -> dict[str, Any]:
    overall_summary = get_summary(
        db,
        user_id,
        category=category,
        account_id=account_id,
    )
    focus_type = (
        "income"
        if overall_summary["total_income"] > overall_summary["total_expenses"]
        else "expense"
    )
    total_amount = (
        float(overall_summary["total_income"])
        if focus_type == "income"
        else float(overall_summary["total_expenses"])
    )

    current_month = snapshot.get("current_month")
    previous_month = snapshot.get("previous_month")

    current_summary = (
        get_summary(
            db,
            user_id,
            month=current_month,
            category=category,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if current_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )
    previous_summary = (
        get_summary(
            db,
            user_id,
            month=previous_month,
            category=category,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if previous_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )

    current_month_amount = (
        float(current_summary["total_income"])
        if focus_type == "income"
        else float(current_summary["total_expenses"])
    )
    previous_month_amount = (
        float(previous_summary["total_income"])
        if focus_type == "income"
        else float(previous_summary["total_expenses"])
    )

    change_amount = current_month_amount - previous_month_amount
    change_percent = None
    if previous_month_amount > 0:
        change_percent = (change_amount / previous_month_amount) * 100

    month_scope_summary = (
        get_summary(
            db,
            user_id,
            month=current_month,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if current_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )
    month_scope_total = (
        float(month_scope_summary["total_income"])
        if focus_type == "income"
        else float(month_scope_summary["total_expenses"])
    )
    current_share_percent = None
    if month_scope_total > 0 and current_month_amount > 0:
        current_share_percent = (current_month_amount / month_scope_total) * 100

    recent_transactions = get_transactions_for_category(
        db,
        user_id,
        category,
        account_id=account_id,
        limit=3,
    )

    return {
        "category": category,
        "transaction_type": focus_type,
        "total_amount": total_amount,
        "current_month": current_month,
        "previous_month": previous_month,
        "current_month_amount": current_month_amount,
        "previous_month_amount": previous_month_amount,
        "change_amount": change_amount,
        "change_percent": change_percent,
        "current_share_percent": current_share_percent,
        "recent_transactions": recent_transactions,
        "is_top_category": snapshot.get("top_category") == category,
    }


def build_category_focus_supporting_points(
    focus_snapshot: dict[str, Any],
) -> list[str]:
    category = focus_snapshot["category"]
    current_month = focus_snapshot["current_month"]
    previous_month = focus_snapshot["previous_month"]

    points = [
        f"{category} total in this scope: {format_currency(focus_snapshot['total_amount'])}",
    ]

    if current_month:
        points.append(
            f"{current_month}: {format_currency(focus_snapshot['current_month_amount'])}"
        )

    if previous_month and focus_snapshot["previous_month_amount"] > 0:
        direction = "up" if focus_snapshot["change_amount"] >= 0 else "down"
        points.append(
            f"Month-over-month: {direction} {format_currency(abs(focus_snapshot['change_amount']))} from {previous_month}"
        )

    if focus_snapshot["current_share_percent"] is not None:
        share_label = "income" if focus_snapshot["transaction_type"] == "income" else "spending"
        points.append(
            f"{category} makes up {focus_snapshot['current_share_percent']:.1f}% of current-month {share_label}"
        )

    if focus_snapshot["recent_transactions"]:
        recent_text = ", ".join(
            f"{tx.description} ({format_currency(tx.amount)})"
            for tx in focus_snapshot["recent_transactions"]
        )
        points.append(f"Recent matching transactions: {recent_text}")

    return points[:5]


def build_category_focus_answer(
    intent: str,
    mode: str,
    focus_snapshot: dict[str, Any],
    top_category: str | None,
) -> str:
    category = focus_snapshot["category"]
    total_amount = format_currency(focus_snapshot["total_amount"])
    current_month = focus_snapshot["current_month"]
    current_month_amount = format_currency(focus_snapshot["current_month_amount"])
    change_amount = focus_snapshot["change_amount"]
    change_percent = focus_snapshot["change_percent"]
    is_expense = focus_snapshot["transaction_type"] == "expense"
    recent_transactions = focus_snapshot["recent_transactions"]

    change_text = ""
    if current_month:
        change_text = f" In {current_month}, it is {current_month_amount}."
    if change_percent is not None:
        direction = "up" if change_amount >= 0 else "down"
        change_text += f" That is {direction} {abs(change_percent):.1f}% from the previous month."

    if intent == "category_transactions" or intent == "recent":
        recent_hint = (
            f" Recent items include {', '.join(tx.description for tx in recent_transactions[:2])}."
            if recent_transactions
            else ""
        )
        if mode == "strict":
            return f"{category} is where the detail is.{change_text or f' It totals {total_amount} in this scope.'}{recent_hint}"
        if mode == "coach":
            return f"{category} is a good place to zoom in.{change_text or f' It totals {total_amount} in this scope.'}{recent_hint}"
        return f"Here is the focused view for {category}. It totals {total_amount} in this scope.{change_text}{recent_hint}"

    if intent in {"saving_advice", "spending_change", "driver", "alerts"} and is_expense:
        if mode == "strict":
            return f"{category} is worth reviewing closely. It totals {total_amount} in this scope.{change_text}"
        if mode == "coach":
            return f"{category} looks like a practical place to focus. It totals {total_amount} in this scope.{change_text}"
        return f"{category} is a meaningful spending category here. It totals {total_amount} in this scope.{change_text}"

    if focus_snapshot["is_top_category"]:
        return f"{category} is currently your top category in this scope at {total_amount}.{change_text}"

    comparator = f" {top_category} is currently higher." if top_category and top_category != category else ""
    return f"{category} totals {total_amount} in this scope.{change_text}{comparator}"


def classify_question(question: str, context_text: str) -> str:
    text = f"{context_text} {question}".lower().strip()

    if any(
        phrase in text
        for phrase in [
            "should i review charts or transactions first",
            "charts or transactions first",
            "review charts or transactions",
            "what should i review first",
            "where should i start",
        ]
    ):
        return "review_path"

    if any(
        phrase in text
        for phrase in [
            "top 3",
            "top three",
            "biggest 3",
            "largest 3",
            "top categories",
            "where is my money going",
            "where does my money go",
        ]
    ):
        return "top_categories_multi"

    if any(
        phrase in text
        for phrase in [
            "their transactions",
            "show transactions",
            "show me transactions",
            "category transactions",
            "transactions for category",
        ]
    ):
        return "category_transactions"

    if any(word in text for word in ["balance", "left over", "how much do i have"]):
        return "balance"

    if any(word in text for word in ["top expense", "top category", "biggest category", "most spent"]):
        return "top_category"

    if any(word in text for word in ["increase", "decrease", "trend", "last month", "this month", "overspend", "spending change"]):
        return "spending_change"

    if any(word in text for word in ["save", "saving", "advice", "reduce", "cut spending", "budget"]):
        return "saving_advice"

    if any(word in text for word in ["summary", "summarize", "overview", "my finances"]):
        return "summary"

    if any(word in text for word in ["driving this", "which category", "what caused", "reason for increase"]):
        return "driver"

    if any(word in text for word in ["alert", "warning", "problem", "risk"]):
        return "alerts"

    if any(word in text for word in ["recent", "latest transactions", "last transactions"]):
        return "recent"

    if any(word in text for word in ["youtube", "google", "resource", "article", "learn more", "guide"]):
        return "education"

    return "general"


def build_assistant_actions(
    snapshot: dict[str, Any],
    intent: str,
    account_id: int | None = None,
    driver_category: str | None = None,
    focus_category: str | None = None,
    focus_transaction_type: str = "expense",
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    top_category = snapshot["top_category"]
    current_month = snapshot["current_month"]
    target_category = focus_category or driver_category or top_category
    target_transaction_type = focus_transaction_type if focus_category else "expense"
    target_label_suffix = "transactions" if target_transaction_type == "income" else "expenses"

    if intent == "balance":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
                "account_id": account_id,
            }
        )

    elif intent == "top_category":
        if target_category:
            actions.append(
                {
                    "label": f"Open {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )
            actions.append(
                {
                    "label": "View category ranking",
                    "page": "analytics",
                    "section": "categories",
                    "account_id": account_id,
                }
            )

    elif intent == "spending_change":
        actions.append(
            {
                "label": "Inspect overspending alerts",
                "page": "analytics",
                "section": "alerts",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "View category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

    elif intent == "saving_advice":
        actions.append(
            {
                "label": "Open spending insights",
                "page": "analytics",
                "section": "insights",
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} transactions",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )

    elif intent == "summary":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "View all transactions",
                "page": "transactions",
                "account_id": account_id,
            }
        )

    elif intent == "driver":
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Inspect {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

    elif intent == "alerts":
        actions.append(
            {
                "label": "Open overspending alerts",
                "page": "analytics",
                "section": "alerts",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )

    elif intent == "recent":
        if target_category:
            actions.append(
                {
                    "label": f"Open {target_category} transactions",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )
        else:
            actions.append(
                {
                    "label": "View all transactions",
                    "page": "transactions",
                    "account_id": account_id,
                }
            )

    elif intent == "general" and target_category:
        actions.append(
            {
                "label": f"Open {target_category} transactions",
                "page": "transactions",
                "category": target_category,
                "transaction_type": target_transaction_type,
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )

    return actions[:3]


def generate_mode_intro(mode: str) -> str:
    if mode == "strict":
        return "Strict view:"
    if mode == "coach":
        return "Coach view:"
    return ""


def generate_dynamic_followups(
    intent: str,
    mode: str,
    top_category: str | None,
    driver_category: str | None,
    focus_category: str | None = None,
) -> list[str]:
    if focus_category:
        return [
            f"Show me recent {focus_category} transactions",
            f"How has {focus_category} changed month to month?",
            f"How can I improve my {focus_category} spending?",
        ]

    if mode == "strict":
        if intent in {"spending_change", "driver", "alerts"}:
            return [
                "What should I cut first?",
                "Show me the transactions causing this.",
                f"Is {driver_category or top_category or 'this category'} the main problem?",
            ]
        return [
            "What is hurting my budget most?",
            "Where should I cut first?",
            "Show me the transactions behind this.",
        ]

    if mode == "coach":
        if intent in {"saving_advice", "summary"}:
            return [
                "What is one easy improvement I can make this week?",
                "Where can I save without feeling restricted?",
                "Show me the best place to start improving.",
            ]
        return [
            "What is one smart next step?",
            "Where can I improve gradually?",
            "Show me the best starting point.",
        ]

    if intent == "top_categories_multi":
        return [
            "Show me their transactions",
            "Which one is growing fastest?",
            "How can I reduce them?",
        ]
    if intent == "category_transactions":
        return [
            "Which category is driving my spending most?",
            "How can I reduce these expenses?",
            "Open those transactions",
        ]
    if intent == "spending_change":
        return [
            "What category caused the increase?",
            "Show me the recent transactions behind this.",
            "What should I review first?",
        ]
    if intent == "saving_advice":
        return [
            "Where should I start cutting back?",
            "Which category gives me the biggest savings opportunity?",
            "Show me the transactions I should review first.",
        ]
    return [
        "Show me my top 3 spending categories",
        "Show me their transactions",
        "Give me saving advice",
    ]


def build_driver_explanation(
    expense_change_percent: float | None,
    top_category: str | None,
    driver_category: str | None,
    recent_transactions: list[Any],
) -> list[str]:
    reasons: list[str] = []

    if expense_change_percent is not None:
        if expense_change_percent > 0:
            reasons.append(f"overall expenses increased by {expense_change_percent:.1f}%")
        elif expense_change_percent < 0:
            reasons.append(f"overall expenses decreased by {abs(expense_change_percent):.1f}%")

    if driver_category:
        reasons.append(f"{driver_category} appears to be the fastest-growing category")
    elif top_category:
        reasons.append(f"{top_category} is currently the biggest spending category")

    if recent_transactions:
        recent_labels = ", ".join(tx.description for tx in recent_transactions[:2])
        if recent_labels:
            reasons.append(f"recent transactions such as {recent_labels} may be contributing")

    return reasons


def generate_assistant_response(
    db: Session,
    user_id: int,
    question: str,
    history: list[Any] | None = None,
    mode: str = "balanced",
    account_id: int | None = None,
    scope_label: str = "All accounts combined",
) -> dict[str, Any]:
    history = history or []
    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)
    snapshot["scope_label"] = scope_label
    category_trends = get_category_trends(db, user_id, account_id=account_id)
    overspending_alerts = get_overspending_alerts(db, user_id, account_id=account_id)
    recent_transactions = get_recent_transactions(
        db,
        user_id,
        account_id=account_id,
        limit=5,
    )

    q = (question or "").strip().lower()
    context_text = extract_recent_context(history)
    intent = classify_question(q, context_text)
    focus_category = detect_focus_category(
        question=question,
        context_text=context_text,
        categories=get_distinct_categories(db, user_id, account_id=account_id),
    )
    if focus_category and "transaction" in q:
        intent = "category_transactions"

    total_income = snapshot["total_income"]
    total_expenses = snapshot["total_expenses"]
    balance = snapshot["balance"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    top_category_share_percent = snapshot["top_category_share_percent"]
    current_month = snapshot["current_month"]
    expense_change_percent = snapshot["expense_change_percent"]

    primary_driver = None
    if category_trends.get("top_increases"):
        primary_driver = category_trends["top_increases"][0]["category"]

    focus_snapshot = (
        build_category_focus_snapshot(
            db,
            user_id,
            focus_category,
            snapshot,
            account_id=account_id,
        )
        if focus_category
        else None
    )

    llm_result = generate_llm_assistant_response(
        question=question,
        conversation_context=context_text,
        snapshot=snapshot,
        category_trends=category_trends,
        overspending_alerts=overspending_alerts,
        recent_transactions=recent_transactions,
        focus_category_context=focus_snapshot,
        mode=mode,
    )

    if llm_result:
        suggested_actions = []

        action_type = llm_result.get("action_type", "none")
        action_label = llm_result.get("action_label")
        action_target = llm_result.get("action_target")

        if action_type == "transactions":
            suggested_actions.append(
                {
                    "label": action_label or "Review transactions",
                    "page": "transactions",
                    "category": (
                        action_target
                        if action_target and action_target.lower() != "none"
                        else focus_category or primary_driver or top_category
                    ),
                    "transaction_type": (
                        focus_snapshot["transaction_type"]
                        if focus_snapshot
                        else "expense"
                    ),
                    "month": current_month,
                    "account_id": account_id,
                }
            )

        elif action_type == "dashboard":
            suggested_actions.append(
                {
                    "label": action_label or "Open dashboard",
                    "page": "dashboard",
                    "account_id": account_id,
                }
            )

        elif action_type == "analytics":
            target_section = "insights"
            if action_target:
                lower_target = action_target.lower()
                if "alert" in lower_target:
                    target_section = "alerts"
                elif "trend" in lower_target:
                    target_section = "trends"
                elif "month" in lower_target or "summary" in lower_target:
                    target_section = "monthly"
                elif "categor" in lower_target:
                    target_section = "categories"

            suggested_actions.append(
                {
                    "label": action_label or "Open analytics",
                    "page": "analytics",
                    "section": target_section,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

        elif action_type == "external_resource":
            suggested_actions.append(
                {
                    "label": action_label or "Explore learning resources",
                    "page": "external_resource",
                    "section": action_target or "budgeting basics",
                    "account_id": account_id,
                }
            )

        followups = llm_result["suggested_followups"] or generate_dynamic_followups(
            intent=intent,
            mode=mode,
            top_category=top_category,
            driver_category=primary_driver,
            focus_category=focus_category,
        )

        return {
            "answer": llm_result["answer"],
            "supporting_points": llm_result["supporting_points"],
            "suggested_followups": followups,
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    if total_income == 0 and total_expenses == 0:
        answer = "I do not have enough financial activity yet to give a meaningful answer."
        intro = generate_mode_intro(mode)
        final_answer = f"{intro} {answer}".strip() if intro else answer

        return {
            "answer": final_answer,
            "supporting_points": [
                "No recorded income found yet.",
                "No recorded expenses found yet.",
            ],
            "suggested_followups": generate_dynamic_followups(
                intent="general",
                mode=mode,
                top_category=None,
                driver_category=None,
                focus_category=focus_category,
            ),
            "suggested_actions": [],
            "scope_label": scope_label,
        }

    if not q:
        answer = "Ask me about your balance, top categories, transactions, spending trends, saving ideas, alerts, and financial summaries."
        intro = generate_mode_intro(mode)
        final_answer = f"{intro} {answer}".strip() if intro else answer

        return {
            "answer": final_answer,
            "supporting_points": [],
            "suggested_followups": generate_dynamic_followups(
                intent="general",
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [],
            "scope_label": scope_label,
        }

    if focus_snapshot and intent in {
        "category_transactions",
        "recent",
        "saving_advice",
        "spending_change",
        "driver",
        "alerts",
        "top_category",
        "general",
        "summary",
    }:
        return {
            "answer": build_category_focus_answer(
                intent=intent,
                mode=mode,
                focus_snapshot=focus_snapshot,
                top_category=top_category,
            ),
            "supporting_points": build_category_focus_supporting_points(focus_snapshot),
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent="recent" if intent == "category_transactions" else intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                focus_transaction_type=focus_snapshot["transaction_type"],
            ),
            "scope_label": scope_label,
        }

    if intent == "top_categories_multi":
        top_three = get_top_expense_categories(
            db,
            user_id,
            account_id=account_id,
            limit=3,
        )

        if not top_three:
            answer = "I do not have enough expense data yet to identify your top categories."
            intro = generate_mode_intro(mode)
            final_answer = f"{intro} {answer}".strip() if intro else answer

            return {
                "answer": final_answer,
                "supporting_points": [],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [],
                "scope_label": scope_label,
            }

        points = [
            f"{idx + 1}. {item['category']} — {format_currency(item['total'])}"
            for idx, item in enumerate(top_three)
        ]

        if mode == "strict":
            answer = "These categories are taking the biggest share of your money. If you want results, start here."
        elif mode == "coach":
            answer = "These are your top spending categories. They are the best places to look for realistic savings."
        else:
            answer = "These are your top spending categories ranked by total expense amount."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "View all transactions",
                    "page": "transactions",
                }
            ],
            "scope_label": scope_label,
        }

    if intent == "category_transactions":
        top_with_transactions = get_top_categories_with_transactions(
            db,
            user_id,
            account_id=account_id,
            category_limit=3,
            transaction_limit=2,
        )

        if not top_with_transactions:
            answer = "I do not have enough category transaction data yet."
            intro = generate_mode_intro(mode)
            final_answer = f"{intro} {answer}".strip() if intro else answer

            return {
                "answer": final_answer,
                "supporting_points": [],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [],
                "scope_label": scope_label,
            }

        points = []
        for item in top_with_transactions:
            tx_text = ", ".join(
                f"{tx.description} ({format_currency(tx.amount)})"
                for tx in item["transactions"]
            ) or "No recent transactions"
            points.append(
                f"{item['category']} — {format_currency(item['total'])}. Recent items: {tx_text}"
            )

        if mode == "strict":
            answer = "These transactions show where your money is actually going. Review them before looking at charts."
        elif mode == "coach":
            answer = "These transactions help explain your biggest categories. This is a good place to find practical improvements."
        else:
            answer = "Here are the recent transactions inside your biggest expense categories."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "Open transactions",
                    "page": "transactions",
                }
            ],
            "scope_label": scope_label,
        }

    if intent in {"spending_change", "driver", "alerts", "saving_advice", "summary", "balance", "top_category", "general"}:
        driver_reasons = build_driver_explanation(
            expense_change_percent=expense_change_percent,
            top_category=top_category,
            driver_category=primary_driver,
            recent_transactions=recent_transactions,
        )

        if mode == "strict":
            if intent == "saving_advice":
                answer = (
                    f"The clearest weakness is {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "That is where you should cut first if you want meaningful improvement."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The main issue looks straightforward: "
                    + (driver_reasons[0] if driver_reasons else "your spending pattern is under pressure")
                    + "."
                )
            else:
                answer = (
                    f"Your balance is {format_currency(balance)}, and the biggest pressure point is "
                    f"{top_category or 'your top expense area'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )

        elif mode == "coach":
            if intent == "saving_advice":
                answer = (
                    f"The best opportunity right now is {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "A small improvement there could make a noticeable difference."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The strongest signal right now is "
                    + (driver_reasons[0] if driver_reasons else "a change in your recent spending pattern")
                    + ", which gives us a clear place to start."
                )
            else:
                answer = (
                    f"You currently have {format_currency(balance)} available, and your biggest spending pressure is "
                    f"{top_category or 'your top expense area'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "That gives us a clear next step."
                )
        else:
            if intent == "saving_advice":
                answer = (
                    f"The biggest savings opportunity appears to be {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The likely driver is "
                    + (driver_reasons[0] if driver_reasons else "your recent expense pattern")
                    + "."
                )
            else:
                answer = (
                    f"Your balance is {format_currency(balance)}, and your top expense category is "
                    f"{top_category or 'N/A'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )

        supporting_points = [
            f"Balance: {format_currency(balance)}",
            f"Total income: {format_currency(total_income)}",
            f"Total expenses: {format_currency(total_expenses)}",
        ]

        if top_category:
            supporting_points.append(
                f"Top expense category: {top_category} at {format_currency(top_category_amount)}"
            )

        if top_category_share_percent is not None:
            supporting_points.append(
                f"{top_category} represents {top_category_share_percent:.1f}% of all expenses"
            )

        if expense_change_percent is not None:
            supporting_points.append(
                f"Latest monthly expense change: {expense_change_percent:.1f}%"
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent=intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                focus_transaction_type=focus_snapshot["transaction_type"] if focus_snapshot else "expense",
            ),
            "scope_label": scope_label,
        }

    return {
        "answer": "I can help with your balance, top categories, transactions, spending trends, saving ideas, alerts, and summaries.",
        "supporting_points": [
            f"Balance: {format_currency(balance)}",
            f"Top expense category: {top_category or 'N/A'}",
        ],
        "suggested_followups": generate_dynamic_followups(
            intent="general",
            mode=mode,
            top_category=top_category,
            driver_category=primary_driver,
            focus_category=focus_category,
        ),
        "suggested_actions": [],
        "scope_label": scope_label,
    }


def generate_assistant_suggestions(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> list[str]:
    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)
    category_trends = get_category_trends(db, user_id, account_id=account_id)

    suggestions: list[str] = ["What is my balance?"]

    if snapshot["top_category"]:
        suggestions.append(f"Why is {snapshot['top_category']} my top expense category?")
        suggestions.append(f"How can I reduce {snapshot['top_category']} spending?")

    if category_trends.get("top_increases"):
        suggestions.append(
            f"Why did my {category_trends['top_increases'][0]['category']} spending increase?"
        )

    if snapshot["expense_change_percent"] is not None:
        if snapshot["expense_change_percent"] > 0:
            suggestions.append("Why did my spending increase?")
        elif snapshot["expense_change_percent"] < 0:
            suggestions.append("Why did my spending decrease?")

    if snapshot["current_month"]:
        suggestions.append(f"Summarize my finances for {snapshot['current_month']}")

    suggestions.append("Show my recent transactions")
    suggestions.append("Give me saving advice")

    unique_suggestions: list[str] = []
    for item in suggestions:
        if item not in unique_suggestions:
            unique_suggestions.append(item)

    return unique_suggestions[:7]


def get_dashboard_payload(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    return {
        "summary": get_summary(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "top_category": get_top_expense_category(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "category_breakdown": get_category_breakdown(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "monthly_summary": get_monthly_summary(
            db,
            user_id,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "recent_transactions": get_recent_transactions(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "spending_insights": get_spending_insights(db, user_id, account_id=account_id),
        "overspending_alerts": get_overspending_alerts(
            db,
            user_id,
            account_id=account_id,
        ),
        "category_trends": get_category_trends(db, user_id, account_id=account_id),
    }
