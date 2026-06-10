from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import get_args

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Transaction, User
from app.routes.route_guards import require_owned_account
from app.schemas import (
    BulkCategoryApplyRequest,
    BulkCategoryApplyResponse,
    BulkCategorySuggestionItem,
    BulkCategorySuggestionResponse,
    CategoryLearningApplyRequest,
    CategoryLearningApplyResponse,
    CategoryLearningCandidateItem,
    CategoryLearningCandidatesResponse,
    CategoryLearningSummaryResponse,
    CategoryReviewApplyRequest,
    CategoryReviewApplyResponse,
    CategorySuggestionRequest,
    CategorySuggestionResponse,
    ConfirmPreviewImportRequest,
    DuplicateCleanupApplyRequest,
    DuplicateCleanupApplyResponse,
    FreshStartRequest,
    FreshStartResponse,
    SmartImportResponse,
    SuspiciousAmountRepairApplyRequest,
    SuspiciousAmountRepairApplyResponse,
    SuspiciousAmountRepairItem,
    SuspiciousAmountRepairPreviewResponse,
    TransactionCreate,
    TransactionDataQualityResponse,
    TransactionEntrySource,
    TransactionImportHistoryResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionReviewQueueResponse,
    TransactionSourceSummaryResponse,
)
from app.services.account_service import ensure_default_account
from app.security import ensure_batch_file_count, ensure_batch_payload_size, read_validated_import_upload
from app.services.import_quality_service import suggest_reference_code_amount_values
from app.services.seed_service import seed_realistic_transactions
from app.services.transaction_service import (
    apply_category_to_merchant_learning_group,
    apply_bulk_categories,
    apply_likely_duplicate_cleanup,
    build_duplicate_key,
    build_statement_match_key,
    categorize_transaction,
    categorize_transaction_details,
    find_likely_statement_match,
    get_existing_duplicate_keys,
    get_existing_statement_match_map,
    get_category_learning_candidates,
    get_category_learning_summary,
    get_transaction_data_quality_report,
    get_transaction_import_history,
    get_transaction_review_queue,
    get_transaction_source_summary,
    get_transactions_page_for_user,
    get_transactions_for_user,
    get_uncategorized_candidates,
    apply_category_review_correction,
    is_usable_category_name,
    merchant_category_amount_matches,
    normalize_category_name,
    normalize_existing_categories_for_user,
    record_category_learning_event,
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
logger = logging.getLogger(__name__)
VALID_ENTRY_SOURCES = set(get_args(TransactionEntrySource))


def safe_upload_extension(filename: str | None) -> str:
    return Path(filename or "").suffix.lower() or "unknown"


def validate_transaction_category(category: str) -> None:
    if not is_usable_category_name(category):
        raise HTTPException(
            status_code=400,
            detail="Category must be at least 2 letters or numbers. Use a full category name, not a single key.",
        )


def save_category_memory_safely(
    db: Session,
    *,
    owner_id: int,
    description: str,
    category: str,
    tx_type: str,
    amount: float,
    account_id: int | None = None,
    signal_source: str = "manual",
    confidence: float = 1.0,
    affected_count: int = 1,
    record_event: bool = True,
    store_memory: bool = True,
) -> None:
    try:
        if store_memory:
            save_category_memory(
                db=db,
                owner_id=owner_id,
                description=description,
                category=category,
                tx_type=tx_type,
                amount=amount,
            )
        if record_event:
            record_category_learning_event(
                db=db,
                owner_id=owner_id,
                description=description,
                category=category,
                tx_type=tx_type,
                amount=amount,
                account_id=account_id,
                signal_source=signal_source,
                confidence=confidence,
                affected_count=affected_count,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "Category learning side effect skipped for owner_id=%s signal_source=%s",
            owner_id,
            signal_source,
            exc_info=True,
        )


def commit_pending_side_effects_safely(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Import side effects commit skipped", exc_info=True)


def entry_source_for_preview_row(row) -> str:
    if row.source_file_type == "csv_statement":
        return "csv_import"
    if row.source_file_type == "pdf_statement":
        return "pdf_import"
    if row.source_file_type == "receipt_image":
        return "receipt_import"
    if row.source_line and "manual" in row.source_line.lower():
        return "manual_import_review"
    return "statement_import"


@router.get("/", response_model=list[TransactionResponse])
def get_transactions(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)
    require_owned_account(db, current_user, account_id, allow_all=True)

    return get_transactions_for_user(
        db,
        current_user.id,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )


@router.get("/page", response_model=TransactionListResponse)
def get_transactions_page(
    account_id: int | None = Query(default=None),
    transaction_type: str | None = Query(default=None, alias="type"),
    month: str | None = Query(default=None),
    category: str | None = Query(default=None),
    entry_source: str | None = Query(default=None),
    description: str | None = Query(default=None),
    amount_min: float | None = Query(default=None),
    amount_max: float | None = Query(default=None),
    amount_min_exclusive: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)

    require_owned_account(db, current_user, account_id, allow_all=True)

    if transaction_type is not None and transaction_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Transaction type must be income or expense")
    if entry_source is not None and entry_source not in VALID_ENTRY_SOURCES:
        raise HTTPException(status_code=400, detail="Entry source filter is not supported")
    if amount_min is not None and amount_max is not None and amount_min >= amount_max:
        raise HTTPException(status_code=400, detail="Amount minimum must be lower than amount maximum")

    try:
        result = get_transactions_page_for_user(
            db=db,
            owner_id=current_user.id,
            account_id=account_id,
            transaction_type=transaction_type,
            month=month,
            category=category,
            entry_source=entry_source,
            description=description,
            amount_min=amount_min,
            amount_max=amount_max,
            amount_min_exclusive=amount_min_exclusive,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return TransactionListResponse(**result)


@router.get("/sources/summary", response_model=TransactionSourceSummaryResponse)
def get_transaction_sources_summary(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)

    require_owned_account(db, current_user, account_id, allow_all=True)

    return TransactionSourceSummaryResponse(
        **get_transaction_source_summary(db, current_user.id, account_id=account_id)
    )


@router.get("/quality-report", response_model=TransactionDataQualityResponse)
def get_transaction_quality_report(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)

    require_owned_account(db, current_user, account_id, allow_all=True)

    return TransactionDataQualityResponse(
        **get_transaction_data_quality_report(db, current_user.id, account_id=account_id)
    )


@router.get("/review-queue", response_model=TransactionReviewQueueResponse)
def get_transaction_review_queue_route(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=25),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)

    require_owned_account(db, current_user, account_id, allow_all=True)

    return TransactionReviewQueueResponse(
        **get_transaction_review_queue(
            db=db,
            owner_id=current_user.id,
            account_id=account_id,
            limit=limit,
        )
    )


@router.get("/import/history", response_model=TransactionImportHistoryResponse)
def get_import_history(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)

    require_owned_account(db, current_user, account_id, allow_all=True)

    return TransactionImportHistoryResponse(
        **get_transaction_import_history(
            db,
            current_user.id,
            account_id=account_id,
            limit=limit,
        )
    )


@router.post("/", response_model=TransactionResponse)
def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_default_account(db, current_user)
    validate_transaction_category(transaction.category)
    require_owned_account(db, current_user, transaction.account_id)

    new_transaction = Transaction(
        amount=transaction.amount,
        category=normalize_category_name(transaction.category),
        category_confidence=1.0,
        category_source="manual",
        category_reason="User entered this category manually.",
        description=transaction.description,
        date=transaction.date,
        type=transaction.type,
        entry_source="manual",
        owner_id=current_user.id,
        account_id=transaction.account_id,
    )

    db.add(new_transaction)
    similar_updated_count = apply_category_to_similar_transactions(
        db=db,
        owner_id=current_user.id,
        description=transaction.description,
        category=transaction.category,
        tx_type=transaction.type,
        amount=transaction.amount,
        account_id=transaction.account_id,
        signal_source="manual_create",
        category_source="manual_create",
        category_confidence=1.0,
        category_reason="User entered a category for a matching merchant.",
    )
    db.commit()
    db.refresh(new_transaction)

    save_category_memory_safely(
        db=db,
        owner_id=current_user.id,
        description=transaction.description,
        category=transaction.category,
        tx_type=transaction.type,
        amount=transaction.amount,
        account_id=transaction.account_id,
        signal_source="manual_create",
        affected_count=similar_updated_count + 1,
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

    validate_transaction_category(updated_data.category)
    require_owned_account(db, current_user, updated_data.account_id)

    transaction.amount = updated_data.amount
    transaction.category = normalize_category_name(updated_data.category)
    transaction.category_confidence = 1.0
    transaction.category_source = "manual_edit"
    transaction.category_reason = "User edited this category manually."
    transaction.description = updated_data.description
    transaction.date = updated_data.date
    transaction.type = updated_data.type
    transaction.account_id = updated_data.account_id

    similar_updated_count = apply_category_to_similar_transactions(
        db=db,
        owner_id=current_user.id,
        description=updated_data.description,
        category=updated_data.category,
        tx_type=updated_data.type,
        amount=updated_data.amount,
        account_id=updated_data.account_id,
        signal_source="manual_edit",
        category_source="manual_edit",
        category_confidence=1.0,
        category_reason="User edited a similar transaction category manually.",
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
        account_id=updated_data.account_id,
        signal_source="manual_edit",
        affected_count=similar_updated_count + 1,
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


@router.get("/fresh-start/count")
def count_fresh_start_transactions(
    account_id: int | None = Query(default=None),
    keep_from: date | None = Query(default=None),
    delete_all: bool = Query(default=False),
    entry_source: TransactionEntrySource | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, account_id, allow_all=True)

    query = db.query(Transaction).filter(Transaction.owner_id == current_user.id)
    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)
    if entry_source is not None:
        query = query.filter(Transaction.entry_source == entry_source)

    if not delete_all:
        if keep_from is None:
            raise HTTPException(
                status_code=400,
                detail="Provide keep_from or set delete_all=true.",
            )
        query = query.filter(Transaction.date < keep_from)

    return {"count": query.count()}


@router.post("/fresh-start", response_model=FreshStartResponse)
def fresh_start_transactions(
    payload: FreshStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, payload.account_id, allow_all=True)

    query = db.query(Transaction).filter(Transaction.owner_id == current_user.id)
    if payload.account_id is not None:
        query = query.filter(Transaction.account_id == payload.account_id)
    if payload.entry_source is not None:
        query = query.filter(Transaction.entry_source == payload.entry_source)

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
    require_owned_account(db, current_user, account_id, allow_all=True)

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
    require_owned_account(db, current_user, account_id, allow_all=True)

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
    require_owned_account(db, current_user, payload.account_id, allow_all=True)

    result = apply_suspicious_amount_repairs(
        db=db,
        owner_id=current_user.id,
        transaction_ids=payload.transaction_ids,
        account_id=payload.account_id,
    )
    return SuspiciousAmountRepairApplyResponse(**result)


@router.post("/duplicates/apply", response_model=DuplicateCleanupApplyResponse)
def apply_duplicate_cleanup_route(
    payload: DuplicateCleanupApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, payload.account_id, allow_all=True)

    result = apply_likely_duplicate_cleanup(
        db=db,
        owner_id=current_user.id,
        transaction_ids=payload.transaction_ids,
        account_id=payload.account_id,
    )
    return DuplicateCleanupApplyResponse(**result)


@router.post("/import/file", response_model=SmartImportResponse)
async def smart_import_file(
    request: Request,
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, account_id)

    try:
        file_bytes, safe_filename, safe_content_type = await read_validated_import_upload(file)
        result = process_smart_import(
            db=db,
            owner_id=current_user.id,
            account_id=account_id,
            file_bytes=file_bytes,
            filename=safe_filename,
            content_type=safe_content_type,
        )
        commit_pending_side_effects_safely(db)
        logger.info(
            "Smart import completed user_id=%s account_id=%s request_id=%s extension=%s content_type=%s size_bytes=%s detected_type=%s status=%s preview_rows=%s invalid_rows=%s",
            current_user.id,
            account_id,
            getattr(request.state, "request_id", None),
            safe_upload_extension(safe_filename),
            safe_content_type or "unknown",
            len(file_bytes),
            result.get("detected_type"),
            result.get("status"),
            len(result.get("preview_rows", [])),
            (result.get("import_summary") or {}).get("invalid_rows_skipped", 0),
        )
        return result
    except ValueError as exc:
        db.rollback()
        logger.warning(
            "Smart import rejected user_id=%s account_id=%s request_id=%s error=%s",
            current_user.id,
            account_id,
            getattr(request.state, "request_id", None),
            str(exc)[:300],
        )
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "Smart import failed for user_id=%s account_id=%s request_id=%s",
            current_user.id,
            account_id,
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Smart import failed. Please try a different file.",
                "request_id": request_id,
                "stage": getattr(exc, "stage", "smart_import_processing"),
            },
        )


@router.post("/import/files", response_model=SmartImportResponse)
async def smart_import_files(
    request: Request,
    files: list[UploadFile] = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, account_id)

    try:
        files = ensure_batch_file_count(files)
        file_payloads = [
            await read_validated_import_upload(file)
            for file in files
        ]
        ensure_batch_payload_size(file_payloads)
        result = process_smart_import_batch(
            db=db,
            owner_id=current_user.id,
            account_id=account_id,
            files=file_payloads,
        )
        commit_pending_side_effects_safely(db)
        logger.info(
            "Smart batch import completed user_id=%s account_id=%s request_id=%s file_count=%s total_size_bytes=%s detected_type=%s status=%s preview_rows=%s invalid_rows=%s",
            current_user.id,
            account_id,
            getattr(request.state, "request_id", None),
            len(file_payloads),
            sum(len(file_bytes) for file_bytes, _, _ in file_payloads),
            result.get("detected_type"),
            result.get("status"),
            len(result.get("preview_rows", [])),
            (result.get("import_summary") or {}).get("invalid_rows_skipped", 0),
        )
        return result
    except ValueError as exc:
        db.rollback()
        logger.warning(
            "Smart batch import rejected user_id=%s account_id=%s request_id=%s error=%s",
            current_user.id,
            account_id,
            getattr(request.state, "request_id", None),
            str(exc)[:300],
        )
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "Smart batch import failed for user_id=%s account_id=%s request_id=%s",
            current_user.id,
            account_id,
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Smart batch import failed. Please review the files and try again.",
                "request_id": request_id,
                "stage": getattr(exc, "stage", "smart_batch_import_processing"),
            },
        )


