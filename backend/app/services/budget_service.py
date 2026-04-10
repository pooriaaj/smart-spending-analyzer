from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Query, Session

from app.models import BudgetPlan
from app.schemas import BudgetListResponse, BudgetPlanResponse, BudgetSummaryResponse
from app.services.analytics_service import get_category_breakdown, get_summary
from app.services.transaction_service import normalize_category_name


def get_default_budget_month() -> str:
    return date.today().strftime("%Y-%m")


def build_budget_scope_query(
    db: Session,
    owner_id: int,
    month: str,
    account_id: int | None = None,
) -> Query:
    query = db.query(BudgetPlan).filter(
        BudgetPlan.owner_id == owner_id,
        BudgetPlan.month == month,
    )

    if account_id is None:
        query = query.filter(BudgetPlan.account_id.is_(None))
    else:
        query = query.filter(BudgetPlan.account_id == account_id)

    return query


def compute_budget_status(
    amount: float,
    spent_amount: float,
) -> tuple[float, float, str]:
    remaining_amount = amount - spent_amount
    usage_percent = (spent_amount / amount) * 100 if amount > 0 else 0.0

    if spent_amount > amount:
        status = "over_budget"
    elif usage_percent >= 80:
        status = "at_risk"
    else:
        status = "on_track"

    return remaining_amount, usage_percent, status


def build_budget_response(
    db: Session,
    budget: BudgetPlan,
) -> BudgetPlanResponse:
    spending_summary = get_summary(
        db,
        budget.owner_id,
        month=budget.month,
        transaction_type="expense",
        category=budget.category,
        account_id=budget.account_id,
    )
    spent_amount = float(spending_summary["total_expenses"])
    remaining_amount, usage_percent, status = compute_budget_status(
        amount=float(budget.amount),
        spent_amount=spent_amount,
    )

    return BudgetPlanResponse(
        id=budget.id,
        month=budget.month,
        category=budget.category,
        amount=float(budget.amount),
        owner_id=budget.owner_id,
        account_id=budget.account_id,
        spent_amount=spent_amount,
        remaining_amount=remaining_amount,
        usage_percent=usage_percent,
        status=status,
    )


def build_budget_summary(
    budgets: list[BudgetPlanResponse],
) -> BudgetSummaryResponse:
    total_budgeted = sum(item.amount for item in budgets)
    total_spent = sum(item.spent_amount for item in budgets)
    total_remaining = sum(item.remaining_amount for item in budgets)
    over_budget_count = sum(1 for item in budgets if item.status == "over_budget")
    at_risk_count = sum(1 for item in budgets if item.status == "at_risk")
    on_track_count = sum(1 for item in budgets if item.status == "on_track")

    return BudgetSummaryResponse(
        total_budgeted=total_budgeted,
        total_spent=total_spent,
        total_remaining=total_remaining,
        over_budget_count=over_budget_count,
        at_risk_count=at_risk_count,
        on_track_count=on_track_count,
    )


def list_budget_plans(
    db: Session,
    owner_id: int,
    month: str,
    account_id: int | None = None,
) -> BudgetListResponse:
    budgets = (
        build_budget_scope_query(
            db,
            owner_id,
            month=month,
            account_id=account_id,
        )
        .order_by(BudgetPlan.category.asc(), BudgetPlan.id.asc())
        .all()
    )
    budget_responses = [build_budget_response(db, budget) for budget in budgets]
    available_categories = [
        item["category"]
        for item in get_category_breakdown(
            db,
            owner_id,
            transaction_type="expense",
            account_id=account_id,
        )
    ]

    return BudgetListResponse(
        month=month,
        account_id=account_id,
        budgets=budget_responses,
        summary=build_budget_summary(budget_responses),
        available_categories=available_categories,
    )


def upsert_budget_plan(
    db: Session,
    owner_id: int,
    month: str,
    category: str,
    amount: float,
    account_id: int | None = None,
) -> BudgetPlan:
    normalized_category = normalize_category_name(category)
    budget = (
        build_budget_scope_query(
            db,
            owner_id,
            month=month,
            account_id=account_id,
        )
        .filter(BudgetPlan.category == normalized_category)
        .first()
    )

    if budget:
        budget.amount = amount
    else:
        budget = BudgetPlan(
            month=month,
            category=normalized_category,
            amount=amount,
            owner_id=owner_id,
            account_id=account_id,
        )
        db.add(budget)

    db.commit()
    db.refresh(budget)
    return budget


def get_budget_plan_for_user(
    db: Session,
    owner_id: int,
    budget_id: int,
) -> BudgetPlan | None:
    return (
        db.query(BudgetPlan)
        .filter(
            BudgetPlan.id == budget_id,
            BudgetPlan.owner_id == owner_id,
        )
        .first()
    )


def delete_budget_plan(
    db: Session,
    budget: BudgetPlan,
) -> None:
    db.delete(budget)
    db.commit()
