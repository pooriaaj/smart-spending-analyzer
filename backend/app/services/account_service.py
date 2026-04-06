from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Account, User


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