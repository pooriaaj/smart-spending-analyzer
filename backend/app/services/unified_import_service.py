from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.pdf_statement_service import parse_pdf_statement_preview
from app.services.receipt_service import scan_receipt_file
from app.services.transaction_service import import_transactions_from_csv


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CSV_EXTENSIONS = {".csv"}
PDF_EXTENSIONS = {".pdf"}


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
        return {
            "detected_type": "pdf_statement",
            "status": "table_review",
            "message": "PDF statement parsed. Review the detected rows before importing.",
            "preview_rows": result.get("preview_rows", []),
            "notes": result.get("notes", []),
        }

    raise ValueError("Unsupported import type")