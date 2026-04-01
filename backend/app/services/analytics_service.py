from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Transaction


def build_filtered_query(db: Session, user_id: int,
                         month=None,
                         start_date=None,
                         end_date=None,
                         transaction_type=None,
                         category=None):

    query = db.query(Transaction).filter(Transaction.owner_id == user_id)

    if month:
        query = query.filter(func.to_char(Transaction.date, "YYYY-MM") == month)

    if start_date:
        query = query.filter(Transaction.date >= start_date)

    if end_date:
        query = query.filter(Transaction.date <= end_date)

    if transaction_type:
        query = query.filter(Transaction.type == transaction_type)

    if category:
        query = query.filter(Transaction.category == category)

    return query


def get_summary(db: Session, user_id: int, **filters):
    query = build_filtered_query(db, user_id, **filters)

    total_income = db.query(func.coalesce(func.sum(Transaction.amount), 0))\
        .filter(Transaction.owner_id == user_id)\
        .filter(Transaction.type == "income")\
        .scalar()

    total_expenses = db.query(func.coalesce(func.sum(Transaction.amount), 0))\
        .filter(Transaction.owner_id == user_id)\
        .filter(Transaction.type == "expense")\
        .scalar()

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": total_income - total_expenses
    }


def get_category_breakdown(db: Session, user_id: int, **filters):
    query = build_filtered_query(db, user_id, **filters)

    return query.with_entities(
        Transaction.category,
        func.sum(Transaction.amount).label("total")
    ).filter(Transaction.type == "expense")\
     .group_by(Transaction.category)\
     .order_by(func.sum(Transaction.amount).desc())\
     .all()


def get_monthly_summary(db: Session, user_id: int, **filters):
    query = build_filtered_query(db, user_id, **filters)

    return query.with_entities(
        func.to_char(Transaction.date, "YYYY-MM").label("month"),
        func.sum(
            func.case((Transaction.type == "income", Transaction.amount), else_=0)
        ).label("income"),
        func.sum(
            func.case((Transaction.type == "expense", Transaction.amount), else_=0)
        ).label("expenses")
    ).group_by("month").order_by("month").all()