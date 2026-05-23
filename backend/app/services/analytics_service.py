from __future__ import annotations

from datetime import date, timedelta
import re
import unicodedata
from typing import Any

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Query, Session

from app.models import Account, BudgetPlan, Transaction
from app.services.budget_metrics import (
    build_budget_action_insights,
    build_budget_pace_context,
    build_budget_projection_context,
    compute_budget_status,
    get_default_budget_month,
)
from app.services.saved_scenario_service import list_saved_scenarios
from app.services.transaction_service import get_transaction_data_quality_report


CASHFLOW_NEUTRAL_CATEGORIES = {
    "transfer",
    "transfers",
    "refund",
    "refunds",
    "credit card payment",
    "credit card payments",
}
CASHFLOW_NEUTRAL_DESCRIPTION_MARKERS = (
    "e-transfer received",
    "e-transfer sent",
    "interac received",
    "interac sent",
    "online transfer",
    "online banking transfer",
    "transfer to deposit account",
    "payment - thank you",
    "payment thank you",
    "paiement - merci",
    "payback with points",
    "atm deposit",
    "virement interac",
    "virement en ligne",
)

ANALYTICS_CATEGORY_ALIASES = {
    "cafe": {"cafe", "café", "coffee"},
    "car maintenance": {"car maintenance", "car_maintenance"},
    "debt": {"debt", "debt payment", "debt payments", "debt_payment", "debt_payments"},
    "education": {"education", "school", "tuition"},
    "groceries": {"grocery", "groceries"},
    "healthcare": {"health", "healthcare"},
    "other": {"other", "misc", "miscellaneous", "uncategorized", "unknown"},
    "restaurant": {"restaurant", "restaurants"},
    "smoking": {"smoking", "smokes", "weed", "cigarette", "cigarettes", "cigar", "cigars"},
    "subscriptions": {"subscription", "subscriptions"},
    "transfer": {"transfer", "transfers"},
    "transport": {"transport", "transportation"},
    "utilities": {"utility", "utilities"},
}

ESSENTIAL_RECURRING_CATEGORY_KEYWORDS = {
    "debt",
    "education",
    "housing",
    "insurance",
    "internet",
    "mortgage",
    "phone",
    "rent",
    "tax",
    "taxes",
    "tuition",
    "utilities",
    "utility",
}

ESSENTIAL_RECURRING_DESCRIPTION_KEYWORDS = {
    "bell",
    "car insurance",
    "cell",
    "cellular",
    "credit card payment",
    "debt",
    "electric",
    "enbridge",
    "fido",
    "freedom mobile",
    "gas bill",
    "hazelview",
    "hydro",
    "insurance",
    "internet",
    "koodo",
    "loan",
    "minimum payment",
    "mobile",
    "mortgage",
    "phone",
    "public mobile",
    "rent",
    "rogers",
    "telus",
    "tuition",
    "virgin plus",
    "virgin mobile",
    "water bill",
    "wireless",
}


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def month_bucket_expression(db: Session):
    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    if getattr(dialect_name, "name", None) == "sqlite":
        return func.strftime("%Y-%m", Transaction.date)
    return func.to_char(Transaction.date, "YYYY-MM")


