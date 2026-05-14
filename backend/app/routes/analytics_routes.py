from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import (
    AnalyticsSummary,
    CategoryBreakdownItem,
    CategoryTrendsResponse,
    FutureSimulationRecommendationsResponse,
    FutureSimulationResponse,
    MessageResponse,
    MoneyMapResponse,
    MonthlySummaryItem,
    OverspendingAlertsResponse,
    RecurringExpensesResponse,
    RecentTransactionItem,
    SavedScenarioCreate,
    SavedScenarioResponse,
    SpendingInsights,
    TopExpenseCategory,
)
from app.services.analytics_service import (
    build_saved_scenario_projection_snapshots,
    build_future_simulation_recommendations,
    build_future_balance_simulation,
    get_category_breakdown,
    get_category_trends,
    get_dashboard_payload,
    get_monthly_summary,
    get_overspending_alerts,
    get_recent_transactions,
    get_recurring_expense_patterns,
    get_recurring_transaction_patterns,
    get_spending_insights,
    get_summary,
    get_top_expense_category,
)
from app.services.account_service import get_account_for_user
from app.services.money_map_service import get_money_map_payload
from app.services.saved_scenario_service import (
    create_saved_scenario,
    delete_saved_scenario,
    get_saved_scenario_for_user,
    list_saved_scenarios,
    update_saved_scenario,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def resolve_account_scope(
    db: Session,
    current_user: User,
    account_id: int | None,
) -> str:
    if account_id is None:
        return "All accounts combined"

    account = get_account_for_user(db, current_user.id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return f"{account.name} ({account.type})"


@router.get("/dashboard")
def get_dashboard(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_dashboard_payload(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )


@router.get("/money-map", response_model=MoneyMapResponse)
def get_money_map_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scope_label = resolve_account_scope(db, current_user, account_id)
    return get_money_map_payload(
        db=db,
        user_id=current_user.id,
        account_id=account_id,
        scope_label=scope_label,
    )


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_summary(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )


@router.get("/category-breakdown", response_model=list[CategoryBreakdownItem])
def get_category_breakdown_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_category_breakdown(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )


@router.get("/monthly-summary", response_model=list[MonthlySummaryItem])
def get_monthly_summary_route(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_monthly_summary(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )


@router.get("/recent-transactions", response_model=list[RecentTransactionItem])
def get_recent_transactions_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_recent_transactions(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
        limit=5,
    )


@router.get("/recurring-expenses", response_model=RecurringExpensesResponse)
def get_recurring_expenses_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return {
        "items": get_recurring_expense_patterns(
            db=db,
            user_id=current_user.id,
            account_id=account_id,
        )
    }


@router.get("/recurring-transactions", response_model=RecurringExpensesResponse)
def get_recurring_transactions_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return {
        "items": get_recurring_transaction_patterns(
            db=db,
            user_id=current_user.id,
            account_id=account_id,
            limit=8,
        )
    }


@router.get("/top-expense-category", response_model=TopExpenseCategory | None)
def get_top_expense_category_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_top_expense_category(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        account_id=account_id,
    )


@router.get("/spending-insights", response_model=SpendingInsights)
def get_spending_insights_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_spending_insights(db=db, user_id=current_user.id, account_id=account_id)


@router.get("/overspending-alerts", response_model=OverspendingAlertsResponse)
def get_overspending_alerts_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_overspending_alerts(db=db, user_id=current_user.id, account_id=account_id)


@router.get("/category-trends", response_model=CategoryTrendsResponse)
def get_category_trends_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolve_account_scope(db, current_user, account_id)
    return get_category_trends(db=db, user_id=current_user.id, account_id=account_id)


@router.get("/future-simulator", response_model=FutureSimulationResponse)
def get_future_simulator_route(
    months: int = Query(default=6, ge=1, le=12),
    income_adjustment: float = Query(default=0.0),
    expense_adjustment: float = Query(default=0.0),
    target_balance: float | None = Query(default=None, gt=0),
    event_month_offset: int | None = Query(default=None, ge=1, le=12),
    event_amount: float = Query(default=0.0),
    event_label: str | None = Query(default=None, min_length=1, max_length=80),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scope_label = resolve_account_scope(db, current_user, account_id)
    return build_future_balance_simulation(
        db=db,
        user_id=current_user.id,
        account_id=account_id,
        months=months,
        income_adjustment=income_adjustment,
        expense_adjustment=expense_adjustment,
        target_balance=target_balance,
        event_month_offset=event_month_offset,
        event_amount=event_amount,
        event_label=event_label,
        scope_label=scope_label,
    )


@router.get("/future-simulator-recommendations", response_model=FutureSimulationRecommendationsResponse)
def get_future_simulator_recommendations_route(
    months: int = Query(default=6, ge=1, le=12),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scope_label = resolve_account_scope(db, current_user, account_id)
    return build_future_simulation_recommendations(
        db=db,
        user_id=current_user.id,
        account_id=account_id,
        months=months,
        scope_label=scope_label,
    )


@router.get("/saved-scenarios", response_model=list[SavedScenarioResponse])
def list_saved_scenarios_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scope_label = resolve_account_scope(db, current_user, account_id)
    saved_scenarios = list_saved_scenarios(
        db=db,
        owner_id=current_user.id,
        account_id=account_id,
    )
    snapshots = build_saved_scenario_projection_snapshots(
        db=db,
        user_id=current_user.id,
        account_id=account_id,
        scope_label=scope_label,
    )
    snapshot_by_id = {item["id"]: item for item in snapshots}

    return [
        scenario.model_copy(
            update={
                "projected_end_balance": snapshot_by_id.get(scenario.id, {}).get("projected_end_balance"),
                "monthly_net_change": snapshot_by_id.get(scenario.id, {}).get("monthly_net_change"),
                "risk_level": snapshot_by_id.get(scenario.id, {}).get("risk_level"),
                "lowest_balance": snapshot_by_id.get(scenario.id, {}).get("lowest_balance"),
                "goal_gap_amount": snapshot_by_id.get(scenario.id, {}).get("goal_gap_amount"),
            }
        )
        for scenario in saved_scenarios
    ]


@router.post("/saved-scenarios", response_model=SavedScenarioResponse)
def create_saved_scenario_route(
    payload: SavedScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.account_id is not None:
        account = get_account_for_user(db, current_user.id, payload.account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

    return create_saved_scenario(
        db=db,
        owner_id=current_user.id,
        payload=payload,
    )


@router.put("/saved-scenarios/{scenario_id}", response_model=SavedScenarioResponse)
def update_saved_scenario_route(
    scenario_id: int,
    payload: SavedScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.account_id is not None:
        account = get_account_for_user(db, current_user.id, payload.account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

    scenario = get_saved_scenario_for_user(db, current_user.id, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Saved scenario not found")

    return update_saved_scenario(
        db=db,
        scenario=scenario,
        payload=payload,
    )


@router.delete("/saved-scenarios/{scenario_id}", response_model=MessageResponse)
def delete_saved_scenario_route(
    scenario_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = get_saved_scenario_for_user(db, current_user.id, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Saved scenario not found")

    delete_saved_scenario(db, scenario)
    return MessageResponse(message="Saved scenario deleted")

