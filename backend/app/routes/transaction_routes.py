from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Transaction, User
from app.schemas import (
    BulkCategoryApplyRequest,
    BulkCategoryApplyResponse,
    BulkCategorySuggestionItem,
    BulkCategorySuggestionResponse,
    ConfirmPreviewImportRequest,
    FreshStartRequest,
    FreshStartResponse,
    SmartImportResponse,
    SuspiciousAmountRepairApplyRequest,
    SuspiciousAmountRepairApplyResponse,
    SuspiciousAmountRepairItem,
    SuspiciousAmountRepairPreviewResponse,
    TransactionCreate,
    TransactionResponse,
)
from app.services.account_service import ensure_default_account, get_account_for_user
from app.services.seed_service import seed_realistic_transactions
from app.services.transaction_service import (
    apply_bulk_categories,
    build_duplicate_key,
    build_statement_match_key,
    categorize_transaction,
    categorize_transaction_details,
    find_likely_statement_match,
    get_existing_duplicate_keys,
    get_existing_statement_match_map,
    get_transactions_for_user,
    get_uncategorized_candidates,
    merchant_category_amount_matches,
    normalize_category_name,
    normalize_existing_categories_for_user,
    normalize_description,
    resolve_import_category_for_transaction,
    apply_category_to_similar_transactions,
    apply_suspicious_amount_repairs,
    extract_merchant_fingerprint,
    get_suspicious_amount_repair_candidates,
    save_category_memory,
    should_store_category_memory,
)
from app.services.unified_import_service import process_smart_import, process_smart_import_batch

router = APIRouter(prefix="/transactions", tags=["Transactions"])


def save_category_memory_safely(
    db: Session,
    *,
    owner_id: int,
    description: str,
    category: str,
    tx_type: str,
    amount: float,
) -> None:
    try:
        save_category_memory(
            db=db,
            owner_id=owner_id,
            description=description,
            category=category,
            tx_type=tx_type,
            amount=amount,
        )
        db.commit()
    except Exception:
        db.rollback()


def commit_pending_side_effects_safely(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()


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
        category=normalize_category_name(transaction.category),
        description=transaction.description,
        date=transaction.date,
        type=transaction.type,
        owner_id=current_user.id,
        account_id=transaction.account_id,
    )

    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)

    save_category_memory_safely(
        db=db,
        owner_id=current_user.id,
        description=transaction.description,
        category=transaction.category,
        tx_type=transaction.type,
        amount=transaction.amount,
    )
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
    transaction.category = normalize_category_name(updated_data.category)
    transaction.description = updated_data.description
    transaction.date = updated_data.date
    transaction.type = updated_data.type
    transaction.account_id = updated_data.account_id

    apply_category_to_similar_transactions(
        db=db,
        owner_id=current_user.id,
        description=updated_data.description,
        category=updated_data.category,
        tx_type=updated_data.type,
        amount=updated_data.amount,
    )
    db.commit()
    db.refresh(transaction)

    save_category_memory_safely(
        db=db,
        owner_id=current_user.id,
        description=updated_data.description,
        category=updated_data.category,
        tx_type=updated_data.type,
        amount=updated_data.amount,
    )
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


