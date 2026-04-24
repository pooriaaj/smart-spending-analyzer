from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Query, Session

from app.models import Account, BudgetPlan, Transaction
from app.services.budget_metrics import (
    build_budget_action_insights,
    build_budget_pace_context,
    build_budget_projection_context,
    compute_budget_status,
    get_default_budget_month,
)
from app.services.llm_service import generate_llm_assistant_response
from app.services.saved_scenario_service import list_saved_scenarios


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def month_bucket_expression(db: Session):
    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    if getattr(dialect_name, "name", None) == "sqlite":
        return func.strftime("%Y-%m", Transaction.date)
    return func.to_char(Transaction.date, "YYYY-MM")


def build_filtered_query(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> Query:
    query = db.query(Transaction).filter(Transaction.owner_id == user_id)
    month_expr = month_bucket_expression(db)

    parsed_start = parse_iso_date(start_date)
    parsed_end = parse_iso_date(end_date)

    if month:
        query = query.filter(month_expr == month)
    if parsed_start:
        query = query.filter(Transaction.date >= parsed_start)
    if parsed_end:
        query = query.filter(Transaction.date <= parsed_end)
    if transaction_type:
        query = query.filter(Transaction.type == transaction_type)
    if category:
        query = query.filter(func.lower(Transaction.category) == category.strip().lower())
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return query


def get_summary(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> dict[str, float]:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    ).with_entities(
        func.coalesce(
            func.sum(case((Transaction.type == "income", Transaction.amount), else_=0.0)),
            0.0,
        ).label("total_income"),
        func.coalesce(
            func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0.0)),
            0.0,
        ).label("total_expenses"),
    )

    totals = query.one()
    total_income = float(totals.total_income or 0.0)
    total_expenses = float(totals.total_expenses or 0.0)

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": total_income - total_expenses,
    }


