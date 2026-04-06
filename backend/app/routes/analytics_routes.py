from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import (
    AnalyticsSummary,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSuggestionsResponse,
    CategoryBreakdownItem,
    CategoryTrendsResponse,
    MonthlySummaryItem,
    OverspendingAlertsResponse,
    RecentTransactionItem,
    SpendingInsights,
    TopExpenseCategory,
)
from app.services.analytics_service import (
    generate_assistant_response,
    generate_assistant_suggestions,
    get_category_breakdown,
    get_category_trends,
    get_dashboard_payload,
    get_monthly_summary,
    get_overspending_alerts,
    get_recent_transactions,
    get_spending_insights,
    get_summary,
    get_top_expense_category,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard")
def get_dashboard(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_dashboard_payload(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
    )


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_summary(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
    )


@router.get("/category-breakdown", response_model=list[CategoryBreakdownItem])
def get_category_breakdown_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_category_breakdown(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
    )


@router.get("/monthly-summary", response_model=list[MonthlySummaryItem])
def get_monthly_summary_route(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_monthly_summary(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
    )


@router.get("/recent-transactions", response_model=list[RecentTransactionItem])
def get_recent_transactions_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_recent_transactions(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
        limit=5,
    )


@router.get("/top-expense-category", response_model=TopExpenseCategory | None)
def get_top_expense_category_route(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_top_expense_category(
        db=db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category=category,
    )


@router.get("/spending-insights", response_model=SpendingInsights)
def get_spending_insights_route(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_spending_insights(db=db, user_id=current_user.id)


@router.get("/overspending-alerts", response_model=OverspendingAlertsResponse)
def get_overspending_alerts_route(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_overspending_alerts(db=db, user_id=current_user.id)


@router.get("/category-trends", response_model=CategoryTrendsResponse)
def get_category_trends_route(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_category_trends(db=db, user_id=current_user.id)


@router.post("/assistant-response", response_model=AssistantQueryResponse)
def get_assistant_response_route(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return generate_assistant_response(
        db=db,
        user_id=current_user.id,
        question=payload.question,
        history=payload.history,
        mode=payload.mode,
    )


@router.get("/assistant-suggestions", response_model=AssistantSuggestionsResponse)
def get_assistant_suggestions_route(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"suggestions": generate_assistant_suggestions(db=db, user_id=current_user.id)}