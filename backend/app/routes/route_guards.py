from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Account, User
from app.services.account_service import get_account_for_user


def require_owned_account(
    db: Session,
    current_user: User,
    account_id: int | None,
    *,
    allow_all: bool = False,
) -> Account | None:
    if account_id is None:
        if allow_all:
            return None
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is required")

    account = get_account_for_user(db, current_user.id, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return account


def resolve_account_scope_label(
    db: Session,
    current_user: User,
    account_id: int | None,
) -> str:
    account = require_owned_account(db, current_user, account_id, allow_all=True)
    if account is None:
        return "All accounts combined"

    return f"{account.name} ({account.type})"