@router.post("/import/confirm-preview")
def confirm_preview_import(
    payload: ConfirmPreviewImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, payload.account_id)

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
            row_amount = float(row.amount)
            if row.amount_review_required and not row.amount_review_approved:
                still_suspicious = suggest_reference_code_amount_values(
                    description=description,
                    amount=row_amount,
                )
                if still_suspicious:
                    invalid_rows_skipped += 1
                    continue

            row_category = row.category
            row_needs_category_review = row.category_review_required
            if not is_usable_category_name(row_category):
                invalid_rows_skipped += 1
                continue

            fingerprint = extract_merchant_fingerprint(description)
            if fingerprint:
                learned_category = None
                reviewed_categories = reviewed_categories_by_merchant.get((fingerprint[0], row.type), [])
                for reviewed_category, reviewed_amount in reviewed_categories:
                    if merchant_category_amount_matches(fingerprint[0], reviewed_amount, row_amount):
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
                amount=row_amount,
            )

            if row_needs_category_review:
                invalid_rows_skipped += 1
                continue

            duplicate_key = build_duplicate_key(
                owner_id=current_user.id,
                account_id=payload.account_id,
                tx_date=tx_date,
                description=description,
                amount=row_amount,
                tx_type=row.type,
                category=normalized_category,
            )
            statement_match_key = build_statement_match_key(
                owner_id=current_user.id,
                account_id=payload.account_id,
                tx_date=tx_date,
                amount=row_amount,
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
                amount=row_amount,
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
                amount=row_amount,
                category=normalized_category,
                category_confidence=row.category_confidence or 0.0,
                category_source=row.category_source or "import_review",
                category_reason=(
                    row.category_reason
                    or row.category_review_reason
                    or "Saved from the statement import review flow."
                ),
                description=description,
                date=tx_date,
                type=row.type,
                entry_source=entry_source_for_preview_row(row),
                import_file_name=row.source_file_name,
                import_file_type=row.source_file_type,
                imported_at=datetime.now(timezone.utc),
                owner_id=current_user.id,
                account_id=payload.account_id,
            )
            db.add(transaction)
            category_memory_events.append(
                {
                    "description": description,
                    "category": normalized_category,
                    "tx_type": row.type,
                    "amount": row_amount,
                    "account_id": payload.account_id,
                    "source": row.category_source or "import",
                    "confidence": row.category_confidence,
                }
            )
            imported += 1
        except Exception:
            invalid_rows_skipped += 1
            logger.warning(
                "Skipping import row due to processing error user_id=%s account_id=%s date=%s desc=%s",
                current_user.id,
                payload.account_id,
                getattr(row, "date", "?"),
                (getattr(row, "description", "") or "")[:80],
                exc_info=True,
            )

    db.commit()

    try:
        for event in category_memory_events:
            user_reviewed_category = str(event["source"]).startswith("user_")
            similar_updated_count = 0
            if user_reviewed_category:
                similar_updated_count = apply_category_to_similar_transactions(
                    db=db,
                    owner_id=current_user.id,
                    description=event["description"],
                    category=event["category"],
                    tx_type=event["tx_type"],
                    amount=event["amount"],
                    account_id=event["account_id"],
                    signal_source="import_review",
                    category_source="import_review",
                    category_confidence=1.0,
                    category_reason=(
                        "Applied from a user-reviewed category during statement import."
                    ),
                )
            save_category_memory_safely(
                db=db,
                owner_id=current_user.id,
                description=event["description"],
                category=event["category"],
                tx_type=event["tx_type"],
                amount=event["amount"],
                account_id=event["account_id"],
                signal_source=(
                    "import_review"
                    if user_reviewed_category
                    else "import_confirm"
                ),
                confidence=float(event.get("confidence") or 0.0),
                affected_count=similar_updated_count + 1,
                record_event=user_reviewed_category,
                store_memory=user_reviewed_category,
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "Preview import category learning side effects skipped for user_id=%s account_id=%s",
            current_user.id,
            payload.account_id,
            exc_info=True,
        )

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


