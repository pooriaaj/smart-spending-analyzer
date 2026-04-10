from __future__ import annotations

import calendar
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.models import BudgetPlan, Transaction
from app.schemas import (
    BudgetCopyResponse,
    BudgetListResponse,
    BudgetPlanResponse,
    BudgetSuggestionResponse,
    BudgetSummaryResponse,
)
from app.services.analytics_service import get_category_breakdown, get_summary, month_bucket_expression
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


def format_budget_currency(value: float) -> str:
    return f"${value:.2f}"


def build_budget_pace_context(
    month: str,
    amount: float,
    spent_amount: float,
    remaining_amount: float,
    *,
    today: date | None = None,
) -> dict[str, int | float | str | None]:
    today = today or date.today()
    month_start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    days_total = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=days_total)

    daily_allowance: float | None = None
    daily_pace: float | None = None

    if today < month_start:
        days_elapsed = 0
        days_remaining = days_total
        daily_allowance = amount / days_total if days_total > 0 else None
        pace_note = (
            f"This budget has not started yet. Planned average pace is {format_budget_currency(daily_allowance or 0.0)} per day."
        )
    elif today > month_end:
        days_elapsed = days_total
        days_remaining = 0
        daily_pace = spent_amount / days_total if days_total > 0 else None
        if remaining_amount >= 0:
            pace_note = (
                f"This month closed with {format_budget_currency(remaining_amount)} remaining."
            )
        else:
            pace_note = (
                f"This month closed {format_budget_currency(abs(remaining_amount))} over budget."
            )
    else:
        days_elapsed = today.day
        days_remaining = days_total - today.day + 1
        daily_allowance = remaining_amount / days_remaining if days_remaining > 0 else None
        daily_pace = spent_amount / days_elapsed if days_elapsed > 0 else None

        expected_spend_to_date = (amount / days_total) * days_elapsed if days_total > 0 else 0.0
        pace_variance = spent_amount - expected_spend_to_date
        significance_threshold = max(amount * 0.05, 5.0)

        if remaining_amount < 0:
            pace_note = (
                f"Already {format_budget_currency(abs(remaining_amount))} over budget with {days_remaining} day(s) left."
            )
        elif pace_variance > significance_threshold:
            pace_note = (
                f"Running about {format_budget_currency(pace_variance)} ahead of pace for this point in the month."
            )
        elif pace_variance < -significance_threshold:
            pace_note = (
                f"Running about {format_budget_currency(abs(pace_variance))} under pace so far this month."
            )
        else:
            pace_note = "Spending is roughly on pace for this point in the month."

    return {
        "days_total": days_total,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "daily_allowance": daily_allowance,
        "daily_pace": daily_pace,
        "pace_note": pace_note,
    }


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
    pace_context = build_budget_pace_context(
        month=budget.month,
        amount=float(budget.amount),
        spent_amount=spent_amount,
        remaining_amount=remaining_amount,
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
        days_total=pace_context["days_total"],
        days_elapsed=pace_context["days_elapsed"],
        days_remaining=pace_context["days_remaining"],
        daily_allowance=pace_context["daily_allowance"],
        daily_pace=pace_context["daily_pace"],
        pace_note=pace_context["pace_note"],
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


def shift_month_label(month: str, offset: int) -> str:
    month_date = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    total_months = (month_date.year * 12 + month_date.month - 1) + offset
    shifted_year = total_months // 12
    shifted_month = total_months % 12 + 1
    return f"{shifted_year:04d}-{shifted_month:02d}"


def build_budget_suggestions(
    db: Session,
    owner_id: int,
    month: str,
    account_id: int | None,
    existing_categories: set[str],
    limit: int = 4,
) -> list[BudgetSuggestionResponse]:
    month_labels = [shift_month_label(month, offset) for offset in (-2, -1, 0)]
    month_expr = month_bucket_expression(db)

    query = db.query(
        Transaction.category.label("category"),
        month_expr.label("month"),
        func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
    ).filter(
        Transaction.owner_id == owner_id,
        Transaction.type == "expense",
        month_expr.in_(month_labels),
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    rows = (
        query.group_by(Transaction.category, month_expr)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    totals_by_category: dict[str, dict[str, float]] = {}
    for row in rows:
        normalized_category = normalize_category_name(row.category)
        if normalized_category in existing_categories:
            continue
        category_totals = totals_by_category.setdefault(normalized_category, {})
        category_totals[row.month] = category_totals.get(row.month, 0.0) + float(row.total or 0.0)

    suggestions: list[BudgetSuggestionResponse] = []
    for category, month_totals in totals_by_category.items():
        monthly_values = [month_totals.get(label, 0.0) for label in month_labels]
        if not any(value > 0 for value in monthly_values):
            continue

        average_spent = sum(monthly_values) / len(monthly_values)
        latest_month_spent = monthly_values[-1]
        suggested_amount = round(max(average_spent, latest_month_spent), 2)

        if suggested_amount <= 0:
            continue

        if latest_month_spent > average_spent:
            note = "Suggested from your current month pace and recent average."
        else:
            note = "Suggested from your recent monthly average spending."

        suggestions.append(
            BudgetSuggestionResponse(
                category=category,
                suggested_amount=suggested_amount,
                average_spent=round(average_spent, 2),
                latest_month_spent=round(latest_month_spent, 2),
                note=note,
            )
        )

    return sorted(
        suggestions,
        key=lambda item: (item.suggested_amount, item.latest_month_spent, item.average_spent),
        reverse=True,
    )[:limit]


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
    existing_categories = {item.category for item in budget_responses}
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
        suggestions=build_budget_suggestions(
            db,
            owner_id=owner_id,
            month=month,
            account_id=account_id,
            existing_categories=existing_categories,
        ),
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


def copy_previous_month_budgets(
    db: Session,
    owner_id: int,
    month: str,
    account_id: int | None = None,
) -> BudgetCopyResponse:
    source_month = shift_month_label(month, -1)
    source_budgets = (
        build_budget_scope_query(
            db,
            owner_id,
            month=source_month,
            account_id=account_id,
        )
        .order_by(BudgetPlan.category.asc(), BudgetPlan.id.asc())
        .all()
    )

    if not source_budgets:
        return BudgetCopyResponse(
            source_month=source_month,
            target_month=month,
            account_id=account_id,
            copied_count=0,
            skipped_existing_count=0,
            message=f"No budgets were found in {source_month} for this scope.",
        )

    target_budgets = build_budget_scope_query(
        db,
        owner_id,
        month=month,
        account_id=account_id,
    ).all()
    existing_categories = {budget.category for budget in target_budgets}

    copied_count = 0
    skipped_existing_count = 0
    for source_budget in source_budgets:
        if source_budget.category in existing_categories:
            skipped_existing_count += 1
            continue

        db.add(
            BudgetPlan(
                month=month,
                category=source_budget.category,
                amount=float(source_budget.amount),
                owner_id=owner_id,
                account_id=account_id,
            )
        )
        existing_categories.add(source_budget.category)
        copied_count += 1

    if copied_count > 0:
        db.commit()

    if copied_count == 0:
        message = f"All {source_month} budgets already exist in {month} for this scope."
    elif skipped_existing_count > 0:
        message = (
            f"Copied {copied_count} budgets from {source_month}. "
            f"Skipped {skipped_existing_count} that already existed in {month}."
        )
    else:
        message = f"Copied {copied_count} budgets from {source_month} into {month}."

    return BudgetCopyResponse(
        source_month=source_month,
        target_month=month,
        account_id=account_id,
        copied_count=copied_count,
        skipped_existing_count=skipped_existing_count,
        message=message,
    )


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
