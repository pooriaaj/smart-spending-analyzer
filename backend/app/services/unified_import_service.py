from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.schemas import StatementPreviewRow
from app.services.pdf_statement_service import parse_pdf_statement_preview
from app.services.receipt_service import scan_receipt_file
from app.services.transaction_service import (
    build_statement_match_key,
    build_duplicate_key,
    describe_likely_statement_match,
    find_likely_statement_match,
    get_existing_duplicate_keys,
    get_existing_statement_match_map,
    parse_csv_statement_preview,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CSV_EXTENSIONS = {".csv"}
PDF_EXTENSIONS = {".pdf"}


def annotate_preview_rows_for_duplicates(
    db: Session,
    owner_id: int,
    account_id: int,
    preview_rows: list[StatementPreviewRow],
) -> list[StatementPreviewRow]:
    existing_keys = get_existing_duplicate_keys(db, owner_id, account_id=account_id)
    existing_statement_matches = get_existing_statement_match_map(db, owner_id, account_id=account_id)
    seen_matched_transaction_ids: set[int] = set()
    annotated_rows: list[StatementPreviewRow] = []

    for row in preview_rows:
        duplicate_reason: str | None = None

        try:
            tx_date = date.fromisoformat(row.date)
            duplicate_key = build_duplicate_key(
                owner_id=owner_id,
                account_id=account_id,
                tx_date=tx_date,
                description=row.description,
                amount=row.amount,
                tx_type=row.type,
                category=row.category,
            )
            statement_match_key = build_statement_match_key(
                owner_id=owner_id,
                account_id=account_id,
                tx_date=tx_date,
                amount=row.amount,
                tx_type=row.type,
            )
        except Exception:
            annotated_rows.append(
                row.model_copy(
                    update={
                        "is_duplicate": False,
                        "duplicate_reason": None,
                        "matched_transaction_id": None,
                        "reconciliation_status": "needs_review",
                        "reconciliation_reason": "Could not compare this row until its date, amount, and type are valid.",
                    }
                )
            )
            continue

        reconciliation_status = "missing"

        if duplicate_key in existing_keys:
            duplicate_reason = "Already written in this account."
            matched_transaction = existing_statement_matches.get(statement_match_key)
        elif statement_match_key in existing_statement_matches:
            matched_transaction = existing_statement_matches[statement_match_key]
            duplicate_reason = f"Already written as {matched_transaction.description}."
        else:
            matched_transaction = find_likely_statement_match(
                db=db,
                owner_id=owner_id,
                account_id=account_id,
                tx_date=tx_date,
                amount=row.amount,
                tx_type=row.type,
            )
            if matched_transaction and matched_transaction.id not in seen_matched_transaction_ids:
                duplicate_reason = describe_likely_statement_match(tx_date, matched_transaction)
            elif matched_transaction:
                matched_transaction = None
                duplicate_reason = "Duplicate of another row in this preview."
            else:
                matched_transaction = None

        if matched_transaction:
            seen_matched_transaction_ids.add(matched_transaction.id)
            reconciliation_status = "matched"
        elif duplicate_reason == "Already written in this account.":
            reconciliation_status = "matched"

        annotated_rows.append(
            row.model_copy(
                update={
                    "is_duplicate": duplicate_reason is not None,
                    "duplicate_reason": duplicate_reason,
                    "matched_transaction_id": matched_transaction.id if matched_transaction else None,
                    "reconciliation_status": reconciliation_status,
                    "reconciliation_reason": duplicate_reason
                    or "Not found in your written transactions yet.",
                }
            )
        )

    return annotated_rows


def detect_import_type(filename: str, content_type: str | None) -> str:
    extension = Path(filename or "").suffix.lower()

    if extension in CSV_EXTENSIONS:
        return "csv_statement"

    if extension in IMAGE_EXTENSIONS:
        return "receipt_image"

    if extension in PDF_EXTENSIONS:
        return "pdf_statement"

    if content_type:
        lowered = content_type.lower()
        if "csv" in lowered:
            return "csv_statement"
        if lowered.startswith("image/"):
            return "receipt_image"
        if "pdf" in lowered:
            return "pdf_statement"

    raise ValueError("Unsupported file type. Use CSV, PDF, JPG, PNG, or WEBP.")


def process_smart_import(
    db: Session,
    owner_id: int,
    account_id: int,
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
) -> dict[str, Any]:
    detected_type = detect_import_type(filename, content_type)

    if detected_type == "csv_statement":
        result = parse_csv_statement_preview(
            db=db,
            owner_id=owner_id,
            file_bytes=file_bytes,
        )
        preview_rows = annotate_preview_rows_for_duplicates(
            db=db,
            owner_id=owner_id,
            account_id=account_id,
            preview_rows=result.get("preview_rows", []),
        )
        return {
            "detected_type": "csv_statement",
            "status": "table_review",
            "message": "CSV statement parsed. Review what is already written and import only the missing rows.",
            "import_summary": {
                "imported": 0,
                "duplicates_skipped": 0,
                "invalid_rows_skipped": result.get("invalid_rows_skipped", 0),
            },
            "preview_rows": preview_rows,
            "notes": [
                "Matched rows are already in your app. Missing rows can be imported after review."
            ],
        }

    if detected_type == "receipt_image":
        result = scan_receipt_file(
            db=db,
            owner_id=owner_id,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
        )
        return {
            "detected_type": "receipt_image",
            "status": "draft_review",
            "message": "Receipt scanned successfully. Review the draft before saving.",
            "draft_transaction": {
                "amount": result.get("amount"),
                "category": result.get("category", "other"),
                "description": result.get("merchant") or "Scanned receipt",
                "date": result.get("date"),
                "type": result.get("type", "expense"),
                "account_id": account_id,
                "confidence": result.get("confidence", 0.0),
                "notes": result.get("notes", []),
            },
            "notes": result.get("notes", []),
        }

    if detected_type == "pdf_statement":
        result = parse_pdf_statement_preview(
            db=db,
            owner_id=owner_id,
            file_bytes=file_bytes,
        )
        preview_rows = annotate_preview_rows_for_duplicates(
            db=db,
            owner_id=owner_id,
            account_id=account_id,
            preview_rows=result.get("preview_rows", []),
        )
        return {
            "detected_type": "pdf_statement",
            "status": "table_review",
            "message": "PDF statement parsed. Review the detected rows before importing.",
            "preview_rows": preview_rows,
            "notes": result.get("notes", []),
        }

    raise ValueError("Unsupported import type")


def add_file_context_to_preview_rows(
    preview_rows: list[StatementPreviewRow],
    filename: str,
) -> list[StatementPreviewRow]:
    rows: list[StatementPreviewRow] = []
    for row in preview_rows:
        source_line = row.source_line or "Detected statement row."
        rows.append(
            row.model_copy(
                update={
                    "source_line": f"{filename}: {source_line}",
                }
            )
        )
    return rows


def process_smart_import_batch(
    db: Session,
    owner_id: int,
    account_id: int,
    files: list[tuple[bytes, str, str | None]],
) -> dict[str, Any]:
    if not files:
        raise ValueError("Select at least one statement file to import.")

    detected_types = [
        detect_import_type(filename, content_type)
        for _, filename, content_type in files
    ]
    if "receipt_image" in detected_types and len(files) > 1:
        raise ValueError(
            "Batch import supports CSV and PDF bank statements. Upload receipt images one at a time."
        )

    imported = 0
    duplicates_skipped = 0
    invalid_rows_skipped = 0
    notes: list[str] = []
    preview_rows: list[StatementPreviewRow] = []
    processed_count = 0

    for file_bytes, filename, content_type in files:
        detected_type = detect_import_type(filename, content_type)
        processed_count += 1

        if detected_type == "csv_statement":
            result = parse_csv_statement_preview(
                db=db,
                owner_id=owner_id,
                file_bytes=file_bytes,
            )
            file_invalid = result.get("invalid_rows_skipped", 0)
            invalid_rows_skipped += file_invalid
            file_rows = result.get("preview_rows", [])
            preview_rows.extend(add_file_context_to_preview_rows(file_rows, filename))
            notes.append(
                f"{filename}: detected {len(file_rows)} row{'' if len(file_rows) == 1 else 's'} for reconciliation, skipped {file_invalid} invalid row"
                f"{'' if file_invalid == 1 else 's'}."
            )
            continue

        if detected_type == "pdf_statement":
            result = parse_pdf_statement_preview(
                db=db,
                owner_id=owner_id,
                file_bytes=file_bytes,
            )
            file_rows = result.get("preview_rows", [])
            preview_rows.extend(add_file_context_to_preview_rows(file_rows, filename))
            notes.append(
                f"{filename}: detected {len(file_rows)} row{'' if len(file_rows) == 1 else 's'} for review."
            )
            notes.extend([f"{filename}: {note}" for note in result.get("notes", [])])
            continue

        raise ValueError("Batch import supports CSV and PDF bank statements.")

    if preview_rows:
        preview_rows = annotate_preview_rows_for_duplicates(
            db=db,
            owner_id=owner_id,
            account_id=account_id,
            preview_rows=preview_rows,
        )
        return {
            "detected_type": "pdf_statement",
            "status": "table_review",
            "message": (
                f"Batch import processed {processed_count} statement file"
                f"{'' if processed_count == 1 else 's'}. Review matched and missing rows before importing."
            ),
            "import_summary": {
                "imported": imported,
                "duplicates_skipped": duplicates_skipped,
                "invalid_rows_skipped": invalid_rows_skipped,
            },
            "preview_rows": preview_rows,
            "notes": notes,
        }

    return {
        "detected_type": "csv_statement",
        "status": "completed",
        "message": (
            f"Batch import completed for {processed_count} statement file"
            f"{'' if processed_count == 1 else 's'}."
        ),
        "import_summary": {
            "imported": imported,
            "duplicates_skipped": duplicates_skipped,
            "invalid_rows_skipped": invalid_rows_skipped,
        },
        "notes": notes,
    }
