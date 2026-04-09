from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.schemas import StatementPreviewRow
from app.services.pdf_statement_service import parse_pdf_statement_preview
from app.services.receipt_service import scan_receipt_file
from app.services.transaction_service import (
    build_duplicate_key,
    get_existing_duplicate_keys,
    import_transactions_from_csv,
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
    seen_in_preview: set[tuple] = set()
    annotated_rows: list[StatementPreviewRow] = []

    for row in preview_rows:
        duplicate_reason: str | None = None

        try:
            duplicate_key = build_duplicate_key(
                owner_id=owner_id,
                account_id=account_id,
                tx_date=date.fromisoformat(row.date),
                description=row.description,
                amount=row.amount,
                tx_type=row.type,
                category=row.category,
            )
        except Exception:
            annotated_rows.append(
                row.model_copy(
                    update={
                        "is_duplicate": False,
                        "duplicate_reason": None,
                    }
                )
            )
            continue

        if duplicate_key in existing_keys:
            duplicate_reason = "Already exists in this account."
        elif duplicate_key in seen_in_preview:
            duplicate_reason = "Duplicate of another row in this preview."

        seen_in_preview.add(duplicate_key)
        annotated_rows.append(
            row.model_copy(
                update={
                    "is_duplicate": duplicate_reason is not None,
                    "duplicate_reason": duplicate_reason,
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
        result = import_transactions_from_csv(
            db=db,
            owner_id=owner_id,
            account_id=account_id,
            file_bytes=file_bytes,
        )
        return {
            "detected_type": "csv_statement",
            "status": "completed",
            "message": result["message"],
            "import_summary": {
                "imported": result.get("imported", 0),
                "duplicates_skipped": result.get("duplicates_skipped", 0),
                "invalid_rows_skipped": result.get("invalid_rows_skipped", 0),
            },
            "notes": [],
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
