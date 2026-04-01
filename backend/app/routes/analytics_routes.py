from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.services.analytics_service import (
    get_summary,
    get_category_breakdown,
    get_monthly_summary
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    month: str = None,
    start_date: str = None,
    end_date: str = None,
    transaction_type: str = None,
    category: str = None
):
    filters = {
        "month": month,
        "start_date": start_date,
        "end_date": end_date,
        "transaction_type": transaction_type,
        "category": category
    }

    return {
        "summary": get_summary(db, current_user.id, **filters),
        "category_breakdown": get_category_breakdown(db, current_user.id, **filters),
        "monthly_summary": get_monthly_summary(db, current_user.id, **filters)
    }