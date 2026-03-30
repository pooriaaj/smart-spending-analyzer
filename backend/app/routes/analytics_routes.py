from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from app.dependencies import get_db, get_current_user
from app.models import Transaction, User
from app.schemas import (
    AnalyticsSummary,
    CategoryBreakdownItem,
    MonthlySummaryItem,
    RecentTransactionItem,
    TopExpenseCategory,
    SpendingInsights,
    OverspendingAlertItem,
    OverspendingAlertsResponse,
    CategoryTrendItem,
    CategoryTrendsResponse,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSuggestionsResponse,
    AssistantAction,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def filter_transactions(
    transactions,
    month: str | None,
    start_date: str | None,
    end_date: str | None,
    transaction_type: str | None,
    category: str | None
):
    result = transactions

    if month:
        result = [
            transaction
            for transaction in result
            if transaction.date.strftime("%Y-%m") == month
        ]

    if start_date:
        start = datetime.fromisoformat(start_date).date()
        result = [
            transaction
            for transaction in result
            if transaction.date >= start
        ]

    if end_date:
        end = datetime.fromisoformat(end_date).date()
        result = [
            transaction
            for transaction in result
            if transaction.date <= end
        ]

    if transaction_type:
        result = [
            transaction
            for transaction in result
            if transaction.type == transaction_type
        ]

    if category:
        result = [
            transaction
            for transaction in result
            if transaction.category == category
        ]

    return result


def build_financial_snapshot(transactions):
    income_transactions = [t for t in transactions if t.type == "income"]
    expense_transactions = [t for t in transactions if t.type == "expense"]

    total_income = sum(t.amount for t in income_transactions)
    total_expenses = sum(t.amount for t in expense_transactions)
    balance = total_income - total_expenses

    monthly_expenses = {}
    category_totals = {}

    for transaction in expense_transactions:
        month_key = transaction.date.strftime("%Y-%m")
        monthly_expenses[month_key] = monthly_expenses.get(month_key, 0.0) + transaction.amount
        category_totals[transaction.category] = category_totals.get(transaction.category, 0.0) + transaction.amount

    top_category = None
    top_category_amount = 0.0
    if category_totals:
        top_category, top_category_amount = max(category_totals.items(), key=lambda item: item[1])

    sorted_months = sorted(monthly_expenses.keys())
    current_month = sorted_months[-1] if sorted_months else None
    previous_month = sorted_months[-2] if len(sorted_months) >= 2 else None

    current_month_expenses = monthly_expenses.get(current_month, 0.0) if current_month else 0.0
    previous_month_expenses = monthly_expenses.get(previous_month, 0.0) if previous_month else 0.0

    expense_change_percent = None
    if previous_month_expenses > 0:
        expense_change_percent = (
            (current_month_expenses - previous_month_expenses) / previous_month_expenses
        ) * 100

    top_category_share_percent = None
    if total_expenses > 0 and top_category_amount > 0:
        top_category_share_percent = (top_category_amount / total_expenses) * 100

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": balance,
        "top_category": top_category,
        "top_category_amount": top_category_amount,
        "top_category_share_percent": top_category_share_percent,
        "current_month": current_month,
        "previous_month": previous_month,
        "current_month_expenses": current_month_expenses,
        "previous_month_expenses": previous_month_expenses,
        "expense_change_percent": expense_change_percent,
    }


def extract_recent_context(history):
    recent_user_messages = [
        message.content.strip().lower()
        for message in history[-6:]
        if message.role.lower() == "user" and message.content.strip()
    ]
    return " ".join(recent_user_messages)


def format_currency(value: float) -> str:
    return f"${value:.2f}"


