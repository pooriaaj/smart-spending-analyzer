from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Transaction, User
from app.schemas import (
    BulkCategoryApplyRequest,
    BulkCategoryApplyResponse,
    BulkCategorySuggestionItem,
    BulkCategorySuggestionResponse,
    TransactionCreate,
    TransactionResponse,
)
from app.services.seed_service import seed_realistic_transactions
from app.services.transaction_service import (
    apply_bulk_categories,
    get_transactions_for_user,
    get_uncategorized_candidates,
    import_transactions_from_csv,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


CATEGORY_RULES = {
    "grocery": ["grocery", "supermarket", "market", "freshco", "nofrills", "walmart", "costco"],
    "transport": ["uber", "lyft", "ttc", "metro", "gas", "shell", "esso", "petro"],
    "cafe": ["coffee", "cafe", "starbucks", "tim hortons"],
    "restaurant": ["restaurant", "pizza", "burger", "shawarma", "mcdonald", "kfc", "subway"],
    "rent": ["rent", "landlord", "lease"],
    "salary": ["salary", "payroll", "paycheque", "paycheck", "deposit"],
    "internet": ["internet", "wifi", "rogers", "bell"],
    "phone": ["phone", "mobile", "cell", "telus", "freedom"],
    "entertainment": ["netflix", "spotify", "youtube", "movie", "cinema"],
}


def suggest_category(description: str, tx_type: str) -> tuple[str, float, str | None, str]:
    normalized = description.strip().lower()

    if tx_type == "income":
        if any(keyword in normalized for keyword in CATEGORY_RULES["salary"]):
            return ("salary", 0.95, "salary", "Matched salary-related income keyword.")
        return ("income", 0.70, None, "Defaulted to generic income category.")

    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in normalized:
                return (
                    category,
                    0.92,
                    keyword,
                    f"Matched keyword '{keyword}' to category '{category}'.",
                )

    return ("other", 0.45, None, "No strong keyword match found.")


@router.get("/", response_model=list[TransactionResponse])
def get_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_transactions_for_user(db, current_user.id)


@router.post("/", response_model=TransactionResponse)
def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_transaction = Transaction(
        amount=transaction.amount,
        category=transaction.category,
        description=transaction.description,
        date=transaction.date,
        type=transaction.type,
        owner_id=current_user.id,
    )

    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)
    return new_transaction


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    updated_data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transaction = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.owner_id == current_user.id)
        .first()
    )

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction.amount = updated_data.amount
    transaction.category = updated_data.category
    transaction.description = updated_data.description
    transaction.date = updated_data.date
    transaction.type = updated_data.type

    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transaction = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.owner_id == current_user.id)
        .first()
    )

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(transaction)
    db.commit()
    return {"message": "Transaction deleted successfully"}


@router.post("/import/csv")
async def import_csv_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    try:
        file_bytes = await file.read()
        return import_transactions_from_csv(db, current_user.id, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CSV import failed: {str(exc)}")


@router.post("/seed-realistic")
def seed_realistic_data(
    months: int = 6,
    clear_existing: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if months < 1 or months > 24:
        raise HTTPException(status_code=400, detail="Months must be between 1 and 24")

    return seed_realistic_transactions(
        db=db,
        owner_id=current_user.id,
        months=months,
        clear_existing=clear_existing,
    )


@router.get("/categorize/bulk-preview", response_model=BulkCategorySuggestionResponse)
def get_bulk_category_preview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidates = get_uncategorized_candidates(db, current_user.id)
    suggestions: list[BulkCategorySuggestionItem] = []

    for transaction in candidates:
        suggested_category, confidence, matched_keyword, reason = suggest_category(
            transaction.description,
            transaction.type,
        )

        if suggested_category.lower() == transaction.category.lower():
            continue

        suggestions.append(
            BulkCategorySuggestionItem(
                transaction_id=transaction.id,
                current_category=transaction.category,
                description=transaction.description,
                type=transaction.type,
                suggested_category=suggested_category,
                confidence=confidence,
                matched_keyword=matched_keyword,
                reason=reason,
            )
        )

    return BulkCategorySuggestionResponse(
        total_candidates=len(suggestions),
        suggestions=suggestions,
    )


@router.post("/categorize/bulk-apply", response_model=BulkCategoryApplyResponse)
def apply_bulk_category_suggestions(
    payload: BulkCategoryApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidates = get_uncategorized_candidates(db, current_user.id)

    suggestion_map: dict[int, str] = {}
    for transaction in candidates:
        suggested_category, _, _, _ = suggest_category(
            transaction.description,
            transaction.type,
        )
        suggestion_map[transaction.id] = suggested_category

    updated_count = apply_bulk_categories(
        db=db,
        owner_id=current_user.id,
        transaction_ids=payload.transaction_ids,
        suggested_category_map=suggestion_map,
    )

    return BulkCategoryApplyResponse(updated_count=updated_count)