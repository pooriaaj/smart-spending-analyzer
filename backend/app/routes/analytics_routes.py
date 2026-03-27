from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models import Transaction, User
from app.schemas import AnalyticsSummary, CategoryBreakdownItem

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