def build_assistant_actions(snapshot: dict, intent: str) -> list[AssistantAction]:
    actions = []

    top_category = snapshot["top_category"]
    current_month = snapshot["current_month"]

    if intent == "balance":
        actions.append(
            AssistantAction(
                label="Open monthly summary",
                page="analytics",
                section="monthly",
                month=current_month,
            )
        )

    elif intent == "top_category":
        if top_category:
            actions.append(
                AssistantAction(
                    label=f"Open {top_category} expenses",
                    page="transactions",
                    category=top_category,
                    transaction_type="expense",
                )
            )
            actions.append(
                AssistantAction(
                    label="View category ranking",
                    page="analytics",
                    section="categories",
                )
            )

    elif intent == "spending_change":
        actions.append(
            AssistantAction(
                label="Inspect overspending alerts",
                page="analytics",
                section="alerts",
            )
        )
        actions.append(
            AssistantAction(
                label="View category trends",
                page="analytics",
                section="trends",
            )
        )

    elif intent == "saving_advice":
        actions.append(
            AssistantAction(
                label="Open spending insights",
                page="analytics",
                section="insights",
            )
        )
        if top_category:
            actions.append(
                AssistantAction(
                    label=f"Review {top_category} transactions",
                    page="transactions",
                    category=top_category,
                    transaction_type="expense",
                )
            )

    elif intent == "summary":
        actions.append(
            AssistantAction(
                label="Open monthly summary",
                page="analytics",
                section="monthly",
                month=current_month,
            )
        )
        actions.append(
            AssistantAction(
                label="View all transactions",
                page="transactions",
            )
        )

    elif intent == "driver":
        actions.append(
            AssistantAction(
                label="Open category trends",
                page="analytics",
                section="trends",
            )
        )
        if top_category:
            actions.append(
                AssistantAction(
                    label=f"Inspect {top_category} expenses",
                    page="transactions",
                    category=top_category,
                    transaction_type="expense",
                )
            )

    return actions[:3]