@router.get("/categorize/learning-candidates", response_model=CategoryLearningCandidatesResponse)
def get_category_learning_candidates_route(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, account_id, allow_all=True)

    candidates = get_category_learning_candidates(
        db=db,
        owner_id=current_user.id,
        account_id=account_id,
        limit=limit,
    )

    return CategoryLearningCandidatesResponse(
        total_candidates=len(candidates),
        candidates=[
            CategoryLearningCandidateItem(
                merchant_key=item.merchant_key,
                display_name=item.display_name,
                type=item.type,
                transaction_count=item.transaction_count,
                current_category=item.current_category,
                suggested_category=item.suggested_category,
                confidence=item.confidence,
                total_amount=item.total_amount,
                representative_amount=item.representative_amount,
                amount_min=item.amount_min,
                amount_max=item.amount_max,
                example_descriptions=item.example_descriptions,
                reason=item.reason,
                review_required=item.review_required,
            )
            for item in candidates
        ],
    )


@router.get("/categorize/learning-summary", response_model=CategoryLearningSummaryResponse)
def get_category_learning_summary_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, account_id, allow_all=True)

    summary = get_category_learning_summary(
        db=db,
        owner_id=current_user.id,
        account_id=account_id,
    )
    return CategoryLearningSummaryResponse(**summary)


