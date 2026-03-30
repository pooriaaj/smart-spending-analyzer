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

    expense_transactions = [t for t in transactions if t.type == "expense"]

    if not expense_transactions:
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

    monthly_expenses = {}
    category_totals = {}

    for transaction in expense_transactions:
        month_key = transaction.date.strftime("%Y-%m")
        monthly_expenses[month_key] = monthly_expenses.get(month_key, 0.0) + transaction.amount
        category_totals[transaction.category] = category_totals.get(transaction.category, 0.0) + transaction.amount

    sorted_months = sorted(monthly_expenses.keys())
    current_month = sorted_months[-1]
    current_month_expenses = monthly_expenses[current_month]

    previous_month_expenses = 0.0
    expense_change_percent = None

    if len(sorted_months) >= 2:
        previous_month = sorted_months[-2]
        previous_month_expenses = monthly_expenses[previous_month]

        if previous_month_expenses > 0:
            expense_change_percent = (
                (current_month_expenses - previous_month_expenses) / previous_month_expenses
            ) * 100

    top_category, top_category_amount = max(
        category_totals.items(),
        key=lambda item: item[1]
    )

    total_expenses = sum(category_totals.values())
    top_category_share_percent = None
    if total_expenses > 0:
        top_category_share_percent = (top_category_amount / total_expenses) * 100

    insights = []
    recommendations = []

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