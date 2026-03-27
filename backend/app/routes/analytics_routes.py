from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models import Transaction, User
from app.schemas import AnalyticsSummary, CategoryBreakdownItem, MonthlySummaryItem, RecentTransactionItem, TopExpenseCategory

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id,
        Transaction.type == "expense"
    ).all()

    category_totals = {}

    for transaction in transactions:
        if transaction.category not in category_totals:
            category_totals[transaction.category] = 0.0
        category_totals[transaction.category] += transaction.amount

    result = [
        CategoryBreakdownItem(category=category, total=total)
        for category, total in category_totals.items()
    ]

    result.sort(key=lambda item: item.total, reverse=True)

    return result

@router.get("/monthly-summary", response_model=list[MonthlySummaryItem])
def get_monthly_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

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

    for month, values in monthly_data.items():
        income = values["income"]
        expenses = values["expenses"]
        balance = income - expenses

        result.append(
            MonthlySummaryItem(
                month=month,
                income=income,
                expenses=expenses,
                balance=balance
            )
        )

    result.sort(key=lambda item: item.month)

    return result

@router.get("/recent-transactions", response_model=list[RecentTransactionItem])
def get_recent_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).order_by(Transaction.date.desc()).limit(5).all()

    return transactions

@router.get("/top-expense-category", response_model=TopExpenseCategory | None)
def get_top_expense_category(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id,
        Transaction.type == "expense"
    ).all()

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