@router.post("/fresh-start", response_model=FreshStartResponse)
def fresh_start_transactions(
    payload: FreshStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.account_id is not None:
        account = get_account_for_user(db, current_user.id, payload.account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

    query = db.query(Transaction).filter(Transaction.owner_id == current_user.id)
    if payload.account_id is not None:
        query = query.filter(Transaction.account_id == payload.account_id)

    if not payload.delete_all:
        if payload.keep_from is None:
            raise HTTPException(
                status_code=400,
                detail="Choose a date to keep transactions from, or confirm deleting all transactions.",
            )
        query = query.filter(Transaction.date < payload.keep_from)

    deleted_count = query.delete(synchronize_session=False)
    db.commit()

    if payload.delete_all:
        message = f"Fresh start complete. Deleted {deleted_count} transaction(s)."
    else:
        message = (
            f"Fresh start complete. Deleted {deleted_count} transaction(s) before "
            f"{payload.keep_from.isoformat()}."
        )

    return {"deleted_count": deleted_count, "message": message}


@router.post("/normalize-categories")
def normalize_categories_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if account_id is not None:
        account = get_account_for_user(db, current_user.id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

    return normalize_existing_categories_for_user(
        db=db,
        owner_id=current_user.id,
        account_id=account_id,
    )


@router.get("/amount-repairs/preview", response_model=SuspiciousAmountRepairPreviewResponse)
def preview_suspicious_amount_repairs(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if account_id is not None:
        account = get_account_for_user(db, current_user.id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

    candidates = get_suspicious_amount_repair_candidates(
        db=db,
        owner_id=current_user.id,
        account_id=account_id,
    )

    return SuspiciousAmountRepairPreviewResponse(
        total_candidates=len(candidates),
        candidates=[
            SuspiciousAmountRepairItem(
                transaction_id=item.transaction_id,
                date=item.date,
                description=item.description,
                type=item.type,
                category=item.category,
                current_amount=item.current_amount,
                suggested_amount=item.suggested_amount,
                confidence=item.confidence,
                reason=item.reason,
            )
            for item in candidates
        ],
    )


@router.post("/amount-repairs/apply", response_model=SuspiciousAmountRepairApplyResponse)
def apply_suspicious_amount_repairs_route(
    payload: SuspiciousAmountRepairApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.account_id is not None:
        account = get_account_for_user(db, current_user.id, payload.account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

    result = apply_suspicious_amount_repairs(
        db=db,
        owner_id=current_user.id,
        transaction_ids=payload.transaction_ids,
        account_id=payload.account_id,
    )
    return SuspiciousAmountRepairApplyResponse(**result)


@router.post("/import/file", response_model=SmartImportResponse)
async def smart_import_file(
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
        result = process_smart_import(
            db=db,
            owner_id=current_user.id,
            account_id=account_id,
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=file.content_type,
        )
        commit_pending_side_effects_safely(db)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Smart import failed: {str(exc)}")


@router.post("/import/files", response_model=SmartImportResponse)
async def smart_import_files(
    files: list[UploadFile] = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_account_for_user(db, current_user.id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        file_payloads = [
            (await file.read(), file.filename or "statement", file.content_type)
            for file in files
        ]
        result = process_smart_import_batch(
            db=db,
            owner_id=current_user.id,
            account_id=account_id,
            files=file_payloads,
        )
        commit_pending_side_effects_safely(db)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Smart batch import failed: {str(exc)}")


@router.post("/import/confirm-preview")
def confirm_preview_import(
    payload: ConfirmPreviewImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_account_for_user(db, current_user.id, payload.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    existing_keys = get_existing_duplicate_keys(
        db=db,
        owner_id=current_user.id,
        account_id=payload.account_id,
    )
    existing_statement_matches = get_existing_statement_match_map(
        db=db,
        owner_id=current_user.id,
        account_id=payload.account_id,
    )
    seen_matched_transaction_ids = set()
    reviewed_categories_by_merchant: dict[tuple[str, str], list[tuple[str, float]]] = {}

    for row in payload.rows:
        normalized_row_category = normalize_category_name(row.category)
        if row.category_review_required or not should_store_category_memory(normalized_row_category):
            continue

        fingerprint = extract_merchant_fingerprint(row.description)
        if fingerprint:
            reviewed_categories_by_merchant.setdefault((fingerprint[0], row.type), []).append(
                (normalized_row_category, row.amount)
            )

    imported = 0
    duplicates_skipped = 0
    invalid_rows_skipped = 0
    category_memory_events = []

    for row in payload.rows:
        try:
            tx_date = date.fromisoformat(row.date)
            description = normalize_description(row.description)
            row_category = row.category
            row_needs_category_review = row.category_review_required
            fingerprint = extract_merchant_fingerprint(description)
            if fingerprint:
                learned_category = None
                reviewed_categories = reviewed_categories_by_merchant.get((fingerprint[0], row.type), [])
                for reviewed_category, reviewed_amount in reviewed_categories:
                    if merchant_category_amount_matches(fingerprint[0], reviewed_amount, row.amount):
                        learned_category = reviewed_category
                        break
                if learned_category and (
                    row_needs_category_review
                    or not should_store_category_memory(normalize_category_name(row_category))
                ):
                    row_category = learned_category
                    row_needs_category_review = False

            normalized_category = resolve_import_category_for_transaction(
                db=db,
                owner_id=current_user.id,
                description=description,
                tx_type=row.type,
                category=row_category,
                amount=row.amount,
            )

            if row_needs_category_review:
                invalid_rows_skipped += 1
                continue

            duplicate_key = build_duplicate_key(
                owner_id=current_user.id,
                account_id=payload.account_id,
                tx_date=tx_date,
                description=description,
                amount=row.amount,
                tx_type=row.type,
                category=normalized_category,
            )
            statement_match_key = build_statement_match_key(
                owner_id=current_user.id,
                account_id=payload.account_id,
                tx_date=tx_date,
                amount=row.amount,
                tx_type=row.type,
            )

            if (
                duplicate_key in existing_keys
                or statement_match_key in existing_statement_matches
            ):
                duplicates_skipped += 1
                continue

            likely_match = find_likely_statement_match(
                db=db,
                owner_id=current_user.id,
                account_id=payload.account_id,
                tx_date=tx_date,
                amount=row.amount,
                tx_type=row.type,
            )
            if likely_match and likely_match.id not in seen_matched_transaction_ids:
                seen_matched_transaction_ids.add(likely_match.id)
                duplicates_skipped += 1
                continue
            if likely_match:
                duplicates_skipped += 1
                continue

            transaction = Transaction(
                amount=row.amount,
                category=normalized_category,
                description=description,
                date=tx_date,
                type=row.type,
                owner_id=current_user.id,
                account_id=payload.account_id,
            )
            db.add(transaction)
            category_memory_events.append(
                {
                    "description": description,
                    "category": normalized_category,
                    "tx_type": row.type,
                    "amount": row.amount,
                }
            )
            imported += 1
        except Exception:
            invalid_rows_skipped += 1

    db.commit()

    try:
        for event in category_memory_events:
            save_category_memory_safely(
                db=db,
                owner_id=current_user.id,
                description=event["description"],
                category=event["category"],
                tx_type=event["tx_type"],
                amount=event["amount"],
            )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "message": "Preview import completed",
        "imported": imported,
        "duplicates_skipped": duplicates_skipped,
        "invalid_rows_skipped": invalid_rows_skipped,
    }


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
        decision = categorize_transaction_details(
            db=db,
            owner_id=current_user.id,
            description=transaction.description,
            tx_type=transaction.type,
            amount=transaction.amount,
        )
        suggested_category = decision.category

        if suggested_category.lower() == transaction.category.lower():
            continue

        if decision.source == "fallback":
            continue

        suggestions.append(
            BulkCategorySuggestionItem(
                transaction_id=transaction.id,
                current_category=transaction.category,
                description=transaction.description,
                type=transaction.type,
                suggested_category=suggested_category,
                confidence=decision.confidence,
                matched_keyword=decision.matched_keyword,
                reason=decision.reason,
            )
        )

    suggestions.sort(
        key=lambda item: (-item.confidence, item.description.lower(), item.transaction_id)
    )

    commit_pending_side_effects_safely(db)

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
        decision = categorize_transaction_details(
            db=db,
            owner_id=current_user.id,
            description=transaction.description,
            tx_type=transaction.type,
            amount=transaction.amount,
        )
        suggestion_map[transaction.id] = decision.category

    updated_count = apply_bulk_categories(
        db=db,
        owner_id=current_user.id,
        transaction_ids=payload.transaction_ids,
        suggested_category_map=suggestion_map,
    )

    return BulkCategoryApplyResponse(updated_count=updated_count)