def normalize_analytics_category(value: str | None) -> str:
    cleaned = str(value or "").strip().lower().replace("&", "and")
    cleaned = (
        unicodedata.normalize("NFD", cleaned)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    cleaned = re.sub(r"[_\-]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned)


def normalized_category_expression():
    return func.lower(
        func.replace(
            func.replace(func.coalesce(Transaction.category, ""), "_", " "),
            "-",
            " ",
        )
    )


def analytics_category_alias_match(value: str | None) -> tuple[str, set[str]]:
    normalized = normalize_analytics_category(value)
    if not normalized:
        return "other", {"other"}

    for canonical, aliases in ANALYTICS_CATEGORY_ALIASES.items():
        normalized_aliases = {normalize_analytics_category(alias) for alias in aliases}
        raw_aliases = {str(alias or "").strip().lower() for alias in aliases if str(alias or "").strip()}
        if normalized == canonical or normalized in normalized_aliases:
            return canonical, normalized_aliases | raw_aliases | {canonical}

    return normalized, {normalized}


def canonical_analytics_category(value: str | None) -> str:
    canonical, _ = analytics_category_alias_match(value)
    return canonical


def get_analytics_category_variants(category: str | None) -> set[str]:
    _, variants = analytics_category_alias_match(category)
    return variants


def is_cashflow_neutral_category(category: str | None) -> bool:
    return normalize_analytics_category(category) in CASHFLOW_NEUTRAL_CATEGORIES


def cashflow_neutral_filter():
    normalized_category = normalized_category_expression()
    normalized_description = func.lower(func.coalesce(Transaction.description, ""))
    description_filters = [
        normalized_description.like(f"%{marker}%")
        for marker in CASHFLOW_NEUTRAL_DESCRIPTION_MARKERS
    ]
    return or_(
        normalized_category.in_(tuple(CASHFLOW_NEUTRAL_CATEGORIES)),
        *description_filters,
    )


def transaction_amount_magnitude_expression():
    return func.abs(func.coalesce(Transaction.amount, 0.0))


def income_amount_expression():
    return case((Transaction.type == "income", transaction_amount_magnitude_expression()), else_=0.0)


def expense_amount_expression():
    return case((Transaction.type == "expense", transaction_amount_magnitude_expression()), else_=0.0)


def build_filtered_query(
    db: Session,
    user_id: int,
    month: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    transaction_type: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
    include_cashflow_neutral: bool = False,
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
        category_variants = get_analytics_category_variants(category)
        if category_variants:
            query = query.filter(normalized_category_expression().in_(tuple(category_variants)))
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    if not include_cashflow_neutral and not is_cashflow_neutral_category(category):
        query = query.filter(~cashflow_neutral_filter())

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
            func.sum(income_amount_expression()),
            0.0,
        ).label("total_income"),
        func.coalesce(
            func.sum(expense_amount_expression()),
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


def merge_category_totals(rows) -> list[dict[str, Any]]:
    totals_by_category: dict[str, float] = {}

    for row in rows:
        category = canonical_analytics_category(row.category)
        totals_by_category[category] = totals_by_category.get(category, 0.0) + float(row.total or 0.0)

    return sorted(
        (
            {"category": category, "total": round(total, 2)}
            for category, total in totals_by_category.items()
        ),
        key=lambda item: item["total"],
        reverse=True,
    )


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

    expense_total_expression = func.coalesce(func.sum(transaction_amount_magnitude_expression()), 0.0)
    rows = (
        query.with_entities(
            Transaction.category.label("category"),
            expense_total_expression.label("total"),
        )
        .group_by(Transaction.category)
        .order_by(expense_total_expression.desc())
        .all()
    )

    return merge_category_totals(rows)


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
                func.sum(income_amount_expression()),
                0.0,
            ).label("income"),
            func.coalesce(
                func.sum(expense_amount_expression()),
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
    return get_category_breakdown(db, user_id, account_id=account_id)[:limit]


def get_transactions_for_category(
    db: Session,
    user_id: int,
    category: str,
    account_id: int | None = None,
    limit: int = 5,
) -> list[Transaction]:
    category_variants = get_analytics_category_variants(category)
    query = db.query(Transaction).filter(Transaction.owner_id == user_id)
    if category_variants:
        query = query.filter(normalized_category_expression().in_(tuple(category_variants)))

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
    breakdown = get_category_breakdown(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )

    return breakdown[0] if breakdown else None


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
    data_quality = get_transaction_data_quality_report(db, user_id, account_id=account_id)
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

    if data_quality["quality_level"] in {"empty", "low"}:
        assumptions.append(
            "Forecast confidence is low until suspicious amounts, duplicates, and uncategorized rows are reviewed."
        )
    elif data_quality["quality_level"] == "medium":
        assumptions.append(
            "Forecast confidence is medium because some transaction review work is still available."
        )
    else:
        assumptions.append("Forecast confidence is high because transaction data quality looks clean.")

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
        "data_quality_level": data_quality["quality_level"],
        "data_quality_score": data_quality["quality_score"],
        "data_quality_message": data_quality["message"],
        "data_review_action_count": len(data_quality["actions"]),
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
            func.coalesce(func.sum(transaction_amount_magnitude_expression()), 0.0).label("total"),
        ).filter(
            Transaction.owner_id == user_id,
            Transaction.type == "expense",
            month_expr.in_(recent_month_labels),
            ~cashflow_neutral_filter(),
        )

        if account_id is not None:
            query = query.filter(Transaction.account_id == account_id)

        rows = (
            query.group_by(Transaction.category, month_expr)
            .order_by(func.sum(transaction_amount_magnitude_expression()).desc())
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


def get_recurring_transaction_patterns(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    *,
    limit: int = 5,
    transaction_type: str | None = None,
) -> list[dict[str, Any]]:
    transactions = (
        build_filtered_query(
            db=db,
            user_id=user_id,
            transaction_type=transaction_type,
            account_id=account_id,
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    groups: dict[tuple[str, str, str], list[Transaction]] = {}
    for transaction in transactions:
        normalized_description = normalize_recurring_description(transaction.description)
        if len(normalized_description) < 3:
            continue
        groups.setdefault(
            (transaction.type, normalized_description, transaction.category),
            [],
        ).append(transaction)

    recurring_items: list[dict[str, Any]] = []
    for (item_type, _, category), items in groups.items():
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
                "type": item_type,
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


def get_recurring_expense_patterns(
    db: Session,
    user_id: int,
    account_id: int | None = None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    return get_recurring_transaction_patterns(
        db=db,
        user_id=user_id,
        account_id=account_id,
        limit=limit,
        transaction_type="expense",
    )


def normalized_text_contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {normalize_analytics_category(text)} "
    normalized_phrase = normalize_analytics_category(phrase)

    if not normalized_phrase:
        return False

    return f" {normalized_phrase} " in normalized_text


def is_essential_recurring_item(item: dict[str, Any]) -> bool:
    category = canonical_analytics_category(item.get("category"))
    description = str(item.get("description") or "")

    if any(
        normalized_text_contains_phrase(category, keyword)
        for keyword in ESSENTIAL_RECURRING_CATEGORY_KEYWORDS
    ):
        return True

    return any(
        normalized_text_contains_phrase(description, keyword)
        for keyword in ESSENTIAL_RECURRING_DESCRIPTION_KEYWORDS
    )


def build_recurring_savings_opportunities(
    recurring_expenses: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    opportunities = [
        item
        for item in recurring_expenses
        if (item.get("average_amount") or 0.0) > 0
        and not is_essential_recurring_item(item)
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
        "data_quality": get_transaction_data_quality_report(
            db,
            user_id,
            account_id=account_id,
        ),
    }
