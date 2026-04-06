from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Query, Session

from app.models import Transaction
from app.services.llm_service import generate_llm_assistant_response


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def build_filtered_query(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
) -> Query:
    query = db.query(Transaction).filter(Transaction.owner_id == user_id)

    parsed_start = parse_iso_date(start_date)
    parsed_end = parse_iso_date(end_date)

    if month:
        query = query.filter(func.to_char(Transaction.date, "YYYY-MM") == month)
    if parsed_start:
        query = query.filter(Transaction.date >= parsed_start)
    if parsed_end:
        query = query.filter(Transaction.date <= parsed_end)
    if transaction_type:
        query = query.filter(Transaction.type == transaction_type)
    if category:
        query = query.filter(Transaction.category == category)

    return query


def get_summary(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
) -> dict[str, float]:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
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
) -> list[dict[str, Any]]:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
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
) -> list[dict[str, Any]]:
    query = build_filtered_query(
        db,
        user_id,
        month=None,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
    )

    month_expr = func.to_char(Transaction.date, "YYYY-MM")

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
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .all()
    )


def get_top_expense_categories(
    db: Session,
    user_id: int,
    limit: int = 3,
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            Transaction.category.label("category"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
        )
        .filter(
            Transaction.owner_id == user_id,
            Transaction.type == "expense",
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
        .all()
    )

    return [{"category": row.category, "total": float(row.total)} for row in rows]


def get_transactions_for_category(
    db: Session,
    user_id: int,
    category: str,
    limit: int = 5,
) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(
            Transaction.owner_id == user_id,
            Transaction.category == category,
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .all()
    )


def get_top_categories_with_transactions(
    db: Session,
    user_id: int,
    category_limit: int = 3,
    transaction_limit: int = 3,
) -> list[dict[str, Any]]:
    top_categories = get_top_expense_categories(db, user_id, limit=category_limit)

    result = []
    for item in top_categories:
        txs = get_transactions_for_category(
            db,
            user_id,
            item["category"],
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


def suggest_external_resource_topic(
    question: str,
    balance: float,
    expense_change_percent: float | None,
    top_category: str | None,
) -> str | None:
    q = (question or "").lower()

    if any(word in q for word in ["learn", "how do i start", "beginner", "budget basics"]):
        return "budgeting basics"

    if any(word in q for word in ["debt", "credit card", "loan"]):
        return "debt reduction basics"

    if balance < 0:
        return "how to recover from overspending"

    if expense_change_percent is not None and expense_change_percent > 20:
        return "how to control monthly spending"

    if top_category:
        return f"how to reduce {top_category} spending"

    return None


def get_top_expense_category(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
) -> dict[str, Any] | None:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
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


def build_financial_snapshot(db: Session, user_id: int) -> dict[str, Any]:
    summary = get_summary(db, user_id)
    monthly_summary = get_monthly_summary(db, user_id)
    top_category = get_top_expense_category(db, user_id)

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


def get_spending_insights(db: Session, user_id: int) -> dict[str, Any]:
    snapshot = build_financial_snapshot(db, user_id)

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


def get_overspending_alerts(db: Session, user_id: int) -> dict[str, Any]:
    monthly_summary = get_monthly_summary(db, user_id)
    monthly_breakdowns = {
        item["month"]: get_category_breakdown(db, user_id, month=item["month"])
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


def get_category_trends(db: Session, user_id: int) -> dict[str, Any]:
    monthly_summary = get_monthly_summary(db, user_id)

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
        for item in get_category_breakdown(db, user_id, month=previous_month)
    }
    current_categories = {
        item["category"]: item["total"]
        for item in get_category_breakdown(db, user_id, month=current_month)
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
    driver_category: str | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    top_category = snapshot["top_category"]
    current_month = snapshot["current_month"]
    target_category = driver_category or top_category

    if intent == "balance":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
            }
        )

    elif intent == "top_category":
        if target_category:
            actions.append(
                {
                    "label": f"Open {target_category} expenses",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": "expense",
                }
            )
            actions.append(
                {
                    "label": "View category ranking",
                    "page": "analytics",
                    "section": "categories",
                }
            )

    elif intent == "spending_change":
        actions.append(
            {
                "label": "Inspect overspending alerts",
                "page": "analytics",
                "section": "alerts",
            }
        )
        actions.append(
            {
                "label": "View category trends",
                "page": "analytics",
                "section": "trends",
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} expenses",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": "expense",
                    "month": current_month,
                }
            )

    elif intent == "saving_advice":
        actions.append(
            {
                "label": "Open spending insights",
                "page": "analytics",
                "section": "insights",
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} transactions",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": "expense",
                }
            )

    elif intent == "summary":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
            }
        )
        actions.append({"label": "View all transactions", "page": "transactions"})

    elif intent == "driver":
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Inspect {target_category} expenses",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": "expense",
                    "month": current_month,
                }
            )

    elif intent == "alerts":
        actions.append(
            {
                "label": "Open overspending alerts",
                "page": "analytics",
                "section": "alerts",
            }
        )
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
            }
        )

    elif intent == "recent":
        actions.append({"label": "View all transactions", "page": "transactions"})

    return actions[:3]


