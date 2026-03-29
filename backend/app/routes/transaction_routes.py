from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Transaction, User
from app.dependencies import get_current_user
import csv
import io
from datetime import datetime

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get("/")
def get_transactions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Transaction).filter(Transaction.user_id == user.id).all()


@router.post("/")
def create_transaction(data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    transaction = Transaction(
        amount=data["amount"],
        type=data["type"],
        category=data["category"],
        description=data.get("description", ""),
        date=data["date"],
        user_id=user.id
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


# ✅ NEW FEATURE: CSV IMPORT
@router.post("/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    try:
        content = await file.read()
        decoded = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded))

        imported_count = 0

        for row in reader:
            try:
                transaction = Transaction(
                    amount=float(row["amount"]),
                    type=row["type"].lower(),
                    category=row.get("category", "Other"),
                    description=row.get("description", ""),
                    date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                    user_id=user.id
                )

                db.add(transaction)
                imported_count += 1

            except Exception as e:
                print("Skipping row:", row, "Error:", e)

        db.commit()

        return {
            "message": f"{imported_count} transactions imported successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CSV import failed: {str(e)}"
        )