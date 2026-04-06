from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import AccountCreate, AccountResponse, AccountUpdate, MessageResponse
from app.services.account_service import (
    create_account,
    deactivate_account,
    ensure_default_account,
    get_account_for_user,
    get_user_accounts,
    update_account,
)

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/", response_model=list[AccountResponse])
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)
    return get_user_accounts(db, current_user.id)


@router.post("/", response_model=AccountResponse)
def create_account_route(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_account(db, current_user.id, payload.name, payload.type)


@router.put("/{account_id}", response_model=AccountResponse)
def update_account_route(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_account_for_user(db, current_user.id, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return update_account(db, account, payload.name, payload.type)


@router.delete("/{account_id}", response_model=MessageResponse)
def delete_account_route(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accounts = get_user_accounts(db, current_user.id)
    account = next((item for item in accounts if item.id == account_id), None)

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if len(accounts) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must keep at least one active account",
        )

    deactivate_account(db, account)
    return MessageResponse(message="Account deactivated successfully")