def get_category_breakdown(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    ).filter(Transaction.type == "expense")

    rows = (
        query.with_entities(
            Transaction.category.label("category"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    return [{"category": row.category, "total": float(row.total)} for row in rows]


def get_monthly_summary(
    db: Session,
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    query = build_filtered_query(
        db,
        user_id,
        month=None,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )

    month_expr = month_bucket_expression(db)

    rows = (
        query.with_entities(
            month_expr.label("month"),
            func.coalesce(
                func.sum(case((Transaction.type == "income", Transaction.amount), else_=0.0)),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0.0)),
                0.0,
            ).label("expenses"),
        )
        .group_by(month_expr)
        .order_by(month_expr)
        .all()
    )

    result = []
    for row in rows:
        income = float(row.income or 0.0)
        expenses = float(row.expenses or 0.0)
        result.append(
            {
                "month": row.month,
                "income": income,
                "expenses": expenses,
                "balance": income - expenses,
            }
        )
    return result


def get_recent_transactions(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
    limit: int = 5,
):
    return (
        build_filtered_query(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .all()
    )


def get_top_expense_categories(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    query = db.query(
        Transaction.category.label("category"),
        func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
    ).filter(
        Transaction.owner_id == user_id,
        Transaction.type == "expense",
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    rows = (
        query.group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
        .all()
    )

    return [{"category": row.category, "total": float(row.total)} for row in rows]


def get_transactions_for_category(
    db: Session,
    user_id: int,
    category: str,
    account_id: int | None = None,
    limit: int = 5,
) -> list[Transaction]:
    query = db.query(Transaction).filter(
        Transaction.owner_id == user_id,
        func.lower(Transaction.category) == category.strip().lower(),
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .all()
    )


def get_top_categories_with_transactions(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    category_limit: int = 3,
    transaction_limit: int = 3,
) -> list[dict[str, Any]]:
    top_categories = get_top_expense_categories(
        db,
        user_id,
        account_id=account_id,
        limit=category_limit,
    )

    result = []
    for item in top_categories:
        txs = get_transactions_for_category(
            db,
            user_id,
            item["category"],
            account_id=account_id,
            limit=transaction_limit,
        )
        result.append(
            {
                "category": item["category"],
                "total": item["total"],
                "transactions": txs,
            }
        )

    return result


def get_account_comparison_snapshot(
    db: Session,
    user_id: int,
) -> list[dict[str, Any]]:
    accounts = (
        db.query(Account)
        .filter(
            Account.owner_id == user_id,
            Account.is_active.is_(True),
        )
        .order_by(Account.name.asc(), Account.id.asc())
        .all()
    )

    comparison: list[dict[str, Any]] = []
    for account in accounts:
        summary = get_summary(db, user_id, account_id=account.id)
        top_category = get_top_expense_category(db, user_id, account_id=account.id)
        comparison.append(
            {
                "account_id": account.id,
                "name": account.name,
                "type": account.type,
                "total_income": float(summary["total_income"]),
                "total_expenses": float(summary["total_expenses"]),
                "balance": float(summary["balance"]),
                "top_category": top_category["category"] if top_category else None,
                "top_category_amount": float(top_category["total"]) if top_category else 0.0,
            }
        )

    return sorted(
        comparison,
        key=lambda item: (item["total_expenses"], item["total_income"]),
        reverse=True,
    )


def get_top_expense_category(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any] | None:
    query = build_filtered_query(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    ).filter(Transaction.type == "expense")

    row = (
        query.with_entities(
            Transaction.category.label("category"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .first()
    )

    if not row:
        return None

    return {
        "category": row.category,
        "total": float(row.total),
    }
def get_budget_progress_snapshot(
    db: Session,
    user_id: int,
    month: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    budget_month = month or get_default_budget_month()
    query = db.query(BudgetPlan).filter(
        BudgetPlan.owner_id == user_id,
        BudgetPlan.month == budget_month,
    )

    if account_id is None:
        query = query.filter(BudgetPlan.account_id.is_(None))
    else:
        query = query.filter(BudgetPlan.account_id == account_id)

    budgets = query.order_by(BudgetPlan.category.asc(), BudgetPlan.id.asc()).all()

    items: list[dict[str, Any]] = []
    for budget in budgets:
        summary = get_summary(
            db,
            user_id,
            month=budget.month,
            transaction_type="expense",
            category=budget.category,
            account_id=budget.account_id,
        )
        spent_amount = float(summary["total_expenses"])
        remaining_amount, usage_percent, status = compute_budget_status(
            float(budget.amount),
            spent_amount,
        )
        pace_context = build_budget_pace_context(
            month=budget.month,
            amount=float(budget.amount),
            spent_amount=spent_amount,
            remaining_amount=remaining_amount,
        )
        projection_context = build_budget_projection_context(
            month=budget.month,
            amount=float(budget.amount),
            spent_amount=spent_amount,
        )
        items.append(
            {
                "id": budget.id,
                "category": budget.category,
                "amount": float(budget.amount),
                "spent_amount": spent_amount,
                "remaining_amount": remaining_amount,
                "usage_percent": usage_percent,
                "status": status,
                "days_total": pace_context["days_total"],
                "days_elapsed": pace_context["days_elapsed"],
                "days_remaining": pace_context["days_remaining"],
                "daily_allowance": pace_context["daily_allowance"],
                "daily_pace": pace_context["daily_pace"],
                "pace_note": pace_context["pace_note"],
                "projected_spent_amount": projection_context["projected_spent_amount"],
                "projected_remaining_amount": projection_context["projected_remaining_amount"],
                "projected_usage_percent": projection_context["projected_usage_percent"],
                "projected_status": projection_context["projected_status"],
                "projection_note": projection_context["projection_note"],
            }
        )

    issue_priority = {"over_budget": 0, "at_risk": 1, "on_track": 2}
    items_by_priority = sorted(
        items,
        key=lambda item: (
            issue_priority.get(item["status"], 3),
            -item["usage_percent"],
            item["category"].lower(),
        ),
    )
    projected_items_by_priority = sorted(
        items,
        key=lambda item: (
            issue_priority.get(item["projected_status"], 3),
            -(item["projected_usage_percent"] or 0.0),
            item["category"].lower(),
        ),
    )

    total_budgeted = sum(item["amount"] for item in items)
    total_spent = sum(item["spent_amount"] for item in items)
    total_remaining = sum(item["remaining_amount"] for item in items)
    over_budget_count = sum(1 for item in items if item["status"] == "over_budget")
    at_risk_count = sum(1 for item in items if item["status"] == "at_risk")
    on_track_count = sum(1 for item in items if item["status"] == "on_track")
    projected_total_spent = sum(item["projected_spent_amount"] or 0.0 for item in items)
    projected_total_remaining = sum(item["projected_remaining_amount"] or 0.0 for item in items)
    projected_over_budget_count = sum(
        1 for item in items if item["projected_status"] == "over_budget"
    )
    projected_at_risk_count = sum(
        1 for item in items if item["projected_status"] == "at_risk"
    )
    projected_on_track_count = sum(
        1 for item in items if item["projected_status"] == "on_track"
    )

    return {
        "month": budget_month,
        "budget_count": len(items),
        "total_budgeted": total_budgeted,
        "total_spent": total_spent,
        "total_remaining": total_remaining,
        "over_budget_count": over_budget_count,
        "at_risk_count": at_risk_count,
        "on_track_count": on_track_count,
        "projected_total_spent": projected_total_spent,
        "projected_total_remaining": projected_total_remaining,
        "projected_over_budget_count": projected_over_budget_count,
        "projected_at_risk_count": projected_at_risk_count,
        "projected_on_track_count": projected_on_track_count,
        "items": items,
        "issue_items": items_by_priority[:3],
        "projected_issue_items": projected_items_by_priority[:3],
    }


def build_financial_snapshot(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    summary = get_summary(db, user_id, account_id=account_id)
    monthly_summary = get_monthly_summary(db, user_id, account_id=account_id)
    top_category = get_top_expense_category(db, user_id, account_id=account_id)

    total_income = float(summary["total_income"])
    total_expenses = float(summary["total_expenses"])
    balance = float(summary["balance"])

    current_month = monthly_summary[-1]["month"] if monthly_summary else None
    previous_month = monthly_summary[-2]["month"] if len(monthly_summary) >= 2 else None

    current_month_expenses = monthly_summary[-1]["expenses"] if monthly_summary else 0.0
    previous_month_expenses = monthly_summary[-2]["expenses"] if len(monthly_summary) >= 2 else 0.0

    expense_change_percent = None
    if previous_month_expenses > 0:
        expense_change_percent = (
            (current_month_expenses - previous_month_expenses) / previous_month_expenses
        ) * 100

    top_category_name = top_category["category"] if top_category else None
    top_category_amount = float(top_category["total"]) if top_category else 0.0

    top_category_share_percent = None
    if total_expenses > 0 and top_category_amount > 0:
        top_category_share_percent = (top_category_amount / total_expenses) * 100

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": balance,
        "top_category": top_category_name,
        "top_category_amount": top_category_amount,
        "top_category_share_percent": top_category_share_percent,
        "current_month": current_month,
        "previous_month": previous_month,
        "current_month_expenses": current_month_expenses,
        "previous_month_expenses": previous_month_expenses,
        "expense_change_percent": expense_change_percent,
    }


def shift_month_label(month: str, offset: int) -> str:
    year_text, month_text = month.split("-")
    year = int(year_text)
    month_number = int(month_text)
    total_months = year * 12 + (month_number - 1) + offset
    shifted_year = total_months // 12
    shifted_month = total_months % 12 + 1
    return f"{shifted_year:04d}-{shifted_month:02d}"


def build_future_balance_simulation(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    *,
    months: int = 6,
    income_adjustment: float = 0.0,
    expense_adjustment: float = 0.0,
    target_balance: float | None = None,
    event_month_offset: int | None = None,
    event_amount: float = 0.0,
    event_label: str | None = None,
    scope_label: str = "All accounts combined",
) -> dict[str, Any]:
    sanitized_months = max(1, min(int(months or 6), 12))
    financial_snapshot = build_financial_snapshot(db, user_id, account_id=account_id)
    monthly_summary = get_monthly_summary(db, user_id, account_id=account_id)
    current_month = get_default_budget_month()
    historical_months = [
        item for item in monthly_summary if item["month"] != current_month
    ] or monthly_summary
    recent_months = (
        historical_months[-3:] if len(historical_months) >= 3 else historical_months
    )
    recent_month_labels = [item["month"] for item in recent_months]

    if recent_months:
        baseline_monthly_income = sum(item["income"] for item in recent_months) / len(recent_months)
        baseline_monthly_expenses = sum(item["expenses"] for item in recent_months) / len(recent_months)
    else:
        baseline_monthly_income = 0.0
        baseline_monthly_expenses = 0.0

    budget_snapshot = get_budget_progress_snapshot(
        db,
        user_id,
        month=current_month,
        account_id=account_id,
    )
    budget_projection = float(budget_snapshot["projected_total_spent"] or 0.0)
    use_budget_projection = budget_snapshot["budget_count"] > 0 and budget_projection > 0
    expense_baseline = (
        max(baseline_monthly_expenses, budget_projection)
        if use_budget_projection
        else baseline_monthly_expenses
    )

    adjusted_monthly_income = max(0.0, baseline_monthly_income + float(income_adjustment or 0.0))
    adjusted_monthly_expenses = max(0.0, expense_baseline + float(expense_adjustment or 0.0))
    monthly_net_change = adjusted_monthly_income - adjusted_monthly_expenses
    baseline_monthly_net_change = baseline_monthly_income - expense_baseline
    starting_balance = float(financial_snapshot["balance"])
    start_month = shift_month_label(current_month, 1)
    planned_event_amount = round(float(event_amount or 0.0), 2)
    normalized_event_offset = (
        int(event_month_offset)
        if event_month_offset is not None and 1 <= int(event_month_offset) <= sanitized_months
        else None
    )
    default_event_label = "One-time income" if planned_event_amount > 0 else "One-time expense"
    normalized_event_label = str(event_label or "").strip() or default_event_label
    event_month_label = (
        shift_month_label(start_month, normalized_event_offset - 1)
        if normalized_event_offset is not None and abs(planned_event_amount) > 0
        else None
    )

    timeline: list[dict[str, Any]] = []
    running_balance = starting_balance
    baseline_running_balance = starting_balance
    lowest_balance = starting_balance

    for offset in range(sanitized_months):
        month_label = shift_month_label(start_month, offset)
        month_event_amount = (
            planned_event_amount
            if normalized_event_offset is not None
            and abs(planned_event_amount) > 0
            and normalized_event_offset == offset + 1
            else 0.0
        )
        scenario_net_change = monthly_net_change + month_event_amount
        baseline_running_balance += baseline_monthly_net_change
        running_balance += scenario_net_change
        lowest_balance = min(lowest_balance, running_balance)
        timeline.append(
            {
                "month": month_label,
                "income": round(adjusted_monthly_income, 2),
                "expenses": round(adjusted_monthly_expenses, 2),
                "net_change": round(scenario_net_change, 2),
                "baseline_ending_balance": round(baseline_running_balance, 2),
                "ending_balance": round(running_balance, 2),
                "balance_delta": round(running_balance - baseline_running_balance, 2),
                "one_time_event_amount": round(month_event_amount, 2),
                "one_time_event_label": normalized_event_label if month_event_amount else None,
            }
        )

    projected_end_balance = round(running_balance, 2)
    baseline_projected_end_balance = round(baseline_running_balance, 2)
    scenario_impact_amount = round(projected_end_balance - baseline_projected_end_balance, 2)
    projected_change_amount = round(projected_end_balance - starting_balance, 2)
    goal_balance_value = round(float(target_balance), 2) if target_balance and target_balance > 0 else None
    goal_gap_amount: float | None = None
    required_monthly_net: float | None = None
    required_income_lift: float | None = None
    required_expense_reduction: float | None = None
    goal_note: str | None = None
    reduction_plan_target: float | None = None
    reduction_plan_coverage_amount: float | None = None

    if lowest_balance < 0:
        risk_level = "high"
    elif monthly_net_change < 0:
        risk_level = "watch"
    else:
        risk_level = "healthy"

    if projected_change_amount < 0:
        narrative = (
            f"At this pace, your balance is projected to fall by "
            f"{format_currency(abs(projected_change_amount))} over the next {sanitized_months} month(s) "
            f"and land near {format_currency(projected_end_balance)}."
        )
    elif projected_change_amount > 0:
        narrative = (
            f"At this pace, your balance is projected to grow by "
            f"{format_currency(projected_change_amount)} over the next {sanitized_months} month(s) "
            f"and reach about {format_currency(projected_end_balance)}."
        )
    else:
        narrative = (
            f"At this pace, your balance is projected to stay roughly flat over the next "
            f"{sanitized_months} month(s) around {format_currency(projected_end_balance)}."
        )

    if event_month_label and abs(planned_event_amount) > 0:
        event_direction = "boost" if planned_event_amount > 0 else "expense"
        narrative = (
            f"{narrative} This includes a planned {format_currency(abs(planned_event_amount))} "
            f"{event_direction} in {event_month_label} for {normalized_event_label}."
        )

    assumptions = []
    if recent_months:
        assumptions.append(
            f"Baseline uses the last {len(recent_months)} month(s) of scoped income and expense history."
        )
    else:
        assumptions.append("No monthly history was available, so the baseline starts from zero activity.")

    if use_budget_projection:
        assumptions.append(
            f"Current budget projections for {current_month} were used to anchor expense pace at "
            f"{format_currency(expense_baseline)}."
        )
    else:
        assumptions.append(
            f"Expense pace is based on a historical average of {format_currency(expense_baseline)} per month."
        )

    if income_adjustment or expense_adjustment:
        assumptions.append(
            f"Scenario adjustments applied: income {format_currency(float(income_adjustment or 0.0))} "
            f"and expenses {format_currency(float(expense_adjustment or 0.0))} per month."
        )
    else:
        assumptions.append("No extra monthly scenario adjustments were applied.")

    if event_month_label and abs(planned_event_amount) > 0:
        assumptions.append(
            f"One-time event: {normalized_event_label} in {event_month_label} for "
            f"{format_signed_currency(planned_event_amount)}."
        )
    elif event_month_offset is not None and abs(planned_event_amount) > 0:
        assumptions.append("The one-time event was outside the simulated window, so it was ignored.")

    if goal_balance_value is not None:
        goal_gap_amount = round(goal_balance_value - projected_end_balance, 2)
        monthly_improvement_needed = round(
            max(goal_gap_amount / sanitized_months, 0.0),
            2,
        )
        required_monthly_net = round(monthly_net_change + monthly_improvement_needed, 2)
        required_income_lift = monthly_improvement_needed
        required_expense_reduction = monthly_improvement_needed

        if projected_end_balance >= goal_balance_value:
            goal_note = (
                f"At the current pace, this scenario already reaches the target balance of "
                f"{format_currency(goal_balance_value)}."
            )
        else:
            goal_note = (
                f"To reach {format_currency(goal_balance_value)} in {sanitized_months} month(s), "
                f"you would need about {format_currency(monthly_improvement_needed)} more net cash flow "
                "per month. That could come from extra income, lower expenses, or a mix of both."
            )

    if required_expense_reduction and required_expense_reduction > 0:
        reduction_plan_target = required_expense_reduction
    elif monthly_net_change < 0:
        reduction_plan_target = round(abs(monthly_net_change), 2)

    reduction_plan = build_simulation_reduction_plan(
        db,
        user_id,
        account_id=account_id,
        target_reduction=reduction_plan_target or 0.0,
        recent_month_labels=recent_month_labels,
        budget_items=budget_snapshot["items"],
    )
    if reduction_plan:
        reduction_plan_coverage_amount = round(
            sum(item["suggested_monthly_reduction"] for item in reduction_plan),
            2,
        )

    return {
        "scope_label": scope_label,
        "start_month": start_month,
        "months": sanitized_months,
        "starting_balance": round(starting_balance, 2),
        "baseline_monthly_income": round(baseline_monthly_income, 2),
        "baseline_monthly_expenses": round(expense_baseline, 2),
        "adjusted_monthly_income": round(adjusted_monthly_income, 2),
        "adjusted_monthly_expenses": round(adjusted_monthly_expenses, 2),
        "monthly_net_change": round(monthly_net_change, 2),
        "baseline_monthly_net_change": round(baseline_monthly_net_change, 2),
        "baseline_projected_end_balance": baseline_projected_end_balance,
        "scenario_impact_amount": scenario_impact_amount,
        "projected_change_amount": projected_change_amount,
        "projected_end_balance": projected_end_balance,
        "risk_level": risk_level,
        "narrative": narrative,
        "one_time_event_month": event_month_label,
        "one_time_event_amount": planned_event_amount if event_month_label else None,
        "one_time_event_label": normalized_event_label if event_month_label else None,
        "goal_balance": goal_balance_value,
        "goal_gap_amount": goal_gap_amount,
        "required_monthly_net": required_monthly_net,
        "required_income_lift": required_income_lift,
        "required_expense_reduction": required_expense_reduction,
        "goal_note": goal_note,
        "reduction_plan_target": reduction_plan_target,
        "reduction_plan_coverage_amount": reduction_plan_coverage_amount,
        "assumptions": assumptions,
        "timeline": timeline,
        "reduction_plan": reduction_plan,
    }


def build_simulation_reduction_plan(
    db: Session,
    user_id: int,
    *,
    account_id: int | None,
    target_reduction: float,
    recent_month_labels: list[str],
    budget_items: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    if target_reduction <= 0:
        return []

    issue_lookup = {
        normalize_text_for_matching(item["category"]): item
        for item in budget_items
        if item.get("status") != "on_track" or item.get("projected_status") != "on_track"
    }

    category_candidates: list[dict[str, Any]] = []
    if recent_month_labels:
        month_expr = month_bucket_expression(db)
        query = db.query(
            Transaction.category.label("category"),
            month_expr.label("month"),
            func.coalesce(func.sum(Transaction.amount), 0.0).label("total"),
        ).filter(
            Transaction.owner_id == user_id,
            Transaction.type == "expense",
            month_expr.in_(recent_month_labels),
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
            category_name = str(row.category or "").strip()
            if not category_name:
                continue
            category_totals = totals_by_category.setdefault(category_name, {})
            category_totals[row.month] = float(row.total or 0.0)

        for category_name, month_totals in totals_by_category.items():
            current_monthly_spend = sum(
                month_totals.get(label, 0.0) for label in recent_month_labels
            ) / len(recent_month_labels)
            if current_monthly_spend <= 0:
                continue

            issue_item = issue_lookup.get(normalize_text_for_matching(category_name))
            priority = 0 if issue_item else 1
            if issue_item and issue_item.get("projected_status") == "over_budget":
                priority = -1

            reason = (
                "Already showing budget pressure in the current outlook."
                if issue_item
                else "One of your larger recurring expense categories."
            )

            category_candidates.append(
                {
                    "category": category_name,
                    "current_monthly_spend": round(current_monthly_spend, 2),
                    "priority": priority,
                    "reason": reason,
                }
            )

    if not category_candidates:
        top_categories = get_top_expense_categories(
            db,
            user_id,
            account_id=account_id,
            limit=limit,
        )
        for item in top_categories:
            category_candidates.append(
                {
                    "category": item["category"],
                    "current_monthly_spend": round(float(item["total"]), 2),
                    "priority": 1,
                    "reason": "One of your larger expense categories.",
                }
            )

    selected = sorted(
        category_candidates,
        key=lambda item: (item["priority"], -item["current_monthly_spend"], item["category"].lower()),
    )[:limit]

    if not selected:
        return []

    for item in selected:
        item["suggested_monthly_reduction"] = 0.0
        item["max_reduction"] = round(item["current_monthly_spend"] * 0.7, 2)

    remaining = round(target_reduction, 2)
    for _ in range(5):
        candidates = [
            item for item in selected
            if item["max_reduction"] - item["suggested_monthly_reduction"] > 0.01
        ]
        if remaining <= 0.01 or not candidates:
            break

        weight_sum = sum(item["current_monthly_spend"] for item in candidates)
        distributed = 0.0
        for item in candidates:
            if weight_sum > 0:
                proportional_share = remaining * (item["current_monthly_spend"] / weight_sum)
            else:
                proportional_share = remaining / len(candidates)

            available = item["max_reduction"] - item["suggested_monthly_reduction"]
            additional = min(proportional_share, available)
            item["suggested_monthly_reduction"] += additional
            distributed += additional

        if distributed <= 0.01:
            break
        remaining = round(max(remaining - distributed, 0.0), 2)

    total_selected_spend = sum(item["current_monthly_spend"] for item in selected)
    return [
        {
            "category": item["category"],
            "current_monthly_spend": round(item["current_monthly_spend"], 2),
            "suggested_monthly_reduction": round(item["suggested_monthly_reduction"], 2),
            "suggested_budget_amount": round(
                max(item["current_monthly_spend"] - item["suggested_monthly_reduction"], 0.01),
                2,
            ),
            "share_percent": round(
                (item["current_monthly_spend"] / total_selected_spend) * 100, 1
            ) if total_selected_spend > 0 else 0.0,
            "reason": item["reason"],
        }
        for item in selected
        if item["suggested_monthly_reduction"] > 0.01
    ]


def get_spending_insights(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)

    total_expenses = snapshot["total_expenses"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    top_category_share_percent = snapshot["top_category_share_percent"]
    current_month = snapshot["current_month"]
    current_month_expenses = snapshot["current_month_expenses"]
    previous_month_expenses = snapshot["previous_month_expenses"]
    expense_change_percent = snapshot["expense_change_percent"]

    if total_expenses == 0:
        return {
            "current_month": None,
            "current_month_expenses": 0.0,
            "previous_month_expenses": 0.0,
            "expense_change_percent": None,
            "top_category": None,
            "top_category_amount": 0.0,
            "top_category_share_percent": None,
            "insights": ["No expense data available yet."],
            "recommendations": ["Add more transactions to unlock spending insights."],
        }

    insights: list[str] = []
    recommendations: list[str] = []

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

    return {
        "current_month": current_month,
        "current_month_expenses": current_month_expenses,
        "previous_month_expenses": previous_month_expenses,
        "expense_change_percent": expense_change_percent,
        "top_category": top_category,
        "top_category_amount": top_category_amount,
        "top_category_share_percent": top_category_share_percent,
        "insights": insights,
        "recommendations": recommendations,
    }


def get_overspending_alerts(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    monthly_summary = get_monthly_summary(db, user_id, account_id=account_id)
    monthly_breakdowns = {
        item["month"]: get_category_breakdown(
            db,
            user_id,
            month=item["month"],
            account_id=account_id,
        )
        for item in monthly_summary
    }

    if not monthly_summary:
        return {"current_month": None, "alerts": []}

    current = monthly_summary[-1]
    current_month = current["month"]
    current_total = current["expenses"]

    alerts: list[dict[str, str]] = []

    if len(monthly_summary) >= 2:
        previous = monthly_summary[-2]
        previous_total = previous["expenses"]

        if previous_total > 0:
            change_percent = ((current_total - previous_total) / previous_total) * 100

            if change_percent >= 25:
                alerts.append(
                    {
                        "level": "high",
                        "title": "Monthly spending spike",
                        "message": f"Your spending in {current_month} is up {change_percent:.1f}% compared with {previous['month']}.",
                    }
                )
            elif change_percent >= 15:
                alerts.append(
                    {
                        "level": "medium",
                        "title": "Monthly spending increase",
                        "message": f"Your spending in {current_month} is up {change_percent:.1f}% compared with {previous['month']}.",
                    }
                )

    current_categories = monthly_breakdowns.get(current_month, [])
    current_total_expenses = sum(item["total"] for item in current_categories)

    if current_total_expenses > 0:
        for item in current_categories:
            share = (item["total"] / current_total_expenses) * 100

            if share >= 45:
                alerts.append(
                    {
                        "level": "high",
                        "title": f"{item['category']} is dominating spending",
                        "message": f"{item['category']} makes up {share:.1f}% of your expenses in {current_month}.",
                    }
                )
            elif share >= 30:
                alerts.append(
                    {
                        "level": "medium",
                        "title": f"{item['category']} is a major spending category",
                        "message": f"{item['category']} makes up {share:.1f}% of your expenses in {current_month}.",
                    }
                )

    if not alerts:
        alerts.append(
            {
                "level": "low",
                "title": "No major overspending alert",
                "message": "Your latest spending pattern does not show a strong overspending signal right now.",
            }
        )

    return {"current_month": current_month, "alerts": alerts}


def get_category_trends(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    monthly_summary = get_monthly_summary(db, user_id, account_id=account_id)

    if not monthly_summary:
        return {
            "current_month": None,
            "previous_month": None,
            "top_increases": [],
            "top_decreases": [],
            "summary": ["No expense trend data available yet."],
        }

    if len(monthly_summary) < 2:
        return {
            "current_month": monthly_summary[-1]["month"],
            "previous_month": None,
            "top_increases": [],
            "top_decreases": [],
            "summary": ["At least two months of expense data are needed for category trend comparison."],
        }

    previous_month = monthly_summary[-2]["month"]
    current_month = monthly_summary[-1]["month"]

    previous_categories = {
        item["category"]: item["total"]
        for item in get_category_breakdown(
            db,
            user_id,
            month=previous_month,
            account_id=account_id,
        )
    }
    current_categories = {
        item["category"]: item["total"]
        for item in get_category_breakdown(
            db,
            user_id,
            month=current_month,
            account_id=account_id,
        )
    }

    all_categories = sorted(set(previous_categories.keys()) | set(current_categories.keys()))
    trend_items = []

    for category in all_categories:
        previous_amount = float(previous_categories.get(category, 0.0))
        current_amount = float(current_categories.get(category, 0.0))
        change_amount = current_amount - previous_amount

        change_percent = None
        if previous_amount > 0:
            change_percent = (change_amount / previous_amount) * 100

        trend_items.append(
            {
                "category": category,
                "current_amount": current_amount,
                "previous_amount": previous_amount,
                "change_amount": change_amount,
                "change_percent": change_percent,
            }
        )

    increases = sorted(
        [item for item in trend_items if item["change_amount"] > 0],
        key=lambda item: item["change_amount"],
        reverse=True,
    )[:5]

    decreases = sorted(
        [item for item in trend_items if item["change_amount"] < 0],
        key=lambda item: item["change_amount"],
    )[:5]

    summary: list[str] = []

    if increases:
        top_up = increases[0]
        summary.append(
            f"The biggest increase from {previous_month} to {current_month} was {top_up['category']}, up ${top_up['change_amount']:.2f}."
        )

    if decreases:
        top_down = decreases[0]
        summary.append(
            f"The biggest decrease from {previous_month} to {current_month} was {top_down['category']}, down ${abs(top_down['change_amount']):.2f}."
        )

    if not summary:
        summary.append(
            f"No category-level increase or decrease was detected between {previous_month} and {current_month}."
        )

    return {
        "current_month": current_month,
        "previous_month": previous_month,
        "top_increases": increases,
        "top_decreases": decreases,
        "summary": summary,
    }


def extract_recent_context(history: list[Any]) -> str:
    context_lines: list[str] = []

    for message in history[-8:]:
        role = getattr(message, "role", "").lower()
        content = getattr(message, "content", "").strip()

        if not content:
            continue

        if role == "user":
            context_lines.append(f"User: {content}")
        elif role == "assistant":
            context_lines.append(f"Assistant: {content}")

    return "\n".join(context_lines)


def format_currency(value: float) -> str:
    return f"${value:.2f}"


def format_signed_currency(value: float) -> str:
    prefix = "+" if value >= 0 else "-"
    return f"{prefix}${abs(value):.2f}"


def build_saved_scenario_projection_snapshots(
    db: Session,
    user_id: int,
    account_id: int | None,
    scope_label: str,
) -> list[dict[str, Any]]:
    saved_scenarios = list_saved_scenarios(
        db=db,
        owner_id=user_id,
        account_id=account_id,
    )
    recurring_expenses = get_recurring_expense_patterns(
        db=db,
        user_id=user_id,
        account_id=account_id,
        limit=3,
    )
    simulation_recommendations = build_future_simulation_recommendations(
        db=db,
        user_id=user_id,
        account_id=account_id,
        months=6,
        scope_label=(
            "All accounts combined"
            if account_id is None
            else f"Account {account_id}"
        ),
    )
    snapshots: list[dict[str, Any]] = []

    for scenario in saved_scenarios:
        simulation = build_future_balance_simulation(
            db=db,
            user_id=user_id,
            account_id=account_id,
            months=scenario.months,
            income_adjustment=scenario.income_adjustment,
            expense_adjustment=scenario.expense_adjustment,
            target_balance=scenario.target_balance,
            event_month_offset=scenario.event_month_offset,
            event_amount=scenario.event_amount or 0.0,
            event_label=scenario.event_label,
            scope_label=scope_label,
        )
        snapshots.append(
            {
                "id": scenario.id,
                "name": scenario.name,
                "months": scenario.months,
                "projected_end_balance": simulation["projected_end_balance"],
                "monthly_net_change": simulation["monthly_net_change"],
                "risk_level": simulation["risk_level"],
                "lowest_balance": min(
                    [
                        float(item["ending_balance"])
                        for item in simulation["timeline"]
                    ]
                    or [float(simulation["starting_balance"])]
                ),
                "goal_note": simulation["goal_note"],
                "goal_balance": simulation["goal_balance"],
                "goal_gap_amount": simulation["goal_gap_amount"],
                "one_time_event_month": simulation["one_time_event_month"],
                "one_time_event_amount": simulation["one_time_event_amount"],
                "one_time_event_label": simulation["one_time_event_label"],
                "income_adjustment": scenario.income_adjustment,
                "expense_adjustment": scenario.expense_adjustment,
                "target_balance": scenario.target_balance,
            }
        )

    return sorted(
        snapshots,
        key=lambda item: (
            float(item["projected_end_balance"]),
            float(item["monthly_net_change"]),
            item["name"].lower(),
        ),
        reverse=True,
    )


def get_saved_scenario_risk_rank(risk_level: str | None) -> int:
    if risk_level == "healthy":
        return 2
    if risk_level == "watch":
        return 1
    return 0


def detect_saved_scenario_comparison_focus(question: str, context_text: str) -> str:
    normalized_text = normalize_text_for_matching(f"{context_text} {question}")

    if any(
        phrase in normalized_text
        for phrase in [
            "safest",
            "safe plan",
            "safer",
            "lowest risk",
            "least risky",
            "most stable",
            "risk",
        ]
    ):
        return "risk"

    if any(
        phrase in normalized_text
        for phrase in [
            "monthly net",
            "cash flow",
            "net change",
            "per month",
        ]
    ):
        return "monthly_net"

    if any(
        phrase in normalized_text
        for phrase in [
            "target",
            "goal",
            "reach",
            "hit",
        ]
    ):
        return "goal"

    return "end_balance"


def is_saved_scenario_plan_comparison_question(question: str, context_text: str) -> bool:
    normalized_text = normalize_text_for_matching(f"{context_text} {question}")

    return any(
        phrase in normalized_text
        for phrase in [
            "which plan",
            "best plan",
            "better plan",
            "strongest plan",
            "safest plan",
            "which one is safest",
            "which one is stronger",
            "which one is best",
            "best cash flow plan",
            "best monthly net plan",
            "closest to my goal",
            "closest to my target",
            "goal leader",
        ]
    )


def build_saved_scenario_comparison_key(
    scenario: dict[str, Any],
    comparison_focus: str,
) -> tuple[Any, ...]:
    projected_end_balance = float(scenario["projected_end_balance"])
    monthly_net_change = float(scenario["monthly_net_change"])
    risk_rank = get_saved_scenario_risk_rank(scenario.get("risk_level"))
    lowest_balance = float(scenario.get("lowest_balance") or 0.0)
    goal_balance = scenario.get("goal_balance")
    goal_gap_amount = scenario.get("goal_gap_amount")
    has_goal = goal_balance is not None
    goal_achieved = bool(has_goal and goal_gap_amount is not None and goal_gap_amount <= 0)
    goal_progress_key = (
        -float(goal_gap_amount)
        if goal_gap_amount is not None
        else float("-inf")
    )

    if comparison_focus == "risk":
        return (
            risk_rank,
            lowest_balance,
            projected_end_balance,
            monthly_net_change,
            scenario["name"].lower(),
        )

    if comparison_focus == "monthly_net":
        return (
            monthly_net_change,
            risk_rank,
            projected_end_balance,
            scenario["name"].lower(),
        )

    if comparison_focus == "goal":
        return (
            1 if has_goal else 0,
            1 if goal_achieved else 0,
            goal_progress_key,
            projected_end_balance,
            monthly_net_change,
            scenario["name"].lower(),
        )

    return (
        projected_end_balance,
        monthly_net_change,
        risk_rank,
        scenario["name"].lower(),
    )


def build_saved_scenario_supporting_point(
    scenario: dict[str, Any],
    comparison_focus: str = "end_balance",
) -> str:
    point = (
        f"{scenario['name']}: ends at {format_currency(scenario['projected_end_balance'])}, "
        f"net {format_currency(scenario['monthly_net_change'])}/month, risk {scenario['risk_level']}"
    )

    if comparison_focus == "risk":
        point += f", floor {format_currency(scenario.get('lowest_balance') or 0.0)}"

    if scenario.get("goal_balance") is not None:
        goal_balance = float(scenario["goal_balance"])
        goal_gap_amount = scenario.get("goal_gap_amount")
        if goal_gap_amount is not None and goal_gap_amount <= 0:
            point += f". Goal met: target {format_currency(goal_balance)}"
        elif goal_gap_amount is not None:
            point += (
                f". Goal gap: {format_currency(float(goal_gap_amount))} short of "
                f"{format_currency(goal_balance)}"
            )
        else:
            point += f". Target: {format_currency(goal_balance)}"

    if scenario["goal_note"]:
        point += f". {scenario['goal_note']}"
    if scenario["one_time_event_amount"] is not None and scenario["one_time_event_month"]:
        point += (
            f". Event: {scenario['one_time_event_label']} in {scenario['one_time_event_month']} "
            f"for {format_signed_currency(scenario['one_time_event_amount'])}"
        )

    return point


def build_saved_scenario_portfolio_summary(
    saved_scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    strongest = (
        sorted(
            saved_scenarios,
            key=lambda item: build_saved_scenario_comparison_key(item, "end_balance"),
            reverse=True,
        )[0]
        if saved_scenarios
        else None
    )
    safest = (
        sorted(
            saved_scenarios,
            key=lambda item: build_saved_scenario_comparison_key(item, "risk"),
            reverse=True,
        )[0]
        if saved_scenarios
        else None
    )
    monthly_net_leader = (
        sorted(
            saved_scenarios,
            key=lambda item: build_saved_scenario_comparison_key(item, "monthly_net"),
            reverse=True,
        )[0]
        if saved_scenarios
        else None
    )
    goal_candidates = [item for item in saved_scenarios if item.get("goal_balance") is not None]
    goal_leader = (
        sorted(
            goal_candidates,
            key=lambda item: build_saved_scenario_comparison_key(item, "goal"),
            reverse=True,
        )[0]
        if goal_candidates
        else None
    )

    return {
        "total": len(saved_scenarios),
        "healthy_count": sum(1 for item in saved_scenarios if item.get("risk_level") == "healthy"),
        "attention_count": sum(
            1 for item in saved_scenarios if item.get("risk_level") in {"watch", "high"}
        ),
        "goal_count": len(goal_candidates),
        "event_count": sum(1 for item in saved_scenarios if item.get("one_time_event_amount") is not None),
        "strongest": strongest,
        "safest": safest,
        "monthly_net_leader": monthly_net_leader,
        "goal_leader": goal_leader,
    }


def format_category_label(value: str | None) -> str:
    if not value:
        return "Unknown"

    normalized = normalize_text_for_matching(value)
    if not normalized:
        return "Unknown"

    return " ".join(word.capitalize() for word in normalized.split())


def normalize_text_for_matching(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def normalize_recurring_description(value: str) -> str:
    normalized = normalize_text_for_matching(value)
    if not normalized:
        return ""

    normalized = re.sub(
        r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"\b\d+\b", " ", normalized)
    return " ".join(normalized.split())


def get_recurring_review_priority(
    *,
    annualized_amount: float,
    latest_change_percent: float | None,
    occurrences: int,
    confidence: float,
) -> tuple[str, str]:
    if latest_change_percent is not None and latest_change_percent >= 8:
        return (
            "high",
            f"Latest charge came in about {latest_change_percent:.0f}% above its usual amount.",
        )

    if annualized_amount >= 500:
        return (
            "high",
            "This is one of your larger recurring costs over a full year.",
        )

    if annualized_amount >= 250 or (occurrences >= 4 and confidence >= 0.9):
        return (
            "medium",
            "This looks consistent enough to review as part of your regular monthly costs.",
        )

    return (
        "low",
        "This looks like a recurring charge, but it is a smaller cost right now.",
    )


def get_recurring_expense_patterns(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    transactions = (
        build_filtered_query(
            db=db,
            user_id=user_id,
            transaction_type="expense",
            account_id=account_id,
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    groups: dict[tuple[str, str], list[Transaction]] = {}
    for transaction in transactions:
        normalized_description = normalize_recurring_description(transaction.description)
        if len(normalized_description) < 3:
            continue
        groups.setdefault((normalized_description, transaction.category), []).append(transaction)

    recurring_items: list[dict[str, Any]] = []
    for (_, category), items in groups.items():
        if len(items) < 2:
            continue

        unique_months = {item.date.strftime("%Y-%m") for item in items}
        if len(unique_months) < 2:
            continue

        intervals = [
            (items[index].date - items[index - 1].date).days
            for index in range(1, len(items))
        ]
        if not intervals:
            continue

        average_interval = sum(intervals) / len(intervals)
        monthly_like = 20 <= average_interval <= 40
        if not monthly_like:
            continue

        amounts = [float(item.amount) for item in items]
        average_amount = sum(amounts) / len(amounts)
        amount_variation = max(amounts) - min(amounts)
        variance_ratio = amount_variation / average_amount if average_amount > 0 else 0.0
        if variance_ratio > 0.25 and amount_variation > 5:
            continue

        latest_item = items[-1]
        latest_amount = float(latest_item.amount)
        day_of_month_range = max(item.date.day for item in items) - min(item.date.day for item in items)
        average_interval_days = max(int(round(average_interval)), 1)
        next_expected_date = latest_item.date + timedelta(days=average_interval_days)
        prior_amounts = amounts[:-1] or amounts
        prior_average_amount = (
            sum(prior_amounts) / len(prior_amounts)
            if prior_amounts
            else average_amount
        )
        latest_change_percent = None
        if prior_average_amount > 0:
            latest_change_percent = ((latest_amount - prior_average_amount) / prior_average_amount) * 100
        confidence = min(
            0.99,
            0.6
            + 0.06 * min(len(items), 4)
            + (0.1 if variance_ratio <= 0.1 else 0.0)
            + (0.1 if day_of_month_range <= 3 else 0.0),
        )
        annualized_amount = round(average_amount * 12, 2)
        review_priority, review_reason = get_recurring_review_priority(
            annualized_amount=annualized_amount,
            latest_change_percent=latest_change_percent,
            occurrences=len(items),
            confidence=confidence,
        )

        recurring_items.append(
            {
                "description": latest_item.description,
                "category": category,
                "occurrences": len(items),
                "cadence": "monthly",
                "average_amount": round(average_amount, 2),
                "latest_amount": round(latest_amount, 2),
                "latest_date": latest_item.date,
                "average_interval_days": average_interval_days,
                "next_expected_date": next_expected_date,
                "annualized_amount": annualized_amount,
                "latest_change_percent": round(latest_change_percent, 1)
                if latest_change_percent is not None
                else None,
                "review_priority": review_priority,
                "review_reason": review_reason,
                "confidence": round(confidence, 2),
            }
        )

    priority_rank = {"high": 2, "medium": 1, "low": 0}
    recurring_items.sort(
        key=lambda item: (
            priority_rank.get(str(item["review_priority"]), 0),
            float(item["annualized_amount"]),
            float(item["average_amount"]),
            float(item["confidence"]),
            item["description"].lower(),
        ),
        reverse=True,
    )
    return recurring_items[:limit]


def build_recurring_savings_opportunities(
    recurring_expenses: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    opportunities = [
        item
        for item in recurring_expenses
        if (item.get("average_amount") or 0.0) > 0
    ]
    priority_rank = {"high": 2, "medium": 1, "low": 0}
    opportunities.sort(
        key=lambda item: (
            priority_rank.get(str(item.get("review_priority")), 0),
            float(item.get("annualized_amount") or 0.0),
            float(item.get("confidence") or 0.0),
        ),
        reverse=True,
    )
    return opportunities[:limit]


def build_future_simulation_recommendations(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    *,
    months: int = 6,
    scope_label: str = "All accounts combined",
) -> dict[str, Any]:
    sanitized_months = max(1, min(int(months or 6), 12))
    saved_scenarios = list_saved_scenarios(
        db=db,
        owner_id=user_id,
        account_id=account_id,
    )
    recurring_expenses = get_recurring_expense_patterns(
        db=db,
        user_id=user_id,
        account_id=account_id,
        limit=5,
    )
    recurring_opportunities = build_recurring_savings_opportunities(recurring_expenses, limit=3)
    baseline_simulation = build_future_balance_simulation(
        db=db,
        user_id=user_id,
        account_id=account_id,
        months=sanitized_months,
        scope_label=scope_label,
    )
    budget_snapshot = get_budget_progress_snapshot(
        db,
        user_id,
        month=get_default_budget_month(),
        account_id=account_id,
    )
    projected_budget_gap = round(
        sum(
            max(float(item.get("projected_spent_amount") or 0.0) - float(item.get("amount") or 0.0), 0.0)
            for item in budget_snapshot["items"]
        ),
        2,
    )

    recommendations: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def amounts_match(left: float | None, right: float | None) -> bool:
        return round(float(left or 0.0), 2) == round(float(right or 0.0), 2)

    def find_saved_match(item: dict[str, Any]) -> int | None:
        for scenario in saved_scenarios:
            if int(scenario.months or 0) != int(item["months"]):
                continue
            if not amounts_match(scenario.income_adjustment, item["income_adjustment"]):
                continue
            if not amounts_match(scenario.expense_adjustment, item["expense_adjustment"]):
                continue
            if not amounts_match(scenario.target_balance, item.get("target_balance")):
                continue
            if int(scenario.event_month_offset or 0) != int(item.get("event_month_offset") or 0):
                continue
            if not amounts_match(scenario.event_amount, item.get("event_amount")):
                continue
            if (scenario.event_label or "").strip() != (item.get("event_label") or "").strip():
                continue
            return scenario.id
        return None

    def add_recommendation(
        *,
        key: str,
        label: str,
        description: str,
        reason: str,
        source: str,
        income_adjustment: float = 0.0,
        expense_adjustment: float = 0.0,
        target_balance: float | None = None,
        event_month_offset: int | None = None,
        event_amount: float = 0.0,
        event_label: str | None = None,
    ) -> None:
        if key in seen_keys:
            return

        simulation = build_future_balance_simulation(
            db=db,
            user_id=user_id,
            account_id=account_id,
            months=sanitized_months,
            income_adjustment=income_adjustment,
            expense_adjustment=expense_adjustment,
            target_balance=target_balance,
            event_month_offset=event_month_offset,
            event_amount=event_amount,
            event_label=event_label,
            scope_label=scope_label,
        )
        recommendations.append(
            {
                "key": key,
                "label": label,
                "description": description,
                "reason": reason,
                "source": source,
                "saved_scenario_id": None,
                "is_saved": False,
                "months": sanitized_months,
                "income_adjustment": round(float(income_adjustment or 0.0), 2),
                "expense_adjustment": round(float(expense_adjustment or 0.0), 2),
                "target_balance": round(float(target_balance), 2) if target_balance else None,
                "event_month_offset": event_month_offset,
                "event_amount": round(float(event_amount or 0.0), 2) if event_amount else None,
                "event_label": event_label,
                "projected_end_balance": simulation["projected_end_balance"],
                "scenario_impact_amount": simulation["scenario_impact_amount"],
                "monthly_net_change": simulation["monthly_net_change"],
                "risk_level": simulation["risk_level"],
            }
        )
        seen_keys.add(key)

    if baseline_simulation.get("reduction_plan_target"):
        required_cut = round(float(baseline_simulation["reduction_plan_target"]), 2)
        add_recommendation(
            key="stabilize-cash-flow",
            label="Stabilize monthly cash flow",
            description=(
                f"Model a {format_currency(required_cut)} monthly expense cut to steady the current balance path."
            ),
            reason=(
                baseline_simulation.get("goal_note")
                or "This is the monthly improvement needed to stop the current projected slide."
            ),
            source="cash_flow",
            expense_adjustment=-required_cut,
        )

    if recurring_opportunities:
        top_item = recurring_opportunities[0]
        add_recommendation(
            key=f"cancel-{normalize_text_for_matching(top_item['description']).replace(' ', '-')}",
            label=f"Cancel {top_item['description']}",
            description=(
                f"Free about {format_currency(top_item['average_amount'])} per month by cutting this recurring charge."
            ),
            reason=top_item["review_reason"],
            source="recurring",
            expense_adjustment=-float(top_item["average_amount"]),
        )

        if len(recurring_opportunities) > 1:
            bundle_amount = round(
                sum(float(item["average_amount"]) for item in recurring_opportunities[:2]),
                2,
            )
            bundle_names = ", ".join(item["description"] for item in recurring_opportunities[:2])
            add_recommendation(
                key="bundle-top-recurring-cuts",
                label="Trim top recurring costs",
                description=(
                    f"Model your two strongest recurring review candidates as a {format_currency(bundle_amount)} monthly cut."
                ),
                reason=f"Bundles {bundle_names} into one cleaner savings scenario.",
                source="recurring_bundle",
                expense_adjustment=-bundle_amount,
            )

    if projected_budget_gap > 0:
        add_recommendation(
            key="reset-budget-pressure",
            label="Reset budget pressure",
            description=(
                f"Cut about {format_currency(projected_budget_gap)} per month to absorb current budget overages."
            ),
            reason=(
                f"Current budget projections are running about {format_currency(projected_budget_gap)} over plan."
            ),
            source="budget_pressure",
            expense_adjustment=-projected_budget_gap,
        )

    recommendations.sort(
        key=lambda item: (
            {"cash_flow": 3, "recurring": 2, "recurring_bundle": 1, "budget_pressure": 0}.get(item["source"], 0),
            float(item["scenario_impact_amount"]),
            float(item["projected_end_balance"]),
        ),
        reverse=True,
    )
    for recommendation in recommendations:
        saved_match_id = find_saved_match(recommendation)
        if saved_match_id is not None:
            recommendation["saved_scenario_id"] = saved_match_id
            recommendation["is_saved"] = True

    return {
        "scope_label": scope_label,
        "items": recommendations[:4],
    }


def get_distinct_categories(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> list[str]:
    query = db.query(Transaction.category).filter(Transaction.owner_id == user_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    categories = {
        (row[0] or "").strip()
        for row in query.distinct().all()
        if row[0] and str(row[0]).strip()
    }

    return sorted(
        categories,
        key=lambda item: (-len(normalize_text_for_matching(item)), item.lower()),
    )


def detect_focus_category(
    question: str,
    context_text: str,
    categories: list[str],
) -> str | None:
    normalized_text = f" {normalize_text_for_matching(f'{context_text} {question}')} "

    for category in categories:
        normalized_category = normalize_text_for_matching(category)
        if not normalized_category:
            continue

        variants = {normalized_category}
        if normalized_category.endswith("ies") and len(normalized_category) > 3:
            variants.add(f"{normalized_category[:-3]}y")
        elif normalized_category.endswith("s") and len(normalized_category) > 1:
            variants.add(normalized_category[:-1])

        if any(f" {variant} " in normalized_text for variant in variants if variant):
            return category

    return None


def detect_named_saved_scenarios(
    question: str,
    context_text: str,
    saved_scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_text = f" {normalize_text_for_matching(f'{context_text} {question}')} "
    matches: list[dict[str, Any]] = []

    for scenario in sorted(saved_scenarios, key=lambda item: len(item["name"]), reverse=True):
        normalized_name = normalize_text_for_matching(scenario["name"])
        if not normalized_name:
            continue

        if f" {normalized_name} " in normalized_text:
            matches.append(scenario)

    deduped: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for scenario in matches:
        if scenario["id"] in seen_ids:
            continue
        deduped.append(scenario)
        seen_ids.add(scenario["id"])

    return deduped


def build_category_focus_snapshot(
    db: Session,
    user_id: int,
    category: str,
    snapshot: dict[str, Any],
    account_id: int | None = None,
) -> dict[str, Any]:
    overall_summary = get_summary(
        db,
        user_id,
        category=category,
        account_id=account_id,
    )
    focus_type = (
        "income"
        if overall_summary["total_income"] > overall_summary["total_expenses"]
        else "expense"
    )
    total_amount = (
        float(overall_summary["total_income"])
        if focus_type == "income"
        else float(overall_summary["total_expenses"])
    )

    current_month = snapshot.get("current_month")
    previous_month = snapshot.get("previous_month")

    current_summary = (
        get_summary(
            db,
            user_id,
            month=current_month,
            category=category,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if current_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )
    previous_summary = (
        get_summary(
            db,
            user_id,
            month=previous_month,
            category=category,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if previous_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )

    current_month_amount = (
        float(current_summary["total_income"])
        if focus_type == "income"
        else float(current_summary["total_expenses"])
    )
    previous_month_amount = (
        float(previous_summary["total_income"])
        if focus_type == "income"
        else float(previous_summary["total_expenses"])
    )

    change_amount = current_month_amount - previous_month_amount
    change_percent = None
    if previous_month_amount > 0:
        change_percent = (change_amount / previous_month_amount) * 100

    month_scope_summary = (
        get_summary(
            db,
            user_id,
            month=current_month,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if current_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )
    month_scope_total = (
        float(month_scope_summary["total_income"])
        if focus_type == "income"
        else float(month_scope_summary["total_expenses"])
    )
    current_share_percent = None
    if month_scope_total > 0 and current_month_amount > 0:
        current_share_percent = (current_month_amount / month_scope_total) * 100

    recent_transactions = get_transactions_for_category(
        db,
        user_id,
        category,
        account_id=account_id,
        limit=3,
    )

    return {
        "category": category,
        "transaction_type": focus_type,
        "total_amount": total_amount,
        "current_month": current_month,
        "previous_month": previous_month,
        "current_month_amount": current_month_amount,
        "previous_month_amount": previous_month_amount,
        "change_amount": change_amount,
        "change_percent": change_percent,
        "current_share_percent": current_share_percent,
        "recent_transactions": recent_transactions,
        "is_top_category": snapshot.get("top_category") == category,
    }


def build_category_focus_supporting_points(
    focus_snapshot: dict[str, Any],
) -> list[str]:
    category = focus_snapshot["category"]
    current_month = focus_snapshot["current_month"]
    previous_month = focus_snapshot["previous_month"]

    points = [
        f"{category} total in this scope: {format_currency(focus_snapshot['total_amount'])}",
    ]

    if current_month:
        points.append(
            f"{current_month}: {format_currency(focus_snapshot['current_month_amount'])}"
        )

    if previous_month and focus_snapshot["previous_month_amount"] > 0:
        direction = "up" if focus_snapshot["change_amount"] >= 0 else "down"
        points.append(
            f"Month-over-month: {direction} {format_currency(abs(focus_snapshot['change_amount']))} from {previous_month}"
        )

    if focus_snapshot["current_share_percent"] is not None:
        share_label = "income" if focus_snapshot["transaction_type"] == "income" else "spending"
        points.append(
            f"{category} makes up {focus_snapshot['current_share_percent']:.1f}% of current-month {share_label}"
        )

    if focus_snapshot["recent_transactions"]:
        recent_text = ", ".join(
            f"{tx.description} ({format_currency(tx.amount)})"
            for tx in focus_snapshot["recent_transactions"]
        )
        points.append(f"Recent matching transactions: {recent_text}")

    return points[:5]


def build_category_focus_answer(
    intent: str,
    mode: str,
    focus_snapshot: dict[str, Any],
    top_category: str | None,
) -> str:
    category = focus_snapshot["category"]
    total_amount = format_currency(focus_snapshot["total_amount"])
    current_month = focus_snapshot["current_month"]
    current_month_amount = format_currency(focus_snapshot["current_month_amount"])
    change_amount = focus_snapshot["change_amount"]
    change_percent = focus_snapshot["change_percent"]
    is_expense = focus_snapshot["transaction_type"] == "expense"
    recent_transactions = focus_snapshot["recent_transactions"]

    change_text = ""
    if current_month:
        change_text = f" In {current_month}, it is {current_month_amount}."
    if change_percent is not None:
        direction = "up" if change_amount >= 0 else "down"
        change_text += f" That is {direction} {abs(change_percent):.1f}% from the previous month."

    if intent == "category_transactions" or intent == "recent":
        recent_hint = (
            f" Recent items include {', '.join(tx.description for tx in recent_transactions[:2])}."
            if recent_transactions
            else ""
        )
        if mode == "strict":
            return f"{category} is where the detail is.{change_text or f' It totals {total_amount} in this scope.'}{recent_hint}"
        if mode == "coach":
            return f"{category} is a good place to zoom in.{change_text or f' It totals {total_amount} in this scope.'}{recent_hint}"
        return f"Here is the focused view for {category}. It totals {total_amount} in this scope.{change_text}{recent_hint}"

    if intent in {"saving_advice", "spending_change", "driver", "alerts"} and is_expense:
        if mode == "strict":
            return f"{category} is worth reviewing closely. It totals {total_amount} in this scope.{change_text}"
        if mode == "coach":
            return f"{category} looks like a practical place to focus. It totals {total_amount} in this scope.{change_text}"
        return f"{category} is a meaningful spending category here. It totals {total_amount} in this scope.{change_text}"

    if focus_snapshot["is_top_category"]:
        return f"{category} is currently your top category in this scope at {total_amount}.{change_text}"

    comparator = f" {top_category} is currently higher." if top_category and top_category != category else ""
    return f"{category} totals {total_amount} in this scope.{change_text}{comparator}"


def classify_question(question: str, context_text: str) -> str:
    text = f"{context_text} {question}".lower().strip()
    has_month_horizon = re.search(r"\d+\s+month", text) is not None
    has_goal_amount = parse_target_balance(text) is not None
    has_one_time_event = (
        parse_one_time_event_amount(text) is not None
        and parse_one_time_event_offset(text) is not None
    )

    if any(
        phrase in text
        for phrase in [
            "future balance",
            "simulate",
            "simulation",
            "forecast my balance",
            "project my balance",
            "months from now",
            "next few months",
            "what will my balance look like",
        ]
    ):
        return "future_balance"

    if has_month_horizon and has_goal_amount and any(
        phrase in text
        for phrase in [
            "reach",
            "get to",
            "grow to",
            "save each month",
            "need to save",
            "target balance",
            "end with",
        ]
    ):
        return "future_balance"

    if has_one_time_event and any(
        phrase in text
        for phrase in [
            "what if",
            "happen",
            "look like",
            "forecast",
            "project",
            "affect",
            "impact",
            "balance",
        ]
    ):
        return "future_balance"

    if any(
        phrase in text
        for phrase in [
            "should i review charts or transactions first",
            "charts or transactions first",
            "review charts or transactions",
            "what should i review first",
            "where should i start",
        ]
    ):
        return "review_path"

    if "compare" in text and "account" in text:
        return "account_comparison"

    if any(
        phrase in text
        for phrase in [
            "saved scenario",
            "saved scenarios",
            "saved plan",
            "saved plans",
            "saved simulator",
            "saved simulation",
        ]
    ):
        if any(
            phrase in text
            for phrase in [
                "compare",
                "best",
                "better",
                "strongest",
                "which one",
                "which plan",
                "safest",
                "lowest risk",
                "least risky",
                "most stable",
                "goal",
                "target",
                "cash flow",
                "monthly net",
            ]
        ):
            return "saved_scenario_compare"
        return "saved_scenario_list"

    if any(
        phrase in text
        for phrase in [
            "savings scenario",
            "saving scenario",
            "simulator plan",
            "scenario should i try",
            "which plan should i try",
            "best plan to try",
            "best savings plan",
            "best scenario to try",
        ]
    ):
        return "savings_scenario"

    if any(
        phrase in text
        for phrase in [
            "subscription",
            "subscriptions",
            "recurring charge",
            "recurring charges",
            "recurring expense",
            "recurring expenses",
            "monthly charges",
            "memberships",
        ]
    ):
        return "recurring_expenses"

    if any(
        phrase in text
        for phrase in [
            "compare accounts",
            "which account",
            "account is driving",
            "driving my spending by account",
            "highest spending account",
            "most expensive account",
        ]
    ):
        return "account_comparison"

    if any(
        phrase in text
        for phrase in [
            "top 3",
            "top three",
            "biggest 3",
            "largest 3",
            "top categories",
            "where is my money going",
            "where does my money go",
        ]
    ):
        return "top_categories_multi"

    if any(
        phrase in text
        for phrase in [
            "their transactions",
            "show transactions",
            "show me transactions",
            "category transactions",
            "transactions for category",
        ]
    ):
        return "category_transactions"

    if any(word in text for word in ["balance", "left over", "how much do i have"]):
        return "balance"

    if any(word in text for word in ["top expense", "top category", "biggest category", "most spent"]):
        return "top_category"

    if any(
        phrase in text
        for phrase in [
            "budget",
            "budgets",
            "on track",
            "over budget",
            "left in my budget",
            "remaining budget",
            "budget limit",
            "close to the limit",
            "budget forecast",
            "projected to go over",
            "projected budget",
        ]
    ):
        return "budget_status"

    if any(word in text for word in ["increase", "decrease", "trend", "last month", "this month", "overspend", "spending change"]):
        return "spending_change"

    if any(word in text for word in ["save", "saving", "advice", "reduce", "cut spending", "budget"]):
        return "saving_advice"

    if any(word in text for word in ["summary", "summarize", "overview", "my finances"]):
        return "summary"

    if any(word in text for word in ["driving this", "which category", "what caused", "reason for increase"]):
        return "driver"

    if any(word in text for word in ["alert", "warning", "problem", "risk"]):
        return "alerts"

    if any(word in text for word in ["recent", "latest transactions", "last transactions"]):
        return "recent"

    if any(word in text for word in ["youtube", "google", "resource", "article", "learn more", "guide"]):
        return "education"

    return "general"


def build_assistant_actions(
    snapshot: dict[str, Any],
    intent: str,
    account_id: int | None = None,
    driver_category: str | None = None,
    focus_category: str | None = None,
    focus_transaction_type: str = "expense",
    simulation_months: int | None = None,
    simulation_target_balance: float | None = None,
    simulation_income_adjustment: float | None = None,
    simulation_expense_adjustment: float | None = None,
    simulation_event_month_offset: int | None = None,
    simulation_event_amount: float | None = None,
    simulation_event_label: str | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    top_category = snapshot["top_category"]
    current_month = snapshot["current_month"]
    target_category = focus_category or driver_category or top_category
    target_transaction_type = focus_transaction_type if focus_category else "expense"
    target_label_suffix = "transactions" if target_transaction_type == "income" else "expenses"

    if intent == "balance":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
                "account_id": account_id,
            }
        )

    elif intent == "future_balance":
        actions.append(
            {
                "label": "Open simulator",
                "page": "simulator",
                "months_ahead": simulation_months,
                "account_id": account_id,
                "target_balance": simulation_target_balance,
                "income_adjustment": simulation_income_adjustment,
                "expense_adjustment": simulation_expense_adjustment,
                "event_month_offset": simulation_event_month_offset,
                "event_amount": simulation_event_amount,
                "event_label": simulation_event_label,
            }
        )
        actions.append(
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": snapshot.get("current_month") or get_default_budget_month(),
                "account_id": account_id,
            }
        )

    elif intent == "account_comparison":
        actions.append(
            {
                "label": "Open accounts",
                "page": "accounts",
            }
        )

    elif intent == "top_category":
        if target_category:
            actions.append(
                {
                    "label": f"Open {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )
            actions.append(
                {
                    "label": "View category ranking",
                    "page": "analytics",
                    "section": "categories",
                    "account_id": account_id,
                }
            )

    elif intent == "spending_change":
        actions.append(
            {
                "label": "Inspect overspending alerts",
                "page": "analytics",
                "section": "alerts",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "View category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

    elif intent == "saving_advice":
        actions.append(
            {
                "label": "Open spending insights",
                "page": "analytics",
                "section": "insights",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": snapshot.get("current_month"),
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} transactions",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )

    elif intent == "summary":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "View all transactions",
                "page": "transactions",
                "account_id": account_id,
            }
        )

    elif intent == "driver":
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Inspect {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

    elif intent == "alerts":
        actions.append(
            {
                "label": "Open overspending alerts",
                "page": "analytics",
                "section": "alerts",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )

    elif intent == "recent":
        if target_category:
            actions.append(
                {
                    "label": f"Open {target_category} transactions",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )
        else:
            actions.append(
                {
                    "label": "View all transactions",
                    "page": "transactions",
                    "account_id": account_id,
                }
            )

    elif intent == "general" and target_category:
        actions.append(
            {
                "label": f"Open {target_category} transactions",
                "page": "transactions",
                "category": target_category,
                "transaction_type": target_transaction_type,
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )

    return actions[:3]


def generate_mode_intro(mode: str) -> str:
    if mode == "strict":
        return "Strict view:"
    if mode == "coach":
        return "Coach view:"
    return ""


def generate_dynamic_followups(
    intent: str,
    mode: str,
    top_category: str | None,
    driver_category: str | None,
    focus_category: str | None = None,
) -> list[str]:
    if focus_category:
        return [
            f"Show me recent {focus_category} transactions",
            f"How has {focus_category} changed month to month?",
            f"How can I improve my {focus_category} spending?",
        ]

    if intent == "future_balance":
        return [
            "What if my monthly expenses go up by 200?",
            "What if I increase my income by 500 a month?",
            "What if I have a 1200 repair in 2 months?",
            "Should I build next month's budgets from this pace?",
        ]

    if intent == "account_comparison":
        return [
            "Which account should I review first?",
            "Show me transactions from the highest-spending account.",
            "Which account has the healthiest balance?",
        ]

    if intent == "budget_status":
        return [
            "Which budget is closest to the limit?",
            "Which budget is projected to go over?",
            "How can I get back on track?",
        ]

    if intent == "recurring_expenses":
        return [
            "Which recurring charge costs me the most each year?",
            "Which subscriptions should I review first?",
            "Did any recurring charge increase lately?",
            "What happens if I cancel my biggest subscription?",
            "Open my transactions",
        ]

    if intent == "savings_scenario":
        return [
            "Which savings scenario should I try first?",
            "Open the strongest simulator plan",
            "What happens if I cancel my biggest subscription?",
        ]

    if mode == "strict":
        if intent in {"spending_change", "driver", "alerts"}:
            return [
                "What should I cut first?",
                "Show me the transactions causing this.",
                f"Is {driver_category or top_category or 'this category'} the main problem?",
            ]
        return [
            "What is hurting my budget most?",
            "Where should I cut first?",
            "Show me the transactions behind this.",
        ]

    if mode == "coach":
        if intent in {"saving_advice", "summary"}:
            return [
                "What is one easy improvement I can make this week?",
                "Where can I save without feeling restricted?",
                "Show me the best place to start improving.",
            ]
        return [
            "What is one smart next step?",
            "Where can I improve gradually?",
            "Show me the best starting point.",
        ]

    if intent == "top_categories_multi":
        return [
            "Show me their transactions",
            "Which one is growing fastest?",
            "How can I reduce them?",
        ]
    if intent == "category_transactions":
        return [
            "Which category is driving my spending most?",
            "How can I reduce these expenses?",
            "Open those transactions",
        ]
    if intent == "spending_change":
        return [
            "What category caused the increase?",
            "Show me the recent transactions behind this.",
            "What should I review first?",
        ]
    if intent == "saving_advice":
        return [
            "Where should I start cutting back?",
            "Which category gives me the biggest savings opportunity?",
            "Show me the transactions I should review first.",
        ]
    return [
        "Show me my top 3 spending categories",
        "Show me their transactions",
        "Give me saving advice",
    ]


def build_driver_explanation(
    expense_change_percent: float | None,
    top_category: str | None,
    driver_category: str | None,
    recent_transactions: list[Any],
) -> list[str]:
    reasons: list[str] = []

    if expense_change_percent is not None:
        if expense_change_percent > 0:
            reasons.append(f"overall expenses increased by {expense_change_percent:.1f}%")
        elif expense_change_percent < 0:
            reasons.append(f"overall expenses decreased by {abs(expense_change_percent):.1f}%")

    if driver_category:
        reasons.append(f"{driver_category} appears to be the fastest-growing category")
    elif top_category:
        reasons.append(f"{top_category} is currently the biggest spending category")

    if recent_transactions:
        recent_labels = ", ".join(tx.description for tx in recent_transactions[:2])
        if recent_labels:
            reasons.append(f"recent transactions such as {recent_labels} may be contributing")

    return reasons


def parse_projection_months(question: str) -> int:
    match = re.search(r"(\d+)\s+month", question.lower())
    if not match:
        return 3

    return max(1, min(int(match.group(1)), 12))


def parse_target_balance(question: str) -> float | None:
    lowered = question.lower()
    patterns = [
        r"(?:reach|get to|grow to|balance of|balance at|target balance(?: of)?|end with)\s+\$?(\d+(?:,\d{3})*(?:\.\d+)?)",
        r"\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s+(?:balance|saved)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1).replace(",", ""))

    return None


def parse_one_time_event_amount(question: str) -> float | None:
    lowered = question.lower()
    expense_keywords = [
        "trip",
        "vacation",
        "repair",
        "car repair",
        "purchase",
        "buy",
        "bill",
        "payment",
        "expense",
        "cost",
        "tuition",
        "wedding",
        "medical",
    ]
    income_keywords = [
        "bonus",
        "refund",
        "tax refund",
        "windfall",
        "sale",
        "sell",
        "rebate",
        "gift",
        "payout",
    ]
    keyword_group = "|".join(
        sorted(
            [re.escape(keyword) for keyword in expense_keywords + income_keywords],
            key=len,
            reverse=True,
        )
    )
    patterns = [
        rf"\$?(\d+(?:,\d{{3}})*(?:\.\d+)?)(?:[^a-z0-9]{{0,24}})(?:{keyword_group})",
        rf"(?:{keyword_group})(?:[^0-9$]{{0,24}})\$?(\d+(?:,\d{{3}})*(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue

        trailing_context = lowered[match.end(): min(len(lowered), match.end() + 16)]
        if re.match(r"\s*months?\b", trailing_context):
            continue

        amount = float(match.group(1).replace(",", ""))
        context = lowered[max(0, match.start() - 32): min(len(lowered), match.end() + 32)]
        if any(keyword in context for keyword in income_keywords):
            return amount
        if any(keyword in context for keyword in expense_keywords):
            return -amount

    return None


def parse_one_time_event_offset(question: str) -> int | None:
    lowered = question.lower()
    if "next month" in lowered:
        return 1

    patterns = [
        r"in\s+(\d+)\s+month",
        r"(\d+)\s+months?\s+from\s+now",
        r"month\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return max(1, min(int(match.group(1)), 12))

    return None


def derive_one_time_event_label(question: str, event_amount: float | None) -> str | None:
    if event_amount is None:
        return None

    lowered = question.lower()
    label_map = [
        ("tax refund", "Tax refund"),
        ("car repair", "Car repair"),
        ("repair", "Repair"),
        ("trip", "Planned trip"),
        ("vacation", "Vacation"),
        ("bonus", "Bonus"),
        ("refund", "Refund"),
        ("purchase", "Planned purchase"),
        ("bill", "Bill"),
        ("payment", "Payment"),
        ("tuition", "Tuition"),
        ("wedding", "Wedding"),
        ("medical", "Medical expense"),
        ("gift", "Gift"),
        ("sale", "Sale"),
    ]

    for keyword, label in label_map:
        if keyword in lowered:
            return label

    return "One-time income" if event_amount > 0 else "One-time expense"


def parse_simulation_adjustments(question: str) -> tuple[float, float]:
    lower_question = question.lower()

    def extract_amount(keywords: list[str]) -> float:
        keyword_group = "|".join(re.escape(keyword) for keyword in keywords)
        match = re.search(
            rf"(?:{keyword_group})(?:[^0-9-]{{0,24}})(\d+(?:\.\d+)?)",
            lower_question,
        )
        if not match:
            return 0.0

        amount = float(match.group(1))
        context = lower_question[max(0, match.start() - 24): match.end()]
        negative_signals = ("down", "decrease", "less", "lower", "reduce", "cut")
        positive_signals = ("up", "increase", "more", "higher", "raise")

        if any(signal in context for signal in negative_signals) and not any(
            signal in context for signal in positive_signals
        ):
            return -amount

        return amount

    income_adjustment = extract_amount(["income", "salary", "earn", "earning", "pay"])
    expense_adjustment = extract_amount(["expense", "expenses", "spend", "spending", "costs"])
    return income_adjustment, expense_adjustment


def generate_assistant_response(
    db: Session,
    user_id: int,
    question: str,
    history: list[Any] | None = None,
    mode: str = "balanced",
    account_id: int | None = None,
    scope_label: str = "All accounts combined",
) -> dict[str, Any]:
    history = history or []
    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)
    snapshot["scope_label"] = scope_label
    category_trends = get_category_trends(db, user_id, account_id=account_id)
    overspending_alerts = get_overspending_alerts(db, user_id, account_id=account_id)
    recent_transactions = get_recent_transactions(
        db,
        user_id,
        account_id=account_id,
        limit=5,
    )

    q = (question or "").strip().lower()
    context_text = extract_recent_context(history)
    intent = classify_question(q, context_text)
    likely_saved_scenario_question = any(
        phrase in q
        for phrase in [
            "compare",
            "better",
            "best",
            "strongest",
            "plan",
            "scenario",
            "safest",
            "risk",
            "goal",
            "target",
            "cash flow",
            "monthly net",
        ]
    )
    saved_scenario_name_candidates = (
        [
            {
                "id": item.id,
                "name": item.name,
            }
            for item in list_saved_scenarios(
                db=db,
                owner_id=user_id,
                account_id=account_id,
            )
        ]
        if likely_saved_scenario_question
        else []
    )
    named_saved_scenarios_in_question = detect_named_saved_scenarios(
        question=question,
        context_text=context_text,
        saved_scenarios=saved_scenario_name_candidates,
    )
    if len(named_saved_scenarios_in_question) >= 2:
        intent = "saved_scenario_compare"

    current_month = snapshot["current_month"]
    budget_snapshot = get_budget_progress_snapshot(
        db,
        user_id,
        month=current_month or get_default_budget_month(),
        account_id=account_id,
    )
    budget_action_insights = build_budget_action_insights(budget_snapshot["items"])
    budget_categories = [item["category"] for item in budget_snapshot["items"]]
    focus_categories = get_distinct_categories(db, user_id, account_id=account_id)
    seen_focus_categories = {
        normalize_text_for_matching(item)
        for item in focus_categories
    }
    for category in budget_categories:
        normalized_category = normalize_text_for_matching(category)
        if normalized_category and normalized_category not in seen_focus_categories:
            focus_categories.append(category)
            seen_focus_categories.add(normalized_category)

    focus_category = detect_focus_category(
        question=question,
        context_text=context_text,
        categories=sorted(
            focus_categories,
            key=lambda item: (-len(normalize_text_for_matching(item)), item.lower()),
        ),
    )
    if focus_category and "transaction" in q:
        intent = "category_transactions"

    total_income = snapshot["total_income"]
    total_expenses = snapshot["total_expenses"]
    balance = snapshot["balance"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    top_category_share_percent = snapshot["top_category_share_percent"]
    expense_change_percent = snapshot["expense_change_percent"]

    primary_driver = None
    if category_trends.get("top_increases"):
        primary_driver = category_trends["top_increases"][0]["category"]

    focus_snapshot = (
        build_category_focus_snapshot(
            db,
            user_id,
            focus_category,
            snapshot,
            account_id=account_id,
        )
        if focus_category
        else None
    )
    focused_budget = next(
        (
            item
            for item in budget_snapshot["items"]
            if normalize_text_for_matching(item["category"]) == normalize_text_for_matching(focus_category or "")
        ),
        None,
    )
    saved_scenario_snapshots = (
        build_saved_scenario_projection_snapshots(
            db=db,
            user_id=user_id,
            account_id=account_id,
            scope_label=scope_label,
        )
        if intent in {"saved_scenario_list", "saved_scenario_compare"} or likely_saved_scenario_question
        else []
    )
    recurring_expenses = (
        get_recurring_expense_patterns(
            db=db,
            user_id=user_id,
            account_id=account_id,
            limit=5,
        )
        if intent in {"recurring_expenses", "saving_advice"}
        else []
    )
    simulation_recommendations = (
        build_future_simulation_recommendations(
            db=db,
            user_id=user_id,
            account_id=account_id,
            months=6,
            scope_label=scope_label,
        )
        if intent == "savings_scenario"
        else {"items": []}
    )
    if (
        intent not in {"saved_scenario_list", "saved_scenario_compare"}
        and saved_scenario_snapshots
        and is_saved_scenario_plan_comparison_question(question, context_text)
    ):
        intent = "saved_scenario_compare"

    if intent == "saved_scenario_list":
        if not saved_scenario_snapshots:
            return {
                "answer": (
                    f"You do not have any saved simulator scenarios in {scope_label} yet. "
                    "Save a few plans in the simulator first and I can help compare them."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    "Saved scenarios found: 0",
                ],
                "suggested_followups": [
                    "What will my balance look like in 3 months?",
                    "How much do I need to save each month to hit my target?",
                ],
                "suggested_actions": [
                    {
                        "label": "Open simulator",
                        "page": "simulator",
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        portfolio_summary = build_saved_scenario_portfolio_summary(saved_scenario_snapshots)
        supporting_points = [
            (
                f"Portfolio: {portfolio_summary['healthy_count']} healthy, "
                f"{portfolio_summary['attention_count']} need attention, "
                f"{portfolio_summary['goal_count']} goal-based, "
                f"{portfolio_summary['event_count']} event-driven"
            )
        ]
        if portfolio_summary["strongest"] is not None:
            supporting_points.append(
                f"Strongest finish: {build_saved_scenario_supporting_point(portfolio_summary['strongest'])}"
            )
        if (
            portfolio_summary["safest"] is not None
            and portfolio_summary["safest"]["id"] != portfolio_summary["strongest"]["id"]
        ):
            supporting_points.append(
                f"Safest cushion: {build_saved_scenario_supporting_point(portfolio_summary['safest'], comparison_focus='risk')}"
            )
        if portfolio_summary["goal_leader"] is not None:
            supporting_points.append(
                f"Goal leader: {build_saved_scenario_supporting_point(portfolio_summary['goal_leader'], comparison_focus='goal')}"
            )

        return {
            "answer": (
                f"You have {len(saved_scenario_snapshots)} saved simulator plan"
                f"{'' if len(saved_scenario_snapshots) == 1 else 's'} in {scope_label}. "
                f"{portfolio_summary['healthy_count']} look healthy right now and "
                f"{portfolio_summary['attention_count']} need attention. "
                f"{portfolio_summary['strongest']['name']} currently has the strongest projected finish."
            ),
            "supporting_points": supporting_points,
            "suggested_followups": [
                "Which saved scenario looks strongest?",
                "Which saved scenario is safest?",
                "Which saved scenario has the best monthly cash flow?",
                "Which saved scenario gets me closest to my goal?",
                "What will my balance look like in 3 months?",
            ],
            "suggested_actions": [
                *(
                    [
                        {
                            "label": f"Compare {portfolio_summary['strongest']['name']} vs {portfolio_summary['safest']['name']}",
                            "page": "simulator",
                            "account_id": account_id,
                            "saved_scenario_id": portfolio_summary["strongest"]["id"],
                            "compare_saved_scenario_id": portfolio_summary["safest"]["id"],
                        }
                    ]
                    if portfolio_summary["strongest"] is not None
                    and portfolio_summary["safest"] is not None
                    and portfolio_summary["strongest"]["id"] != portfolio_summary["safest"]["id"]
                    else []
                ),
                *(
                    [
                        {
                            "label": f"Open {portfolio_summary['strongest']['name']}",
                            "page": "simulator",
                            "account_id": account_id,
                            "saved_scenario_id": portfolio_summary["strongest"]["id"],
                        }
                    ]
                    if portfolio_summary["strongest"] is not None
                    else []
                ),
                {
                    "label": "Open simulator",
                    "page": "simulator",
                    "account_id": account_id,
                },
            ],
            "scope_label": scope_label,
        }

    if intent == "saved_scenario_compare":
        if len(saved_scenario_snapshots) < 2:
            return {
                "answer": (
                    f"I need at least two saved scenarios in {scope_label} before I can compare them."
                ),
                "supporting_points": [
                    f"Saved scenarios found: {len(saved_scenario_snapshots)}",
                ],
                "suggested_followups": [
                    "What will my balance look like in 3 months?",
                    "How much do I need to save each month to hit my target?",
                ],
                "suggested_actions": [
                    {
                        "label": "Open simulator",
                        "page": "simulator",
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        named_scenarios = detect_named_saved_scenarios(
            question=question,
            context_text=context_text,
            saved_scenarios=saved_scenario_snapshots,
        )
        comparison_set = named_scenarios[:2] if len(named_scenarios) >= 2 else saved_scenario_snapshots[:2]
        comparison_focus = detect_saved_scenario_comparison_focus(question, context_text)
        comparison_set = sorted(
            comparison_set,
            key=lambda item: build_saved_scenario_comparison_key(item, comparison_focus),
            reverse=True,
        )

        best_scenario = comparison_set[0]
        runner_up = comparison_set[1]
        projected_gap = (
            float(best_scenario["projected_end_balance"])
            - float(runner_up["projected_end_balance"])
        )
        monthly_net_gap = (
            float(best_scenario["monthly_net_change"])
            - float(runner_up["monthly_net_change"])
        )
        safer_floor_gap = (
            float(best_scenario.get("lowest_balance") or 0.0)
            - float(runner_up.get("lowest_balance") or 0.0)
        )
        goal_balance = best_scenario.get("goal_balance")
        goal_gap_amount = best_scenario.get("goal_gap_amount")

        if comparison_focus == "risk":
            if mode == "strict":
                answer = (
                    f"{best_scenario['name']} is the safest saved plan right now. "
                    f"It carries {best_scenario['risk_level']} risk and keeps the balance floor "
                    f"{format_currency(safer_floor_gap)} higher than {runner_up['name']}."
                )
            elif mode == "coach":
                answer = (
                    f"{best_scenario['name']} looks like the safest path to lean on right now. "
                    f"It gives you the steadiest balance cushion through the scenario window."
                )
            else:
                answer = (
                    f"{best_scenario['name']} currently looks like the safest saved scenario. "
                    f"It keeps a stronger balance floor than {runner_up['name']} while staying "
                    f"at {best_scenario['risk_level']} risk."
                )
        elif comparison_focus == "monthly_net":
            if mode == "strict":
                answer = (
                    f"{best_scenario['name']} has the strongest monthly cash flow. "
                    f"It runs {format_currency(monthly_net_gap)} per month ahead of {runner_up['name']}."
                )
            elif mode == "coach":
                answer = (
                    f"{best_scenario['name']} gives you the cleanest month-to-month breathing room. "
                    f"It improves your ongoing cash flow the most."
                )
            else:
                answer = (
                    f"{best_scenario['name']} currently has the strongest monthly net change, "
                    f"running {format_currency(monthly_net_gap)} per month ahead of {runner_up['name']}."
                )
        elif comparison_focus == "goal" and goal_balance is not None:
            if goal_gap_amount is not None and goal_gap_amount <= 0:
                answer = (
                    f"{best_scenario['name']} is your strongest goal-focused saved plan right now. "
                    f"It already reaches its target balance of {format_currency(goal_balance)}."
                )
            else:
                answer = (
                    f"{best_scenario['name']} is currently the closest saved plan to its target balance. "
                    f"It still needs about {format_currency(float(goal_gap_amount or 0.0))} to get there."
                )
        elif comparison_focus == "goal":
            answer = (
                f"None of these saved scenarios has a target balance attached yet, "
                f"so {best_scenario['name']} is leading on ending balance instead."
            )
        elif mode == "strict":
            answer = (
                f"{best_scenario['name']} is the strongest saved plan right now. "
                f"It finishes {format_currency(projected_gap)} ahead of {runner_up['name']}."
            )
        elif mode == "coach":
            answer = (
                f"{best_scenario['name']} looks like your strongest saved path so far. "
                f"It gives you the most room by the end of the scenario window."
            )
        else:
            answer = (
                f"{best_scenario['name']} currently projects the highest ending balance, "
                f"finishing {format_currency(projected_gap)} ahead of {runner_up['name']}."
            )

        supporting_points = []
        for item in comparison_set:
            supporting_points.append(
                build_saved_scenario_supporting_point(item, comparison_focus=comparison_focus)
            )

        if len(named_scenarios) < 2:
            supporting_points.append(
                "Tip: mention two saved plan names if you want a direct head-to-head comparison."
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:4],
            "suggested_followups": [
                f"Open {best_scenario['name']}",
                "Which saved scenario is safest?",
                "Which saved scenario has the best monthly cash flow?",
                "What will my balance look like in 3 months?",
            ],
            "suggested_actions": [
                {
                    "label": f"Compare {best_scenario['name']} vs {runner_up['name']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "saved_scenario_id": best_scenario["id"],
                    "compare_saved_scenario_id": runner_up["id"],
                },
                {
                    "label": f"Open {best_scenario['name']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "saved_scenario_id": best_scenario["id"],
                },
                {
                    "label": "Open simulator",
                    "page": "simulator",
                    "account_id": account_id,
                },
            ],
            "scope_label": scope_label,
        }

    if intent == "savings_scenario":
        recommendation_items = simulation_recommendations.get("items", [])
        if not recommendation_items:
            return {
                "answer": (
                    f"I do not have a strong simulator recommendation for {scope_label} yet. "
                    "A little more recurring, budget, or monthly history would help me rank the best plan."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    "Recommended plans found: 0",
                ],
                "suggested_followups": [
                    "What subscriptions or recurring charges do I have?",
                    "Give me saving advice",
                ],
                "suggested_actions": [
                    {
                        "label": "Open simulator",
                        "page": "simulator",
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        lead_recommendation = recommendation_items[0]
        runner_up = recommendation_items[1] if len(recommendation_items) > 1 else None

        if mode == "strict":
            answer = (
                f"{lead_recommendation['label']} is the strongest simulator plan to try first in {scope_label}. "
                f"It improves the projection by {format_currency(lead_recommendation['scenario_impact_amount'])}."
            )
        elif mode == "coach":
            answer = (
                f"{lead_recommendation['label']} looks like the most practical scenario to try first in {scope_label}. "
                f"It gives you the clearest upside without overcomplicating the plan."
            )
        else:
            answer = (
                f"{lead_recommendation['label']} is the strongest simulator recommendation I see for {scope_label}. "
                f"It projects about {format_currency(lead_recommendation['projected_end_balance'])} at the end of the window."
            )

        supporting_points = [
            (
                f"{item['label']}: {item['description']} "
                f"Projected end {format_currency(item['projected_end_balance'])}, "
                f"impact {format_currency(item['scenario_impact_amount'])}, "
                f"risk {item['risk_level']}."
            )
            for item in recommendation_items[:3]
        ]

        suggested_actions = [
            {
                "label": f"Apply {lead_recommendation['label']}",
                "page": "simulator",
                "account_id": account_id,
                "scenario_name": lead_recommendation["label"],
                "months_ahead": lead_recommendation["months"],
                "income_adjustment": lead_recommendation["income_adjustment"],
                "expense_adjustment": lead_recommendation["expense_adjustment"],
                "target_balance": lead_recommendation.get("target_balance"),
                "event_month_offset": lead_recommendation.get("event_month_offset"),
                "event_amount": lead_recommendation.get("event_amount"),
                "event_label": lead_recommendation.get("event_label"),
            }
        ]
        if runner_up is not None:
            suggested_actions.append(
                {
                    "label": f"Try {runner_up['label']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "scenario_name": runner_up["label"],
                    "months_ahead": runner_up["months"],
                    "income_adjustment": runner_up["income_adjustment"],
                    "expense_adjustment": runner_up["expense_adjustment"],
                    "target_balance": runner_up.get("target_balance"),
                    "event_month_offset": runner_up.get("event_month_offset"),
                    "event_amount": runner_up.get("event_amount"),
                    "event_label": runner_up.get("event_label"),
                }
            )

        suggested_actions.append(
            {
                "label": "Open simulator",
                "page": "simulator",
                "account_id": account_id,
            }
        )

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    if intent == "recurring_expenses":
        if not recurring_expenses:
            return {
                "answer": (
                    f"I do not see any strong recurring expense patterns in {scope_label} yet. "
                    "If you track a couple more months of subscription or bill activity, I can flag them more reliably."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    "Recurring patterns found: 0",
                ],
                "suggested_followups": [
                    "Show my recent transactions",
                    "What category is driving my spending most?",
                ],
                "suggested_actions": [
                    {
                        "label": "Open transactions",
                        "page": "transactions",
                    }
                ],
                "scope_label": scope_label,
            }

        recurring_total = round(sum(item["average_amount"] for item in recurring_expenses), 2)
        annualized_total = round(sum(item["annualized_amount"] for item in recurring_expenses), 2)
        savings_opportunities = build_recurring_savings_opportunities(recurring_expenses)
        review_candidate = savings_opportunities[0]
        increased_items = [
            item
            for item in recurring_expenses
            if (item.get("latest_change_percent") or 0.0) >= 8
        ]
        combined_review_cut = round(
            sum(float(item.get("average_amount") or 0.0) for item in savings_opportunities[:2]),
            2,
        )
        review_words = ("review", "cancel", "cut", "first", "trim")
        wants_review = any(word in q for word in review_words)
        wants_savings_model = any(
            phrase in q
            for phrase in [
                "cancel",
                "cut",
                "drop",
                "remove",
                "save if",
                "what happens if",
                "what if i cancel",
            ]
        )
        wants_increase_focus = any(
            phrase in q
            for phrase in [
                "increase",
                "increased",
                "went up",
                "higher",
                "price change",
                "price increase",
            ]
        )

        if wants_increase_focus and increased_items:
            leading_item = increased_items[0]
            answer = (
                f"{leading_item['description']} is the clearest recurring charge increase in {scope_label}. "
                f"Its latest charge landed about {leading_item['latest_change_percent']:.0f}% above its usual amount."
            )
        elif wants_savings_model:
            answer = (
                f"If you cancel {review_candidate['description']}, you would free up about "
                f"{format_currency(review_candidate['average_amount'])} per month or "
                f"{format_currency(review_candidate['annualized_amount'])} per year in {scope_label}. "
                "I can open that as a simulator cut so you can see the balance impact."
            )
        elif wants_review:
            answer = (
                f"{review_candidate['description']} is the first recurring charge I would review in {scope_label}. "
                f"{review_candidate['review_reason']}"
            )
        elif mode == "strict":
            answer = (
                f"I found {len(recurring_expenses)} likely recurring expense pattern"
                f"{'' if len(recurring_expenses) == 1 else 's'} in {scope_label}, worth about "
                f"{format_currency(recurring_total)} per month. {review_candidate['description']} is the first one to review."
            )
        elif mode == "coach":
            answer = (
                f"You have {len(recurring_expenses)} likely recurring charge"
                f"{'' if len(recurring_expenses) == 1 else 's'} in {scope_label}, adding up to about "
                f"{format_currency(recurring_total)} a month. {review_candidate['description']} looks like the first one to review."
            )
        else:
            answer = (
                f"I found {len(recurring_expenses)} likely recurring expense pattern"
                f"{'' if len(recurring_expenses) == 1 else 's'} in {scope_label}. "
                f"Together they add up to about {format_currency(recurring_total)} a month "
                f"or {format_currency(annualized_total)} a year."
            )

        supporting_points = [
            (
                f"{item['description']}: {item['cadence']}, avg {format_currency(item['average_amount'])}, "
                f"latest {format_currency(item['latest_amount'])} on {item['latest_date'].isoformat()}, "
                f"about {format_currency(item['annualized_amount'])}/year. "
                f"{item['review_reason']}"
                f"{' Next expected around ' + item['next_expected_date'].isoformat() + '.' if item.get('next_expected_date') else ''}"
            )
            for item in recurring_expenses
        ]

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": f"Review {review_candidate['description']}",
                    "page": "transactions",
                    "section": "recurring",
                    "description": review_candidate["description"],
                    "category": review_candidate["category"],
                    "transaction_type": "expense",
                    "account_id": account_id,
                },
                {
                    "label": f"Model cancelling {review_candidate['description']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "scenario_name": f"Cancel {review_candidate['description']}",
                    "expense_adjustment": -float(review_candidate["average_amount"]),
                },
                *(
                    [
                        {
                            "label": "Model review-first recurring cuts",
                            "page": "simulator",
                            "account_id": account_id,
                            "scenario_name": "Review-first recurring cuts",
                            "expense_adjustment": -combined_review_cut,
                        }
                    ]
                    if combined_review_cut > float(review_candidate["average_amount"])
                    else []
                ),
                {
                    "label": "Open all recurring charges",
                    "page": "transactions",
                    "section": "recurring",
                    "transaction_type": "expense",
                    "account_id": account_id,
                }
            ],
            "scope_label": scope_label,
        }

    if intent == "account_comparison":
        if account_id is not None:
            return {
                "answer": (
                    f"You're currently focused on {scope_label}, so I can't compare accounts inside this scoped view. "
                    "Switch to all accounts and ask again if you want a cross-account comparison."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    f"Balance in this scope: {format_currency(balance)}",
                ],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": "Open accounts",
                        "page": "accounts",
                    }
                ],
                "scope_label": scope_label,
            }

        account_comparison = get_account_comparison_snapshot(db, user_id)
        if len(account_comparison) < 2:
            return {
                "answer": "I need at least two active accounts before I can compare which one is driving your spending.",
                "supporting_points": [
                    f"Active accounts found: {len(account_comparison)}",
                ],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": "Open accounts",
                        "page": "accounts",
                    }
                ],
                "scope_label": scope_label,
            }

        leading_account = account_comparison[0]
        runner_up = account_comparison[1]
        expense_gap = leading_account["total_expenses"] - runner_up["total_expenses"]

        if mode == "strict":
            answer = (
                f"{leading_account['name']} is driving the most spending at {format_currency(leading_account['total_expenses'])}. "
                f"That is {format_currency(expense_gap)} more than {runner_up['name']}, so start there first."
            )
        elif mode == "coach":
            answer = (
                f"{leading_account['name']} is the main spending driver right now at {format_currency(leading_account['total_expenses'])}. "
                f"That gives us a clear account to review first."
            )
        else:
            answer = (
                f"{leading_account['name']} currently has the highest expenses at {format_currency(leading_account['total_expenses'])}, "
                f"followed by {runner_up['name']} at {format_currency(runner_up['total_expenses'])}."
            )

        supporting_points = []
        for item in account_comparison[:3]:
            point = (
                f"{item['name']} ({item['type']}): expenses {format_currency(item['total_expenses'])}, "
                f"income {format_currency(item['total_income'])}, balance {format_currency(item['balance'])}"
            )
            if item["top_category"]:
                point += (
                    f", top category {item['top_category']} "
                    f"at {format_currency(item['top_category_amount'])}"
                )
            supporting_points.append(point)

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "Open accounts",
                    "page": "accounts",
                },
                {
                    "label": f"Review {leading_account['name']} transactions",
                    "page": "transactions",
                    "account_id": leading_account["account_id"],
                },
            ],
            "scope_label": scope_label,
        }

    if intent == "budget_status":
        budget_month = budget_snapshot["month"]

        if budget_snapshot["budget_count"] == 0:
            return {
                "answer": (
                    f"You do not have any budgets set for {budget_month} in {scope_label} yet. "
                    "Create a few category targets first so I can tell you what is on track or under pressure."
                ),
                "supporting_points": [
                    f"Current budget month: {budget_month}",
                    f"Current scope: {scope_label}",
                    f"Recorded expenses in this scope: {format_currency(total_expenses)}",
                ],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": "Open budgets",
                        "page": "budgets",
                        "month": budget_month,
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        if focused_budget:
            focused_budget_label = format_category_label(focus_category or focused_budget["category"])
            remaining_text = (
                f"{format_currency(focused_budget['remaining_amount'])} remaining"
                if focused_budget["remaining_amount"] >= 0
                else f"{format_currency(abs(focused_budget['remaining_amount']))} over"
            )
            projected_finish_text = (
                f"Projected month-end: {format_currency(focused_budget['projected_spent_amount'])} spent, "
                f"{format_currency(focused_budget['projected_remaining_amount'])} remaining"
                if focused_budget["projected_remaining_amount"] >= 0
                else f"Projected month-end: {format_currency(focused_budget['projected_spent_amount'])} spent, "
                f"{format_currency(abs(focused_budget['projected_remaining_amount']))} over"
            )

            if focused_budget["status"] == "over_budget":
                if mode == "strict":
                    answer = (
                        f"{focused_budget_label} is already over budget for {budget_month}. "
                        f"You have used {focused_budget['usage_percent']:.1f}% of the limit."
                    )
                elif mode == "coach":
                    answer = (
                        f"{focused_budget_label} is over budget for {budget_month}, "
                        "so this is the clearest place to tighten up next."
                    )
                else:
                    answer = (
                        f"{focused_budget_label} is over budget for {budget_month}. "
                        f"You have used {focused_budget['usage_percent']:.1f}% of the target."
                    )
            elif focused_budget["status"] == "at_risk":
                if mode == "strict":
                    answer = (
                        f"{focused_budget_label} is getting close to the limit for {budget_month}. "
                        f"You have already used {focused_budget['usage_percent']:.1f}% of the budget."
                    )
                elif mode == "coach":
                    answer = (
                        f"{focused_budget_label} is still on the board for {budget_month}, "
                        "but it is close enough to the limit that it deserves attention now."
                    )
                else:
                    answer = (
                        f"{focused_budget_label} is at risk for {budget_month}. "
                        f"You have used {focused_budget['usage_percent']:.1f}% of the budget."
                    )
            else:
                answer = (
                    f"{focused_budget_label} is on track for {budget_month}. "
                    f"You have used {focused_budget['usage_percent']:.1f}% of the budget so far."
                )

            if (
                focused_budget["projected_status"] == "over_budget"
                and focused_budget["status"] != "over_budget"
            ):
                answer += (
                    f" At the current pace, it is projected to finish "
                    f"{format_currency(abs(focused_budget['projected_remaining_amount']))} over budget."
                )
            elif (
                focused_budget["projected_status"] == "at_risk"
                and focused_budget["status"] == "on_track"
            ):
                answer += (
                    f" At the current pace, it is projected to use "
                    f"{focused_budget['projected_usage_percent']:.1f}% of the budget by month end."
                )

            supporting_points = [
                f"Budget: {format_currency(focused_budget['amount'])}",
                f"Spent so far: {format_currency(focused_budget['spent_amount'])}",
                remaining_text,
                projected_finish_text,
            ]

            if focus_snapshot and focus_snapshot["recent_transactions"]:
                recent_text = ", ".join(
                    f"{tx.description} ({format_currency(tx.amount)})"
                    for tx in focus_snapshot["recent_transactions"][:3]
                )
                supporting_points.append(f"Recent {focused_budget_label} transactions: {recent_text}")
            else:
                supporting_points.append(f"Usage: {focused_budget['usage_percent']:.1f}%")

            return {
                "answer": answer,
                "supporting_points": supporting_points[:5],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": f"Open {focused_budget_label} budget",
                        "page": "budgets",
                        "month": budget_month,
                        "category": focused_budget["category"],
                        "account_id": account_id,
                    },
                    {
                        "label": f"Review {focused_budget_label} transactions",
                        "page": "transactions",
                        "category": focused_budget["category"],
                        "transaction_type": "expense",
                        "month": budget_month,
                        "account_id": account_id,
                    },
                ],
                "scope_label": scope_label,
            }

        use_projected_issue_view = (
            budget_snapshot["over_budget_count"] == 0
            and budget_snapshot["at_risk_count"] == 0
            and (
                budget_snapshot["projected_over_budget_count"] > 0
                or budget_snapshot["projected_at_risk_count"] > 0
            )
        )
        issue_items = (
            budget_snapshot["projected_issue_items"]
            if use_projected_issue_view
            else budget_snapshot["issue_items"]
        )
        lead_budget = issue_items[0] if issue_items else None

        if budget_snapshot["over_budget_count"] > 0:
            answer = (
                f"You are tracking {budget_snapshot['budget_count']} budgets for {budget_month}, "
                f"and {budget_snapshot['over_budget_count']} of them are already over budget."
            )
        elif budget_snapshot["projected_over_budget_count"] > 0:
            answer = (
                f"Your budgets for {budget_month} are not over budget yet, but "
                f"{budget_snapshot['projected_over_budget_count']} category budgets are projected "
                "to finish over budget at the current pace."
            )
        elif budget_snapshot["at_risk_count"] > 0:
            answer = (
                f"Your budgets for {budget_month} are mostly intact, but {budget_snapshot['at_risk_count']} "
                "category budgets are getting close to the limit."
            )
        elif budget_snapshot["projected_at_risk_count"] > 0:
            answer = (
                f"Your budgets for {budget_month} are still on track today, but "
                f"{budget_snapshot['projected_at_risk_count']} category budgets are projected to get tight "
                "if spending keeps this pace."
            )
        else:
            answer = (
                f"Your budgets for {budget_month} are on track right now. "
                f"You have {format_currency(budget_snapshot['total_remaining'])} of planned room left."
            )

        supporting_points = [
            f"Total budgeted: {format_currency(budget_snapshot['total_budgeted'])}",
            f"Total spent against budgets: {format_currency(budget_snapshot['total_spent'])}",
            f"Remaining budget room: {format_currency(budget_snapshot['total_remaining'])}",
            (
                f"Projected month-end room: {format_currency(budget_snapshot['projected_total_remaining'])}"
                if budget_snapshot["projected_total_remaining"] >= 0
                else f"Projected month-end overage: {format_currency(abs(budget_snapshot['projected_total_remaining']))}"
            ),
        ]

        for item in issue_items:
            if use_projected_issue_view:
                status_label = item["projected_status"].replace("_", " ")
                supporting_points.append(
                    f"{format_category_label(item['category'])}: projected {format_currency(item['projected_spent_amount'])} spent vs {format_currency(item['amount'])} budget ({item['projected_usage_percent']:.1f}% used, {status_label})"
                )
            else:
                status_label = item["status"].replace("_", " ")
                supporting_points.append(
                    f"{format_category_label(item['category'])}: {format_currency(item['spent_amount'])} spent vs {format_currency(item['amount'])} budget ({item['usage_percent']:.1f}% used, {status_label})"
                )

        suggested_actions = [
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": budget_month,
                "account_id": account_id,
            }
        ]

        if lead_budget:
            suggested_actions.append(
                {
                    "label": f"Review {format_category_label(lead_budget['category'])} transactions",
                    "page": "transactions",
                    "category": lead_budget["category"],
                    "transaction_type": "expense",
                    "month": budget_month,
                    "account_id": account_id,
                }
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    actionable_budget_insights = [
        item for item in budget_action_insights if item["severity"] in {"action", "watch"}
    ]
    if intent == "saving_advice" and actionable_budget_insights:
        lead_budget_insight = actionable_budget_insights[0]
        lead_budget_label = format_category_label(lead_budget_insight["category"])

        if mode == "strict":
            answer = (
                f"{lead_budget_insight['title']}. {lead_budget_insight['detail']} "
                "That is the first place to tighten up."
            )
        elif mode == "coach":
            answer = (
                f"{lead_budget_insight['title']}. {lead_budget_insight['detail']} "
                "A small change there would have the clearest payoff."
            )
        else:
            answer = f"{lead_budget_insight['title']}. {lead_budget_insight['detail']}"

        supporting_points = [
            f"{item['title']}: {item['detail']}"
            for item in actionable_budget_insights[:3]
        ]
        supporting_points.append(f"Current scope: {scope_label}")

        suggested_actions = [
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": budget_snapshot["month"],
                "account_id": account_id,
                "amount": lead_budget_insight.get("recommended_amount"),
            }
        ]
        if lead_budget_insight["category"]:
            suggested_actions.append(
                {
                    "label": f"Review {lead_budget_label} transactions",
                    "page": "transactions",
                    "category": lead_budget_insight["category"],
                    "transaction_type": "expense",
                    "month": budget_snapshot["month"],
                    "account_id": account_id,
                }
            )
            suggested_actions[0]["category"] = lead_budget_insight["category"]

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    recurring_savings_opportunities = build_recurring_savings_opportunities(recurring_expenses)
    if intent == "saving_advice" and recurring_savings_opportunities:
        lead_recurring = recurring_savings_opportunities[0]
        combined_recurring_cut = round(
            sum(float(item.get("average_amount") or 0.0) for item in recurring_savings_opportunities[:2]),
            2,
        )

        if mode == "strict":
            answer = (
                f"{lead_recurring['description']} is the cleanest recurring cost to pressure-test first. "
                f"Cutting it would free about {format_currency(lead_recurring['average_amount'])} per month."
            )
        elif mode == "coach":
            answer = (
                f"{lead_recurring['description']} looks like the easiest recurring place to create breathing room. "
                f"It is worth about {format_currency(lead_recurring['average_amount'])} per month."
            )
        else:
            answer = (
                f"{lead_recurring['description']} is the strongest recurring savings lever I see in {scope_label}. "
                f"It is worth about {format_currency(lead_recurring['average_amount'])} per month "
                f"or {format_currency(lead_recurring['annualized_amount'])} per year."
            )

        supporting_points = [
            (
                f"{item['description']}: {format_currency(item['average_amount'])}/month, "
                f"{format_currency(item['annualized_amount'])}/year. {item['review_reason']}"
            )
            for item in recurring_savings_opportunities[:3]
        ]
        supporting_points.append(f"Current scope: {scope_label}")

        suggested_actions = [
            {
                "label": f"Review {lead_recurring['description']}",
                "page": "transactions",
                "section": "recurring",
                "description": lead_recurring["description"],
                "category": lead_recurring["category"],
                "transaction_type": "expense",
                "account_id": account_id,
            },
            {
                "label": f"Model cancelling {lead_recurring['description']}",
                "page": "simulator",
                "account_id": account_id,
                "scenario_name": f"Cancel {lead_recurring['description']}",
                "expense_adjustment": -float(lead_recurring["average_amount"]),
            },
        ]
        if combined_recurring_cut > float(lead_recurring["average_amount"]):
            suggested_actions.append(
                {
                    "label": "Model top recurring cuts",
                    "page": "simulator",
                    "account_id": account_id,
                    "scenario_name": "Top recurring cuts",
                    "expense_adjustment": -combined_recurring_cut,
                }
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": [
                "Which subscriptions should I review first?",
                "What happens if I cancel my biggest subscription?",
                "Open my transactions",
            ],
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    llm_result = generate_llm_assistant_response(
        question=question,
        conversation_context=context_text,
        snapshot=snapshot,
        category_trends=category_trends,
        overspending_alerts=overspending_alerts,
        recent_transactions=recent_transactions,
        focus_category_context=focus_snapshot,
        mode=mode,
    )

    if llm_result:
        suggested_actions = []

        action_type = llm_result.get("action_type", "none")
        action_label = llm_result.get("action_label")
        action_target = llm_result.get("action_target")

        if action_type == "transactions":
            suggested_actions.append(
                {
                    "label": action_label or "Review transactions",
                    "page": "transactions",
                    "category": (
                        action_target
                        if action_target and action_target.lower() != "none"
                        else focus_category or primary_driver or top_category
                    ),
                    "transaction_type": (
                        focus_snapshot["transaction_type"]
                        if focus_snapshot
                        else "expense"
                    ),
                    "month": current_month,
                    "account_id": account_id,
                }
            )

        elif action_type == "dashboard":
            suggested_actions.append(
                {
                    "label": action_label or "Open dashboard",
                    "page": "dashboard",
                    "account_id": account_id,
                }
            )

        elif action_type == "analytics":
            target_section = "insights"
            if action_target:
                lower_target = action_target.lower()
                if "alert" in lower_target:
                    target_section = "alerts"
                elif "trend" in lower_target:
                    target_section = "trends"
                elif "month" in lower_target or "summary" in lower_target:
                    target_section = "monthly"
                elif "categor" in lower_target:
                    target_section = "categories"

            suggested_actions.append(
                {
                    "label": action_label or "Open analytics",
                    "page": "analytics",
                    "section": target_section,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

        elif action_type == "external_resource":
            suggested_actions.append(
                {
                    "label": action_label or "Explore learning resources",
                    "page": "external_resource",
                    "section": action_target or "budgeting basics",
                    "account_id": account_id,
                }
            )

        followups = llm_result["suggested_followups"] or generate_dynamic_followups(
            intent=intent,
            mode=mode,
            top_category=top_category,
            driver_category=primary_driver,
            focus_category=focus_category,
        )

        return {
            "answer": llm_result["answer"],
            "supporting_points": llm_result["supporting_points"],
            "suggested_followups": followups,
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    if total_income == 0 and total_expenses == 0:
        answer = "I do not have enough financial activity yet to give a meaningful answer."
        intro = generate_mode_intro(mode)
        final_answer = f"{intro} {answer}".strip() if intro else answer

        return {
            "answer": final_answer,
            "supporting_points": [
                "No recorded income found yet.",
                "No recorded expenses found yet.",
            ],
            "suggested_followups": generate_dynamic_followups(
                intent="general",
                mode=mode,
                top_category=None,
                driver_category=None,
                focus_category=focus_category,
            ),
            "suggested_actions": [],
            "scope_label": scope_label,
        }

    if not q:
        answer = "Ask me about your balance, top categories, transactions, spending trends, saving ideas, alerts, and financial summaries."
        intro = generate_mode_intro(mode)
        final_answer = f"{intro} {answer}".strip() if intro else answer

        return {
            "answer": final_answer,
            "supporting_points": [],
            "suggested_followups": generate_dynamic_followups(
                intent="general",
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [],
            "scope_label": scope_label,
        }

    if intent == "future_balance":
        projection_months = parse_projection_months(question)
        target_balance = parse_target_balance(question)
        income_adjustment, expense_adjustment = parse_simulation_adjustments(question)
        one_time_event_amount = parse_one_time_event_amount(question)
        one_time_event_offset = parse_one_time_event_offset(question)
        one_time_event_label = derive_one_time_event_label(question, one_time_event_amount)
        simulation = build_future_balance_simulation(
            db,
            user_id,
            account_id=account_id,
            months=projection_months,
            income_adjustment=income_adjustment,
            expense_adjustment=expense_adjustment,
            target_balance=target_balance,
            event_month_offset=one_time_event_offset,
            event_amount=one_time_event_amount or 0.0,
            event_label=one_time_event_label,
            scope_label=scope_label,
        )

        if target_balance is not None and simulation["goal_note"]:
            if mode == "strict":
                answer = (
                    f"At this pace you will miss {format_currency(target_balance)}. "
                    f"{simulation['goal_note']}"
                )
            elif mode == "coach":
                answer = (
                    f"Your current pace points to {format_currency(simulation['projected_end_balance'])} "
                    f"in {projection_months} month(s). {simulation['goal_note']}"
                )
            else:
                answer = (
                    f"Your current pace projects {format_currency(simulation['projected_end_balance'])} "
                    f"in {projection_months} month(s). {simulation['goal_note']}"
                )
        elif mode == "strict":
            answer = (
                f"If nothing changes from this pace, your balance is heading toward "
                f"{format_currency(simulation['projected_end_balance'])} in {projection_months} month(s)."
            )
        elif mode == "coach":
            answer = (
                f"If your current pace holds, your balance could land around "
                f"{format_currency(simulation['projected_end_balance'])} in {projection_months} month(s)."
            )
        else:
            answer = (
                f"At the current pace, your balance is projected to be "
                f"{format_currency(simulation['projected_end_balance'])} in {projection_months} month(s)."
            )

        supporting_points = [
            f"Starting balance: {format_currency(simulation['starting_balance'])}",
            f"Monthly income used: {format_currency(simulation['adjusted_monthly_income'])}",
            f"Monthly expenses used: {format_currency(simulation['adjusted_monthly_expenses'])}",
            f"Projected monthly net change: {format_currency(simulation['monthly_net_change'])}",
        ]
        if simulation["one_time_event_amount"] is not None and simulation["one_time_event_month"]:
            supporting_points.append(
                f"One-time event: {simulation['one_time_event_label']} in {simulation['one_time_event_month']} for {format_signed_currency(simulation['one_time_event_amount'])}"
            )
        if simulation["goal_note"]:
            supporting_points.append(simulation["goal_note"])
        else:
            supporting_points.append(simulation["narrative"])

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent=intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                simulation_months=projection_months,
                simulation_target_balance=target_balance,
                simulation_income_adjustment=income_adjustment,
                simulation_expense_adjustment=expense_adjustment,
                simulation_event_month_offset=one_time_event_offset,
                simulation_event_amount=one_time_event_amount,
                simulation_event_label=one_time_event_label,
            ),
            "scope_label": scope_label,
        }

    if focus_snapshot and intent in {
        "category_transactions",
        "recent",
        "saving_advice",
        "spending_change",
        "driver",
        "alerts",
        "top_category",
        "general",
        "summary",
    }:
        return {
            "answer": build_category_focus_answer(
                intent=intent,
                mode=mode,
                focus_snapshot=focus_snapshot,
                top_category=top_category,
            ),
            "supporting_points": build_category_focus_supporting_points(focus_snapshot),
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent="recent" if intent == "category_transactions" else intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                focus_transaction_type=focus_snapshot["transaction_type"],
            ),
            "scope_label": scope_label,
        }

    if intent == "top_categories_multi":
        top_three = get_top_expense_categories(
            db,
            user_id,
            account_id=account_id,
            limit=3,
        )

        if not top_three:
            answer = "I do not have enough expense data yet to identify your top categories."
            intro = generate_mode_intro(mode)
            final_answer = f"{intro} {answer}".strip() if intro else answer

            return {
                "answer": final_answer,
                "supporting_points": [],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [],
                "scope_label": scope_label,
            }

        points = [
            f"{idx + 1}. {item['category']} — {format_currency(item['total'])}"
            for idx, item in enumerate(top_three)
        ]

        if mode == "strict":
            answer = "These categories are taking the biggest share of your money. If you want results, start here."
        elif mode == "coach":
            answer = "These are your top spending categories. They are the best places to look for realistic savings."
        else:
            answer = "These are your top spending categories ranked by total expense amount."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "View all transactions",
                    "page": "transactions",
                }
            ],
            "scope_label": scope_label,
        }

    if intent == "category_transactions":
        top_with_transactions = get_top_categories_with_transactions(
            db,
            user_id,
            account_id=account_id,
            category_limit=3,
            transaction_limit=2,
        )

        if not top_with_transactions:
            answer = "I do not have enough category transaction data yet."
            intro = generate_mode_intro(mode)
            final_answer = f"{intro} {answer}".strip() if intro else answer

            return {
                "answer": final_answer,
                "supporting_points": [],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [],
                "scope_label": scope_label,
            }

        points = []
        for item in top_with_transactions:
            tx_text = ", ".join(
                f"{tx.description} ({format_currency(tx.amount)})"
                for tx in item["transactions"]
            ) or "No recent transactions"
            points.append(
                f"{item['category']} — {format_currency(item['total'])}. Recent items: {tx_text}"
            )

        if mode == "strict":
            answer = "These transactions show where your money is actually going. Review them before looking at charts."
        elif mode == "coach":
            answer = "These transactions help explain your biggest categories. This is a good place to find practical improvements."
        else:
            answer = "Here are the recent transactions inside your biggest expense categories."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "Open transactions",
                    "page": "transactions",
                }
            ],
            "scope_label": scope_label,
        }

    if intent in {"spending_change", "driver", "alerts", "saving_advice", "summary", "balance", "top_category", "general"}:
        driver_reasons = build_driver_explanation(
            expense_change_percent=expense_change_percent,
            top_category=top_category,
            driver_category=primary_driver,
            recent_transactions=recent_transactions,
        )

        if mode == "strict":
            if intent == "saving_advice":
                answer = (
                    f"The clearest weakness is {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "That is where you should cut first if you want meaningful improvement."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The main issue looks straightforward: "
                    + (driver_reasons[0] if driver_reasons else "your spending pattern is under pressure")
                    + "."
                )
            else:
                answer = (
                    f"Your balance is {format_currency(balance)}, and the biggest pressure point is "
                    f"{top_category or 'your top expense area'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )

        elif mode == "coach":
            if intent == "saving_advice":
                answer = (
                    f"The best opportunity right now is {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "A small improvement there could make a noticeable difference."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The strongest signal right now is "
                    + (driver_reasons[0] if driver_reasons else "a change in your recent spending pattern")
                    + ", which gives us a clear place to start."
                )
            else:
                answer = (
                    f"You currently have {format_currency(balance)} available, and your biggest spending pressure is "
                    f"{top_category or 'your top expense area'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "That gives us a clear next step."
                )
        else:
            if intent == "saving_advice":
                answer = (
                    f"The biggest savings opportunity appears to be {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The likely driver is "
                    + (driver_reasons[0] if driver_reasons else "your recent expense pattern")
                    + "."
                )
            else:
                answer = (
                    f"Your balance is {format_currency(balance)}, and your top expense category is "
                    f"{top_category or 'N/A'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )

        supporting_points = [
            f"Balance: {format_currency(balance)}",
            f"Total income: {format_currency(total_income)}",
            f"Total expenses: {format_currency(total_expenses)}",
        ]

        if top_category:
            supporting_points.append(
                f"Top expense category: {top_category} at {format_currency(top_category_amount)}"
            )

        if top_category_share_percent is not None:
            supporting_points.append(
                f"{top_category} represents {top_category_share_percent:.1f}% of all expenses"
            )

        if expense_change_percent is not None:
            supporting_points.append(
                f"Latest monthly expense change: {expense_change_percent:.1f}%"
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent=intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                focus_transaction_type=focus_snapshot["transaction_type"] if focus_snapshot else "expense",
            ),
            "scope_label": scope_label,
        }

    return {
        "answer": "I can help with your balance, top categories, transactions, spending trends, saving ideas, alerts, and summaries.",
        "supporting_points": [
            f"Balance: {format_currency(balance)}",
            f"Top expense category: {top_category or 'N/A'}",
        ],
        "suggested_followups": generate_dynamic_followups(
            intent="general",
            mode=mode,
            top_category=top_category,
            driver_category=primary_driver,
            focus_category=focus_category,
        ),
        "suggested_actions": [],
        "scope_label": scope_label,
    }


def generate_assistant_suggestions(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> list[str]:
    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)
    category_trends = get_category_trends(db, user_id, account_id=account_id)
    budget_snapshot = get_budget_progress_snapshot(
        db,
        user_id,
        month=snapshot["current_month"] or get_default_budget_month(),
        account_id=account_id,
    )
    saved_scenarios = list_saved_scenarios(
        db=db,
        owner_id=user_id,
        account_id=account_id,
    )
    recurring_expenses = get_recurring_expense_patterns(
        db=db,
        user_id=user_id,
        account_id=account_id,
        limit=3,
    )
    simulation_recommendations = build_future_simulation_recommendations(
        db=db,
        user_id=user_id,
        account_id=account_id,
        months=6,
        scope_label=(
            "All accounts combined"
            if account_id is None
            else f"Account {account_id}"
        ),
    )

    suggestions: list[str] = ["What is my balance?"]

    if snapshot["top_category"]:
        suggestions.append(f"Why is {snapshot['top_category']} my top expense category?")
        suggestions.append(f"How can I reduce {snapshot['top_category']} spending?")

    if simulation_recommendations.get("items"):
        suggestions.append("Which savings scenario should I try first?")

    if budget_snapshot["budget_count"] > 0:
        if budget_snapshot["over_budget_count"] > 0:
            suggestions.append("Which category is over budget right now?")
        elif budget_snapshot["projected_over_budget_count"] > 0:
            suggestions.append("Which budget is projected to go over?")
        elif budget_snapshot["at_risk_count"] > 0:
            suggestions.append("Which budget is closest to the limit?")
        elif budget_snapshot["projected_at_risk_count"] > 0:
            suggestions.append("Which budget is projected to get tight?")
        else:
            suggestions.append("Am I on track with my budgets?")

    if category_trends.get("top_increases"):
        suggestions.append(
            f"Why did my {category_trends['top_increases'][0]['category']} spending increase?"
        )

    if snapshot["expense_change_percent"] is not None:
        if snapshot["expense_change_percent"] > 0:
            suggestions.append("Why did my spending increase?")
        elif snapshot["expense_change_percent"] < 0:
            suggestions.append("Why did my spending decrease?")

    if snapshot["current_month"]:
        suggestions.append(f"Summarize my finances for {snapshot['current_month']}")

    if saved_scenarios:
        suggestions.append("Which saved scenario looks strongest?")
        if len(saved_scenarios) > 1:
            suggestions.append("Which saved scenario is safest?")
            suggestions.append("Which saved scenario has the best monthly cash flow?")
            suggestions.append("Which saved scenario gets me closest to my goal?")
            suggestions.append("Compare my saved scenarios")

    if recurring_expenses:
        suggestions.append("What subscriptions or recurring charges do I have?")
        if any(item.get("review_priority") == "high" for item in recurring_expenses):
            suggestions.append("Which subscriptions should I review first?")
            suggestions.append("What happens if I cancel my biggest subscription?")
            if simulation_recommendations.get("items"):
                suggestions.append("Which savings scenario should I try first?")
        suggestions.append("Which recurring charge costs me the most each year?")

    if simulation_recommendations.get("items"):
        suggestions.append("Which savings scenario should I try first?")

    suggestions.append("What will my balance look like in 3 months?")
    suggestions.append("Show my recent transactions")
    suggestions.append("Give me saving advice")

    unique_suggestions: list[str] = []
    for item in suggestions:
        if item not in unique_suggestions:
            unique_suggestions.append(item)

    return unique_suggestions[:8]


def get_dashboard_payload(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    return {
        "summary": get_summary(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "top_category": get_top_expense_category(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "category_breakdown": get_category_breakdown(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "monthly_summary": get_monthly_summary(
            db,
            user_id,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "recent_transactions": get_recent_transactions(
            db,
            user_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            category=category,
            account_id=account_id,
        ),
        "spending_insights": get_spending_insights(db, user_id, account_id=account_id),
        "overspending_alerts": get_overspending_alerts(
            db,
            user_id,
            account_id=account_id,
        ),
        "category_trends": get_category_trends(db, user_id, account_id=account_id),
        "account_comparison": (
            get_account_comparison_snapshot(db, user_id)
            if account_id is None
            else []
        ),
    }
