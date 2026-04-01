from __future__ import annotations

import csv
import io
from datetime import datetime, date
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Transaction


SUPPORTED_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
REQUIRED_COLUMNS = {"date", "description", "amount", "type", "category"}
UNCATEGORIZED_VALUES = {"other", "misc", "uncategorized", "unknown"}


def decode_file_bytes(file_bytes: bytes) -> str:
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode file. Supported encodings failed.")


def normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def parse_date(value: str) -> date:
    value = value.strip()

    date_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%d-%m-%Y",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Invalid date format: {value}")


def parse_amount(value: str) -> float:
    cleaned = value.replace(",", "").replace("$", "").strip()
    return float(cleaned)


def normalize_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"income", "expense"}:
        raise ValueError(f"Invalid transaction type: {value}")
    return normalized


def sniff_csv_dialect(text: str) -> csv.Dialect:
    sample = text[:5000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;|\t")
    except csv.Error:
        return csv.get_dialect("excel")


def read_csv_rows(text: str) -> list[dict]:
    dialect = sniff_csv_dialect(text)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    if not reader.fieldnames:
        raise ValueError("CSV file is missing headers.")

    normalized_headers = [normalize_header(field) for field in reader.fieldnames]
    reader.fieldnames = normalized_headers

    missing = REQUIRED_COLUMNS - set(normalized_headers)
    if missing:
        raise ValueError(
            f"CSV must contain: {', '.join(sorted(REQUIRED_COLUMNS))}"
        )

    rows = []
    for row in reader:
        normalized_row = {normalize_header(k): (v or "").strip() for k, v in row.items()}
        rows.append(normalized_row)

    return rows


def build_duplicate_key(
    owner_id: int,
    tx_date: date,
    description: str,
    amount: float,
    tx_type: str,
    category: str,
) -> tuple:
    return (
        owner_id,
        tx_date.isoformat(),
        description.strip().lower(),
        round(amount, 2),
        tx_type.strip().lower(),
        category.strip().lower(),
    )


def get_existing_duplicate_keys(db: Session, owner_id: int) -> set[tuple]:
    existing_transactions = (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id)
        .all()
    )

    return {
        build_duplicate_key(
            owner_id=transaction.owner_id,
            tx_date=transaction.date,
            description=transaction.description,
            amount=transaction.amount,
            tx_type=transaction.type,
            category=transaction.category,
        )
        for transaction in existing_transactions
    }


def import_transactions_from_csv(
    db: Session,
    owner_id: int,
    file_bytes: bytes,
) -> dict:
    text = decode_file_bytes(file_bytes)
    rows = read_csv_rows(text)

    existing_keys = get_existing_duplicate_keys(db, owner_id)
    seen_in_file = set()

    to_insert: list[Transaction] = []
    imported = 0
    duplicates_skipped = 0
    invalid_rows_skipped = 0

    for row in rows:
        try:
            tx_date = parse_date(row["date"])
            description = row["description"].strip()
            amount = parse_amount(row["amount"])
            tx_type = normalize_type(row["type"])
            category = row["category"].strip()

            if not description or not category:
                raise ValueError("Description and category are required.")

            duplicate_key = build_duplicate_key(
                owner_id=owner_id,
                tx_date=tx_date,
                description=description,
                amount=amount,
                tx_type=tx_type,
                category=category,
            )

            if duplicate_key in existing_keys or duplicate_key in seen_in_file:
                duplicates_skipped += 1
                continue

            seen_in_file.add(duplicate_key)

            to_insert.append(
                Transaction(
                    amount=amount,
                    category=category,
                    description=description,
                    date=tx_date,
                    type=tx_type,
                    owner_id=owner_id,
                )
            )
            imported += 1

        except Exception:
            invalid_rows_skipped += 1

    if to_insert:
        db.bulk_save_objects(to_insert)
        db.commit()

    return {
        "message": "CSV import completed",
        "imported": imported,
        "duplicates_skipped": duplicates_skipped,
        "invalid_rows_skipped": invalid_rows_skipped,
    }


def get_transactions_for_user(db: Session, owner_id: int) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )


def get_uncategorized_candidates(db: Session, owner_id: int) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id)
        .filter(Transaction.category.in_(UNCATEGORIZED_VALUES))
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )


def apply_bulk_categories(
    db: Session,
    owner_id: int,
    transaction_ids: Iterable[int],
    suggested_category_map: dict[int, str],
) -> int:
    updated_count = 0

    transactions = (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id, Transaction.id.in_(list(transaction_ids)))
        .all()
    )

    for transaction in transactions:
        new_category = suggested_category_map.get(transaction.id)
        if new_category and transaction.category != new_category:
            transaction.category = new_category
            updated_count += 1

    if updated_count > 0:
        db.commit()

    return updated_count