def generate_assistant_response(question: str, snapshot: dict, history=None) -> dict:
    history = history or []
    q = (question or "").strip().lower()
    context_text = extract_recent_context(history)
    combined_text = f"{context_text} {q}".strip()

    total_income = snapshot["total_income"]
    total_expenses = snapshot["total_expenses"]
    balance = snapshot["balance"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    top_category_share_percent = snapshot["top_category_share_percent"]
    current_month = snapshot["current_month"]
    previous_month = snapshot["previous_month"]
    current_month_expenses = snapshot["current_month_expenses"]
    previous_month_expenses = snapshot["previous_month_expenses"]
    expense_change_percent = snapshot["expense_change_percent"]

    if total_income == 0 and total_expenses == 0:
        return {
            "answer": "I do not have enough financial activity yet to give a meaningful answer.",
            "supporting_points": [
                "No recorded income found yet.",
                "No recorded expenses found yet.",
            ],
            "suggested_followups": [
                "How do I get started?",
                "What should I track first?",
            ],
            "suggested_actions": [],
        }

    if not q:
        return {
            "answer": "Ask me about your balance, your spending trend, your biggest expense category, or ways to save money.",
            "supporting_points": [],
            "suggested_followups": [
                "What is my balance?",
                "What is my top expense category?",
                "Did my spending increase?",
            ],
            "suggested_actions": [],
        }

    if "balance" in combined_text:
        if balance >= 0:
            answer = f"Your current recorded balance is {format_currency(balance)}."
        else:
            answer = f"Your current recorded balance is {format_currency(balance)}, which means expenses are currently higher than income."

        return {
            "answer": answer,
            "supporting_points": [
                f"Total income: {format_currency(total_income)}",
                f"Total expenses: {format_currency(total_expenses)}",
            ],
            "suggested_followups": [
                "What is my top expense category?",
                "Give me saving advice",
            ],
            "suggested_actions": build_assistant_actions(snapshot, "balance"),
        }

    if "top expense" in combined_text or "top category" in combined_text or "biggest category" in combined_text:
        if top_category:
            answer = (
                f"Your top expense category is {top_category} at {format_currency(top_category_amount)}."
            )

            supporting_points = [
                f"Total expenses recorded: {format_currency(total_expenses)}",
            ]

            if top_category_share_percent is not None:
                supporting_points.append(
                    f"{top_category} represents {top_category_share_percent:.1f}% of your total expenses."
                )

            if current_month:
                supporting_points.append(
                    f"Latest expense month: {current_month}"
                )

            return {
                "answer": answer,
                "supporting_points": supporting_points,
                "suggested_followups": [
                    "How can I reduce it?",
                    "Did my spending increase?",
                ],
                "suggested_actions": build_assistant_actions(snapshot, "top_category"),
            }

        return {
            "answer": "I do not have enough expense data yet to identify your top expense category.",
            "supporting_points": [],
            "suggested_followups": [
                "What is my balance?",
                "Summarize my finances",
            ],
            "suggested_actions": [],
        }

    if (
        "increase" in combined_text
        or "overspend" in combined_text
        or "spending" in combined_text
        or "last month" in combined_text
        or "this month" in combined_text
    ):
        if current_month and previous_month and expense_change_percent is not None:
            if expense_change_percent > 0:
                answer = (
                    f"Your spending increased by {expense_change_percent:.1f}% in {current_month} compared with {previous_month}."
                )
            elif expense_change_percent < 0:
                answer = (
                    f"Your spending decreased by {abs(expense_change_percent):.1f}% in {current_month} compared with {previous_month}."
                )
            else:
                answer = (
                    f"Your spending stayed flat in {current_month} compared with {previous_month}."
                )

            return {
                "answer": answer,
                "supporting_points": [
                    f"{current_month}: {format_currency(current_month_expenses)}",
                    f"{previous_month}: {format_currency(previous_month_expenses)}",
                    f"Top expense category: {top_category or 'N/A'}",
                ],
                "suggested_followups": [
                    "Which category is driving this?",
                    "Give me saving advice",
                ],
                "suggested_actions": build_assistant_actions(snapshot, "spending_change"),
            }

        return {
            "answer": "I need at least two months of expense data to compare your spending trend properly.",
            "supporting_points": [
                f"Current recorded month expenses: {format_currency(current_month_expenses)}",
            ],
            "suggested_followups": [
                "What is my balance?",
                "Summarize my finances",
            ],
            "suggested_actions": [],
        }

    if (
        "advice" in combined_text
        or "save" in combined_text
        or "saving" in combined_text
        or "reduce it" in combined_text
        or "reduce" in combined_text
    ):
        supporting_points = [
            f"Current balance: {format_currency(balance)}",
        ]

        if top_category:
            supporting_points.append(
                f"Top expense category: {top_category} ({format_currency(top_category_amount)})"
            )

        if expense_change_percent is not None and expense_change_percent > 0:
            supporting_points.append(
                f"Recent spending change: +{expense_change_percent:.1f}%"
            )

        if top_category and top_category_share_percent is not None and top_category_share_percent >= 35:
            answer = (
                f"The strongest place to start is {top_category}. It is currently absorbing a large share of your spending, so even a modest reduction there could improve your budget noticeably."
            )
        elif balance < 0:
            answer = (
                "Your first priority should be reducing non-essential spending, because your current recorded balance is negative."
            )
        else:
            answer = (
                "The best next step is to review your biggest expense areas and look for one category where a small reduction would be easy to maintain."
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": [
                "What is my top expense category?",
                "Did my spending increase?",
            ],
            "suggested_actions": build_assistant_actions(snapshot, "saving_advice"),
        }

    if (
        "summary" in combined_text
        or "summarize" in combined_text
        or "overview" in combined_text
        or "my finances" in combined_text
    ):
        answer = (
            f"Here is your current financial summary: income is {format_currency(total_income)}, expenses are {format_currency(total_expenses)}, and your balance is {format_currency(balance)}."
        )

        supporting_points = []

        if current_month:
            supporting_points.append(
                f"Latest expense month: {current_month} ({format_currency(current_month_expenses)})"
            )

        if top_category:
            supporting_points.append(
                f"Top expense category: {top_category} ({format_currency(top_category_amount)})"
            )

        if expense_change_percent is not None:
            if expense_change_percent > 0:
                supporting_points.append(
                    f"Spending trend: up {expense_change_percent:.1f}% vs previous month"
                )
            elif expense_change_percent < 0:
                supporting_points.append(
                    f"Spending trend: down {abs(expense_change_percent):.1f}% vs previous month"
                )

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": [
                "What is my top expense category?",
                "Give me saving advice",
                "Did my spending increase?",
            ],
            "suggested_actions": build_assistant_actions(snapshot, "summary"),
        }

    if "which category" in combined_text or "driving this" in combined_text:
        if top_category:
            answer = (
                f"The strongest current expense driver appears to be {top_category}, with {format_currency(top_category_amount)} in recorded spending."
            )

            supporting_points = [
                f"Total expenses: {format_currency(total_expenses)}",
            ]

            if top_category_share_percent is not None:
                supporting_points.append(
                    f"{top_category} share of total expenses: {top_category_share_percent:.1f}%"
                )

            if current_month:
                supporting_points.append(
                    f"Latest expense month: {current_month}"
                )

            return {
                "answer": answer,
                "supporting_points": supporting_points,
                "suggested_followups": [
                    "How can I reduce it?",
                    "Summarize my finances",
                ],
                "suggested_actions": build_assistant_actions(snapshot, "driver"),
            }

    return {
        "answer": "I can help with your balance, spending trends, top expense categories, savings ideas, or a full financial summary.",
        "supporting_points": [
            f"Current balance: {format_currency(balance)}",
            f"Top expense category: {top_category or 'N/A'}",
        ],
        "suggested_followups": [
            "What is my balance?",
            "What is my top expense category?",
            "Give me saving advice",
        ],
        "suggested_actions": [],
    }


