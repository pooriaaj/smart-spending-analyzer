from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models import Transaction, User
from app.schemas import TransactionCreate, TransactionResponse

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("/", response_model=TransactionResponse)
def create_transaction(
    transaction_data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transaction = Transaction(
        amount=transaction_data.amount,
        category=transaction_data.category,
        description=transaction_data.description,
        date=transaction_data.date,
        type=transaction_data.type,
        owner_id=current_user.id
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("/", response_model=list[TransactionResponse])
def get_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Transaction).filter(Transaction.owner_id == current_user.id).all()


@router.post("/seed-dummy")
def seed_dummy_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from datetime import date

    dummy_data = [
        Transaction(
            amount=3200.00,
            category="Salary",
            description="Monthly salary",
            date=date(2026, 3, 1),
            type="income",
            owner_id=current_user.id
        ),
        Transaction(
            amount=120.50,
            category="Groceries",
            description="Walmart groceries",
            date=date(2026, 3, 3),
            type="expense",
            owner_id=current_user.id
        ),
        Transaction(
            amount=65.00,
            category="Transport",
            description="Monthly transit pass",
            date=date(2026, 3, 5),
            type="expense",
            owner_id=current_user.id
        ),
        Transaction(
            amount=950.00,
            category="Rent",
            description="Monthly rent payment",
            date=date(2026, 3, 2),
            type="expense",
            owner_id=current_user.id
        )
    ]

    db.add_all(dummy_data)
    db.commit()

    return {"message": "Dummy transactions added successfully"}