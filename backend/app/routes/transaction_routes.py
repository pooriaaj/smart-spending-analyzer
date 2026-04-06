from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Transaction, User
from app.schemas import (
    BulkCategoryApplyRequest,
    BulkCategoryApplyResponse,
    BulkCategorySuggestionItem,
    BulkCategorySuggestionResponse,
    ReceiptScanResponse,
    TransactionCreate,
    TransactionResponse,
)
from app.services.account_service import ensure_default_account, get_account_for_user
from app.services.receipt_service import scan_receipt_file
from app.services.seed_service import seed_realistic_transactions
from app.services.transaction_service import (
    apply_bulk_categories,
    categorize_transaction,
    get_transactions_for_user,
    get_uncategorized_candidates,
    import_transactions_from_csv,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get("/", response_model=list[TransactionResponse])
def get_transactions(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)

    if account_id is not None:
        account = get_account_for_user(db, current_user.id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

    return get_transactions_for_user(db, current_user.id, account_id=account_id)


@router.post("/", response_model=TransactionResponse)
def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)
    account = get_account_for_user(db, current_user.id, transaction.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    new_transaction = Transaction(
        amount=transaction.amount,
        category=transaction.category,
        description=transaction.description,
        date=transaction.date,
        type=transaction.type,
        owner_id=current_user.id,
        account_id=transaction.account_id,
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

    account = get_account_for_user(db, current_user.id, updated_data.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    transaction.amount = updated_data.amount
    transaction.category = updated_data.category
    transaction.description = updated_data.description
    transaction.date = updated_data.date
    transaction.type = updated_data.type
    transaction.account_id = updated_data.account_id

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


@router.post("/import/statement")
async def import_statement_transactions(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_account_for_user(db, current_user.id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV statement files are supported right now")

    try:
        file_bytes = await file.read()
        return import_transactions_from_csv(db, current_user.id, account_id, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Statement import failed: {str(exc)}")


@router.post("/scan-receipt", response_model=ReceiptScanResponse)
async def scan_receipt(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_account_for_user(db, current_user.id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        file_bytes = await file.read()
        return scan_receipt_file(
            db=db,
            owner_id=current_user.id,
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Receipt scan failed: {str(exc)}")


@router.post("/seed-realistic")
def seed_realistic_data(
    months: int = 6,
    clear_existing: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    default_account = ensure_default_account(db, current_user)

    if months < 1 or months > 24:
        raise HTTPException(status_code=400, detail="Months must be between 1 and 24")

    result = seed_realistic_transactions(
        db=db,
        owner_id=current_user.id,
        months=months,
        clear_existing=clear_existing,
    )

    uncategorized = (
        db.query(Transaction)
        .filter(Transaction.owner_id == current_user.id, Transaction.account_id.is_(None))
        .all()
    )
    if uncategorized:
        for item in uncategorized:
            item.account_id = default_account.id
        db.commit()

    return result


@router.get("/categorize/bulk-preview", response_model=BulkCategorySuggestionResponse)
def get_bulk_category_preview(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if account_id is not None:
        account = get_account_for_user(db, current_user.id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

    candidates = get_uncategorized_candidates(db, current_user.id, account_id=account_id)
    suggestions: list[BulkCategorySuggestionItem] = []

    for transaction in candidates:
        suggested_category = categorize_transaction(
            db=db,
            owner_id=current_user.id,
            description=transaction.description,
            tx_type=transaction.type,
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
                confidence=0.9,
                matched_keyword=None,
                reason="Suggested from learned memory and normalized merchant rules.",
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
        suggested_category = categorize_transaction(
            db=db,
            owner_id=current_user.id,
            description=transaction.description,
            tx_type=transaction.type,
        )
        suggestion_map[transaction.id] = suggested_category

    updated_count = apply_bulk_categories(
        db=db,
        owner_id=current_user.id,
        transaction_ids=payload.transaction_ids,
        suggested_category_map=suggestion_map,
    )

    return BulkCategoryApplyResponse(updated_count=updated_count)