def generate_assistant_suggestions(snapshot: dict) -> list[str]:
    suggestions = []

    suggestions.append("What is my balance?")

    if snapshot["top_category"]:
        suggestions.append(f"Why is {snapshot['top_category']} my top expense category?")
        suggestions.append(f"How can I reduce {snapshot['top_category']} spending?")

    if snapshot["expense_change_percent"] is not None:
        if snapshot["expense_change_percent"] > 0:
            suggestions.append("Why did my spending increase?")
        elif snapshot["expense_change_percent"] < 0:
            suggestions.append("Why did my spending decrease?")

    if snapshot["current_month"]:
        suggestions.append(f"Summarize my finances for {snapshot['current_month']}")

    suggestions.append("Give me saving advice")

    unique_suggestions = []
    for item in suggestions:
        if item not in unique_suggestions:
            unique_suggestions.append(item)

    return unique_suggestions[:6]


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    transactions = filter_transactions(
        transactions,
        month,
        start_date,
        end_date,
        transaction_type,
        category
    )

    total_income = sum(t.amount for t in transactions if t.type == "income")
    total_expenses = sum(t.amount for t in transactions if t.type == "expense")
    balance = total_income - total_expenses

    return AnalyticsSummary(
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance
    )


@router.get("/category-breakdown", response_model=list[CategoryBreakdownItem])
def get_category_breakdown(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    transactions = filter_transactions(
        transactions,
        month,
        start_date,
        end_date,
        transaction_type,
        category
    )

    transactions = [t for t in transactions if t.type == "expense"]

    category_totals = {}

    for transaction in transactions:
        if transaction.category not in category_totals:
            category_totals[transaction.category] = 0.0
        category_totals[transaction.category] += transaction.amount

    result = [
        CategoryBreakdownItem(category=category_name, total=total)
        for category_name, total in category_totals.items()
    ]

    result.sort(key=lambda item: item.total, reverse=True)

    return result


@router.get("/monthly-summary", response_model=list[MonthlySummaryItem])
def get_monthly_summary(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    transactions = filter_transactions(
        transactions,
        None,
        start_date,
        end_date,
        transaction_type,
        category
    )

    monthly_data = {}

    for transaction in transactions:
        month_key = transaction.date.strftime("%Y-%m")

        if month_key not in monthly_data:
            monthly_data[month_key] = {
                "income": 0.0,
                "expenses": 0.0
            }

        if transaction.type == "income":
            monthly_data[month_key]["income"] += transaction.amount
        elif transaction.type == "expense":
            monthly_data[month_key]["expenses"] += transaction.amount

    result = []

    for month_value, values in monthly_data.items():
        income = values["income"]
        expenses = values["expenses"]
        balance = income - expenses

        result.append(
            MonthlySummaryItem(
                month=month_value,
                income=income,
                expenses=expenses,
                balance=balance
            )
        )

    result.sort(key=lambda item: item.month)

    return result


@router.get("/recent-transactions", response_model=list[RecentTransactionItem])
def get_recent_transactions(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    transactions = filter_transactions(
        transactions,
        month,
        start_date,
        end_date,
        transaction_type,
        category
    )
    transactions.sort(key=lambda t: t.date, reverse=True)

    return transactions[:5]


@router.get("/top-expense-category", response_model=TopExpenseCategory | None)
def get_top_expense_category(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    transactions = filter_transactions(
        transactions,
        month,
        start_date,
        end_date,
        transaction_type,
        category
    )

    transactions = [t for t in transactions if t.type == "expense"]

    if not transactions:
        return None

    category_totals = {}

    for transaction in transactions:
        if transaction.category not in category_totals:
            category_totals[transaction.category] = 0.0
        category_totals[transaction.category] += transaction.amount

    top_category = max(category_totals.items(), key=lambda item: item[1])

    return TopExpenseCategory(
        category=top_category[0],
        total=top_category[1]
    )


@router.get("/spending-insights", response_model=SpendingInsights)
def get_spending_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    snapshot = build_financial_snapshot(transactions)

    total_expenses = snapshot["total_expenses"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    current_month = snapshot["current_month"]
    current_month_expenses = snapshot["current_month_expenses"]
    previous_month_expenses = snapshot["previous_month_expenses"]
    expense_change_percent = snapshot["expense_change_percent"]
    top_category_share_percent = snapshot["top_category_share_percent"]

    if total_expenses == 0:
        return SpendingInsights(
            current_month=None,
            current_month_expenses=0.0,
            previous_month_expenses=0.0,
            expense_change_percent=None,
            top_category=None,
            top_category_amount=0.0,
            top_category_share_percent=None,
            insights=["No expense data available yet."],
            recommendations=["Add more transactions to unlock spending insights."]
        )

    insights = []
    recommendations = []

    insights.append(
        f"Your latest expense month is {current_month} with {format_currency(current_month_expenses)} in spending."
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
        f"Your top expense category is {top_category} at {format_currency(top_category_amount)}."
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

    return SpendingInsights(
        current_month=current_month,
        current_month_expenses=current_month_expenses,
        previous_month_expenses=previous_month_expenses,
        expense_change_percent=expense_change_percent,
        top_category=top_category,
        top_category_amount=top_category_amount,
        top_category_share_percent=top_category_share_percent,
        insights=insights,
        recommendations=recommendations
    )


@router.get("/overspending-alerts", response_model=OverspendingAlertsResponse)
def get_overspending_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    expense_transactions = [t for t in transactions if t.type == "expense"]

    if not expense_transactions:
        return OverspendingAlertsResponse(current_month=None, alerts=[])

    monthly_totals = {}
    monthly_category_totals = {}

    for transaction in expense_transactions:
        month_key = transaction.date.strftime("%Y-%m")
        monthly_totals[month_key] = monthly_totals.get(month_key, 0.0) + transaction.amount

        if month_key not in monthly_category_totals:
            monthly_category_totals[month_key] = {}

        monthly_category_totals[month_key][transaction.category] = (
            monthly_category_totals[month_key].get(transaction.category, 0.0) + transaction.amount
        )

    sorted_months = sorted(monthly_totals.keys())
    current_month = sorted_months[-1]
    current_total = monthly_totals[current_month]

    alerts = []

    if len(sorted_months) >= 2:
        previous_month = sorted_months[-2]
        previous_total = monthly_totals[previous_month]

        if previous_total > 0:
            change_percent = ((current_total - previous_total) / previous_total) * 100

            if change_percent >= 25:
                alerts.append(
                    OverspendingAlertItem(
                        level="high",
                        title="Monthly spending spike",
                        message=f"Your spending in {current_month} is up {change_percent:.1f}% compared with {previous_month}."
                    )
                )
            elif change_percent >= 15:
                alerts.append(
                    OverspendingAlertItem(
                        level="medium",
                        title="Monthly spending increase",
                        message=f"Your spending in {current_month} is up {change_percent:.1f}% compared with {previous_month}."
                    )
                )

    current_categories = monthly_category_totals.get(current_month, {})
    current_total_expenses = sum(current_categories.values())

    if current_total_expenses > 0:
        for category, amount in current_categories.items():
            share = (amount / current_total_expenses) * 100

            if share >= 45:
                alerts.append(
                    OverspendingAlertItem(
                        level="high",
                        title=f"{category} is dominating spending",
                        message=f"{category} makes up {share:.1f}% of your expenses in {current_month}."
                    )
                )
            elif share >= 30:
                alerts.append(
                    OverspendingAlertItem(
                        level="medium",
                        title=f"{category} is a major spending category",
                        message=f"{category} makes up {share:.1f}% of your expenses in {current_month}."
                    )
                )

    if not alerts:
        alerts.append(
            OverspendingAlertItem(
                level="low",
                title="No major overspending alert",
                message="Your latest spending pattern does not show a strong overspending signal right now."
            )
        )

    return OverspendingAlertsResponse(
        current_month=current_month,
        alerts=alerts
    )


@router.get("/category-trends", response_model=CategoryTrendsResponse)
def get_category_trends(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    expense_transactions = [t for t in transactions if t.type == "expense"]

    if not expense_transactions:
        return CategoryTrendsResponse(
            current_month=None,
            previous_month=None,
            top_increases=[],
            top_decreases=[],
            summary=["No expense trend data available yet."]
        )

    monthly_category_totals = {}

    for transaction in expense_transactions:
        month_key = transaction.date.strftime("%Y-%m")

        if month_key not in monthly_category_totals:
            monthly_category_totals[month_key] = {}

        monthly_category_totals[month_key][transaction.category] = (
            monthly_category_totals[month_key].get(transaction.category, 0.0) + transaction.amount
        )

    sorted_months = sorted(monthly_category_totals.keys())

    if len(sorted_months) < 2:
        return CategoryTrendsResponse(
            current_month=sorted_months[-1],
            previous_month=None,
            top_increases=[],
            top_decreases=[],
            summary=["At least two months of expense data are needed for category trend comparison."]
        )

    previous_month = sorted_months[-2]
    current_month = sorted_months[-1]

    previous_categories = monthly_category_totals.get(previous_month, {})
    current_categories = monthly_category_totals.get(current_month, {})

    all_categories = sorted(set(previous_categories.keys()) | set(current_categories.keys()))
    trend_items = []

    for category in all_categories:
        previous_amount = previous_categories.get(category, 0.0)
        current_amount = current_categories.get(category, 0.0)
        change_amount = current_amount - previous_amount

        change_percent = None
        if previous_amount > 0:
            change_percent = (change_amount / previous_amount) * 100

        trend_items.append(
            CategoryTrendItem(
                category=category,
                current_amount=current_amount,
                previous_amount=previous_amount,
                change_amount=change_amount,
                change_percent=change_percent
            )
        )

    increases = sorted(
        [item for item in trend_items if item.change_amount > 0],
        key=lambda item: item.change_amount,
        reverse=True
    )[:5]

    decreases = sorted(
        [item for item in trend_items if item.change_amount < 0],
        key=lambda item: item.change_amount
    )[:5]

    summary = []

    if increases:
        top_up = increases[0]
        summary.append(
            f"The biggest increase from {previous_month} to {current_month} was {top_up.category}, up {format_currency(top_up.change_amount)}."
        )

    if decreases:
        top_down = decreases[0]
        summary.append(
            f"The biggest decrease from {previous_month} to {current_month} was {top_down.category}, down {format_currency(abs(top_down.change_amount))}."
        )

    if not summary:
        summary.append(
            f"No category-level increase or decrease was detected between {previous_month} and {current_month}."
        )

    return CategoryTrendsResponse(
        current_month=current_month,
        previous_month=previous_month,
        top_increases=increases,
        top_decreases=decreases,
        summary=summary
    )


@router.post("/assistant-response", response_model=AssistantQueryResponse)
def get_assistant_response(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    snapshot = build_financial_snapshot(transactions)
    result = generate_assistant_response(payload.question, snapshot, payload.history)

    return AssistantQueryResponse(**result)


@router.get("/assistant-suggestions", response_model=AssistantSuggestionsResponse)
def get_assistant_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    snapshot = build_financial_snapshot(transactions)
    suggestions = generate_assistant_suggestions(snapshot)

    return AssistantSuggestionsResponse(suggestions=suggestions)