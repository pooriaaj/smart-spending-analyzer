from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import BudgetListResponse, BudgetPlanCreate, BudgetPlanResponse, MessageResponse
from app.services.account_service import get_account_for_user
from app.services.budget_service import (
    delete_budget_plan,
    get_budget_plan_for_user,
    get_default_budget_month,
    list_budget_plans,
    build_budget_response,
    upsert_budget_plan,
)

router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.get("/", response_model=BudgetListResponse)
def list_budgets_route(
    month: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if account_id is not None:
        account = get_account_for_user(db, current_user.id, account_id)
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return list_budget_plans(
        db=db,
        owner_id=current_user.id,
        month=month or get_default_budget_month(),
        account_id=account_id,
    )


@router.post("/", response_model=BudgetPlanResponse)
def upsert_budget_route(
    payload: BudgetPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.account_id is not None:
        account = get_account_for_user(db, current_user.id, payload.account_id)
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    budget = upsert_budget_plan(
        db=db,
        owner_id=current_user.id,
        month=payload.month,
        category=payload.category,
        amount=payload.amount,
        account_id=payload.account_id,
    )
    return build_budget_response(db, budget)


@router.delete("/{budget_id}", response_model=MessageResponse)
def delete_budget_route(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = get_budget_plan_for_user(db, current_user.id, budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")

    delete_budget_plan(db, budget)
    return MessageResponse(message="Budget deleted successfully")
