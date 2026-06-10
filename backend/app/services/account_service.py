from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Account, Transaction, User
from app.services.analytics_service import (
    canonical_analytics_category,
    cashflow_neutral_filter,
    expense_amount_expression,
    income_amount_expression,
    transaction_amount_magnitude_expression,
)


DEFAULT_ACCOUNT_NAME = "Main Account"
ALLOWED_ACCOUNT_TYPES = {"chequing", "savings", "credit_card", "cash", "business", "other"}


def normalize_account_type(value: str) -> str:
    normalized = (value or "other").strip().lower()
    return normalized if normalized in ALLOWED_ACCOUNT_TYPES else "other"


def ensure_default_account(db: Session, user: User) -> Account:
    account = (
        db.query(Account)
        .filter(Account.owner_id == user.id, Account.is_active.is_(True))
        .order_by(Account.id.asc())
        .first()
    )

    if account:
        return account

    account = Account(
        name=DEFAULT_ACCOUNT_NAME,
        type="other",
        owner_id=user.id,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get_user_accounts(db: Session, user_id: int) -> list[Account]:
    return (
        db.query(Account)
        .filter(Account.owner_id == user_id, Account.is_active.is_(True))
        .order_by(Account.name.asc(), Account.id.asc())
        .all()
    )


def get_user_accounts_with_stats(db: Session, user_id: int) -> list[dict]:
    accounts = get_user_accounts(db, user_id)
    if not accounts:
        return []

    account_ids = [a.id for a in accounts]

    summary_rows = (
        db.query(
            Transaction.account_id,
            func.coalesce(func.sum(income_amount_expression()), 0.0).label("total_income"),
            func.coalesce(func.sum(expense_amount_expression()), 0.0).label("total_expenses"),
        )
        .filter(
            Transaction.owner_id == user_id,
            Transaction.account_id.in_(account_ids),
            ~cashflow_neutral_filter(),
        )
        .group_by(Transaction.account_id)
        .all()
    )
    summaries = {row.account_id: row for row in summary_rows}

    category_rows = (
        db.query(
            Transaction.account_id,
            Transaction.category,
            func.sum(transaction_amount_magnitude_expression()).label("total"),
        )
        .filter(
            Transaction.owner_id == user_id,
            Transaction.type == "expense",
            Transaction.account_id.in_(account_ids),
            ~cashflow_neutral_filter(),
        )
        .group_by(Transaction.account_id, Transaction.category)
        .all()
    )
    top_categories: dict[int, tuple[str, float]] = {}
    for row in category_rows:
        canon = canonical_analytics_category(row.category)
        amount = float(row.total or 0.0)
        current = top_categories.get(row.account_id)
        if current is None or amount > current[1]:
            top_categories[row.account_id] = (canon, amount)

    result: list[dict] = []
    for account in accounts:
        summary = summaries.get(account.id)
        top = top_categories.get(account.id)
        total_income = float(summary.total_income) if summary else 0.0
        total_expenses = float(summary.total_expenses) if summary else 0.0
        result.append(
            {
                "id": account.id,
                "name": account.name,
                "type": account.type,
                "owner_id": account.owner_id,
                "is_active": account.is_active,
                "total_income": total_income,
                "total_expenses": total_expenses,
                "balance": total_income - total_expenses,
                "top_category": top[0] if top else None,
                "top_category_amount": top[1] if top else 0.0,
            }
        )

    return result


def get_account_for_user(db: Session, user_id: int, account_id: int) -> Account | None:
    return (
        db.query(Account)
        .filter(
            Account.id == account_id,
            Account.owner_id == user_id,
            Account.is_active.is_(True),
        )
        .first()
    )


def create_account(db: Session, user_id: int, name: str, account_type: str) -> Account:
    account = Account(
        name=name.strip(),
        type=normalize_account_type(account_type),
        owner_id=user_id,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(db: Session, account: Account, name: str, account_type: str) -> Account:
    account.name = name.strip()
    account.type = normalize_account_type(account_type)
    db.commit()
    db.refresh(account)
    return account


def deactivate_account(db: Session, account: Account) -> None:
    account.is_active = False
    db.commit()