@router.post("/categorize/learning-apply", response_model=CategoryLearningApplyResponse)
def apply_category_learning_candidate_route(
    payload: CategoryLearningApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    validate_transaction_category(payload.category)
    require_owned_account(db, current_user, payload.account_id, allow_all=True)

    result = apply_category_to_merchant_learning_group(
        db=db,
        owner_id=current_user.id,
        merchant_key=payload.merchant_key,
        tx_type=payload.type,
        category=payload.category,
        account_id=payload.account_id,
        representative_amount=payload.representative_amount,
    )
    return CategoryLearningApplyResponse(**result)


@router.post("/categorize/review-apply", response_model=CategoryReviewApplyResponse)
def apply_category_review_correction_route(
    payload: CategoryReviewApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    validate_transaction_category(payload.category)
    result = apply_category_review_correction(
        db=db,
        owner_id=current_user.id,
        transaction_id=payload.transaction_id,
        category=payload.category,
        apply_to_similar=payload.apply_to_similar,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return CategoryReviewApplyResponse(**result)


@router.post("/categorize/suggest", response_model=CategorySuggestionResponse)
def suggest_transaction_category(
    payload: CategorySuggestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    decision = categorize_transaction_details(
        db=db,
        owner_id=current_user.id,
        description=payload.description,
        tx_type=payload.type,
        amount=payload.amount,
    )
    return CategorySuggestionResponse(
        suggested_category=decision.category,
        confidence=decision.confidence,
        matched_keyword=decision.matched_keyword,
        reason=decision.reason,
    )


@router.get("/categorize/bulk-preview", response_model=BulkCategorySuggestionResponse)
def get_bulk_category_preview(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_owned_account(db, current_user, account_id, allow_all=True)

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
    candidates = get_uncategorized_candidates(
        db,
        current_user.id,
        transaction_ids=payload.transaction_ids,
    )

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
