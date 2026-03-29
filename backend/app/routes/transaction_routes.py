from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models import Transaction, User
from app.schemas import TransactionCreate, TransactionResponse
import csv
import io
from datetime import datetime

router = APIRouter(prefix="/transactions", tags=["Transactions"])


def filter_transactions(
    transactions,
    month: str | None,
    start_date: str | None,
    end_date: str | None,
    transaction_type: str | None,
    category: str | None
):
    result = transactions

    if month:
        result = [
            transaction
            for transaction in result
            if transaction.date.strftime("%Y-%m") == month
        ]

    if start_date:
        start = datetime.fromisoformat(start_date).date()
        result = [
            transaction
            for transaction in result
            if transaction.date >= start
        ]

    if end_date:
        end = datetime.fromisoformat(end_date).date()
        result = [
            transaction
            for transaction in result
            if transaction.date <= end
        ]

    if transaction_type:
        result = [
            transaction
            for transaction in result
            if transaction.type == transaction_type
        ]

    if category:
        result = [
            transaction
            for transaction in result
            if transaction.category == category
        ]

    return result


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


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.owner_id == current_user.id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(transaction)
    db.commit()

    return {"message": "Transaction deleted successfully"}


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    transaction_data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.owner_id == current_user.id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction.amount = transaction_data.amount
    transaction.category = transaction_data.category
    transaction.description = transaction_data.description
    transaction.date = transaction_data.date
    transaction.type = transaction_data.type

    db.commit()
    db.refresh(transaction)

    return transaction


@router.get("/export/csv")
def export_transactions_csv(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    transactions = filter_transactions(
        transactions,
        month,
        start_date,
        end_date,
        transaction_type,
        category
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Date", "Type", "Category", "Description", "Amount"])

    for transaction in sorted(transactions, key=lambda t: t.date, reverse=True):
        writer.writerow([
            transaction.id,
            transaction.date,
            transaction.type,
            transaction.category,
            transaction.description,
            transaction.amount
        ])

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=transactions_export.csv"
        }
    )


@router.post("/import/csv")
async def import_transactions_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    try:
        content = await file.read()
        decoded_content = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded_content))

        required_columns = {"date", "description", "amount", "type", "category"}
        if not reader.fieldnames or not required_columns.issubset(set(reader.fieldnames)):
            raise HTTPException(
                status_code=400,
                detail="CSV must contain: date, description, amount, type, category"
            )

        imported_count = 0

        for row in reader:
            try:
                transaction = Transaction(
                    amount=float(row["amount"]),
                    category=row["category"].strip(),
                    description=row["description"].strip(),
                    date=datetime.strptime(row["date"].strip(), "%Y-%m-%d").date(),
                    type=row["type"].strip().lower(),
                    owner_id=current_user.id
                )

                db.add(transaction)
                imported_count += 1
            except Exception:
                continue

        db.commit()

        return {
            "message": f"{imported_count} transactions imported successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CSV import failed: {str(e)}"
        )