def style_answer(text: str, mode: str) -> str:
    normalized = (mode or "balanced").lower()

    if normalized == "strict":
        return f"Strict view: {text}"

    if normalized == "coach":
        return f"Coach view: {text}"

    return text


def style_followups(followups: list[str], mode: str) -> list[str]:
    normalized = (mode or "balanced").lower()

    if normalized == "strict":
        return [
            "What should I cut first?",
            "Which category is hurting me most?",
            "Show me the transactions causing this.",
        ]

    if normalized == "coach":
        return [
            "What is one easy improvement I can make this week?",
            "Where can I save without feeling restricted?",
            "Show me the best place to start improving.",
        ]

    return followups


def generate_assistant_response(
    db: Session,
    user_id: int,
    question: str,
    history: list[Any] | None = None,
    mode: str = "balanced",
) -> dict[str, Any]:
    history = history or []
    snapshot = build_financial_snapshot(db, user_id)
    category_trends = get_category_trends(db, user_id)
    overspending_alerts = get_overspending_alerts(db, user_id)
    recent_transactions = get_recent_transactions(db, user_id, limit=5)

    q = (question or "").strip().lower()
    context_text = extract_recent_context(history)
    intent = classify_question(q, context_text)

    total_income = snapshot["total_income"]
    total_expenses = snapshot["total_expenses"]
    balance = snapshot["balance"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    current_month = snapshot["current_month"]
    expense_change_percent = snapshot["expense_change_percent"]

    primary_driver = None
    if category_trends.get("top_increases"):
        primary_driver = category_trends["top_increases"][0]["category"]

    llm_result = generate_llm_assistant_response(
        question=question,
        conversation_context=context_text,
        snapshot=snapshot,
        category_trends=category_trends,
        overspending_alerts=overspending_alerts,
        recent_transactions=recent_transactions,
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
                    "category": action_target if action_target and action_target.lower() != "none" else primary_driver or top_category,
                    "transaction_type": "expense",
                    "month": current_month,
                }
            )

        elif action_type == "dashboard":
            suggested_actions.append(
                {
                    "label": action_label or "Open dashboard",
                    "page": "dashboard",
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
                }
            )

        elif action_type == "external_resource":
            suggested_actions.append(
                {
                    "label": action_label or "Explore learning resources",
                    "page": "external_resource",
                    "section": action_target or "budgeting basics",
                }
            )

        return {
            "answer": llm_result["answer"],
            "supporting_points": llm_result["supporting_points"],
            "suggested_followups": llm_result["suggested_followups"],
            "suggested_actions": suggested_actions,
        }

    if total_income == 0 and total_expenses == 0:
        base_answer = "I do not have enough financial activity yet to give a meaningful answer."
        return {
            "answer": style_answer(base_answer, mode),
            "supporting_points": [
                "No recorded income found yet.",
                "No recorded expenses found yet.",
            ],
            "suggested_followups": style_followups(
                [
                    "How do I get started?",
                    "What should I track first?",
                ],
                mode,
            ),
            "suggested_actions": [],
        }

    if not q:
        base_answer = "Ask me about your balance, top categories, transactions, spending trends, saving ideas, alerts, and financial summaries."
        return {
            "answer": style_answer(base_answer, mode),
            "supporting_points": [],
            "suggested_followups": style_followups(
                [
                    "What is my balance?",
                    "Show me my top 3 spending categories",
                    "Did my spending increase?",
                ],
                mode,
            ),
            "suggested_actions": [],
        }

    if intent == "top_categories_multi":
        top_three = get_top_expense_categories(db, user_id, limit=3)

        if not top_three:
            return {
                "answer": style_answer(
                    "I do not have enough expense data yet to identify your top categories.",
                    mode,
                ),
                "supporting_points": [],
                "suggested_followups": style_followups(
                    [
                        "What is my balance?",
                        "Summarize my finances",
                    ],
                    mode,
                ),
                "suggested_actions": [],
            }

        points = [
            f"{idx + 1}. {item['category']} — {format_currency(item['total'])}"
            for idx, item in enumerate(top_three)
        ]

        if mode == "strict":
            answer = "These are the categories taking the biggest share of your money. Focus on controlling them first."
        elif mode == "coach":
            answer = "Here are your top spending categories. These are the best places to look for meaningful savings."
        else:
            answer = "Your top spending categories are listed below, ranked by total expense amount."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": style_followups(
                [
                    "Show me their transactions",
                    "Which one is growing fastest?",
                    "How can I reduce them?",
                ],
                mode,
            ),
            "suggested_actions": [
                {
                    "label": "View all transactions",
                    "page": "transactions",
                }
            ],
        }

    if intent == "category_transactions":
        top_with_transactions = get_top_categories_with_transactions(
            db,
            user_id,
            category_limit=3,
            transaction_limit=2,
        )

        if not top_with_transactions:
            return {
                "answer": style_answer("I do not have enough category transaction data yet.", mode),
                "supporting_points": [],
                "suggested_followups": style_followups(
                    [
                        "Show me my top 3 spending categories",
                        "What is my balance?",
                    ],
                    mode,
                ),
                "suggested_actions": [],
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
            answer = "Here are the transactions behind your biggest categories. This is a great place to spot easy improvements."
        else:
            answer = "Here are your biggest spending categories and a few recent transactions inside each one."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": style_followups(
                [
                    "Which category is driving my spending most?",
                    "How can I reduce these expenses?",
                    "Open those transactions",
                ],
                mode,
            ),
            "suggested_actions": [
                {
                    "label": "Open transactions",
                    "page": "transactions",
                }
            ],
        }

    if mode == "strict":
        fallback_answer = (
            f"Your current balance is {format_currency(balance)}. "
            f"Your biggest expense category is {top_category or 'N/A'}"
            f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
            "If you want better control, start with the category doing the most damage."
        )
    elif mode == "coach":
        fallback_answer = (
            f"Your current balance is {format_currency(balance)}. "
            f"Your top expense category is {top_category or 'N/A'}"
            f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
            "That gives us a clear starting point for improvement."
        )
    else:
        fallback_answer = (
            "I can help with your balance, top categories, transactions, spending trends, saving ideas, alerts, and financial summaries."
        )

    supporting_points = [
        f"Current balance: {format_currency(balance)}",
        f"Top expense category: {top_category or 'N/A'}",
    ]

    if expense_change_percent is not None:
        supporting_points.append(
            f"Latest monthly expense change: {expense_change_percent:.1f}%"
        )

    return {
        "answer": fallback_answer,
        "supporting_points": supporting_points,
        "suggested_followups": style_followups(
            [
                "Show me my top 3 spending categories",
                "Show me their transactions",
                "Give me saving advice",
            ],
            mode,
        ),
        "suggested_actions": [],
    }


def generate_assistant_suggestions(db: Session, user_id: int) -> list[str]:
    snapshot = build_financial_snapshot(db, user_id)
    category_trends = get_category_trends(db, user_id)

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
        ),
        "top_category": get_top_expense_category(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
        ),
        "category_breakdown": get_category_breakdown(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
        ),
        "monthly_summary": get_monthly_summary(
            db,
            user_id,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
        ),
        "recent_transactions": get_recent_transactions(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
        ),
        "spending_insights": get_spending_insights(db, user_id),
        "overspending_alerts": get_overspending_alerts(db, user_id),
        "category_trends": get_category_trends(db, user_id),
    }