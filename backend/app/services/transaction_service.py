from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import CategoryMemory, Transaction


SUPPORTED_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
UNCATEGORIZED_VALUES = {"other", "misc", "uncategorized", "unknown"}

HEADER_ALIASES = {
    "date": {"date", "transaction_date", "posted_date"},
    "description": {"description", "details", "memo", "merchant", "transaction_description"},
    "amount": {"amount", "transaction_amount"},
    "debit": {"debit", "withdrawal", "money_out"},
    "credit": {"credit", "deposit", "money_in"},
    "type": {"type", "transaction_type"},
    "category": {"category"},
}

CATEGORY_RULES = {
    "salary": ["salary", "payroll", "paycheque", "paycheck", "deposit payroll"],
    "rent": ["rent", "lease", "landlord"],
    "groceries": ["grocery", "supermarket", "freshco", "nofrills", "costco", "walmart", "loblaws"],
    "transport": ["uber", "lyft", "ttc", "metro", "gas", "shell", "esso", "petro"],
    "internet": ["internet", "rogers", "bell internet"],
    "phone": ["phone", "mobile", "wireless", "telus", "freedom", "fido"],
    "restaurant": ["restaurant", "pizza", "burger", "shawarma", "mcdonald", "kfc", "subway"],
    "cafe": ["coffee", "cafe", "café", "starbucks", "tim hortons"],
    "entertainment": ["netflix", "spotify", "cinema", "movie", "youtube"],
    "shopping": ["amazon", "shop", "store", "mall", "purchase"],
    "transfer": ["e-transfer", "transfer", "interac"],
    "utilities": ["utility", "utilities", "hydro", "electric", "water", "gas bill"],
    "car maintenance": ["car maintenance", "mechanic", "oil change", "tire", "repair"],
    "personal": ["personal", "pharmacy", "shoppers drug mart", "beauty", "haircut"],
}

CATEGORY_ALIASES = {
    "grocery": "groceries",
    "groceries": "groceries",
    "supermarket": "groceries",
    "transport": "transport",
    "transportation": "transport",
    "cafe": "cafe",
    "café": "cafe",
    "coffee": "cafe",
    "personal": "personal",
    "shopping": "shopping",
    "transfer": "transfer",
    "transfers": "transfer",
    "utilities": "utilities",
    "utility": "utilities",
    "other": "other",
    "misc": "other",
    "miscellaneous": "other",
    "uncategorized": "other",
    "unknown": "other",
    "restaurant": "restaurant",
    "restaurants": "restaurant",
    "salary": "salary",
    "income": "income",
    "refund": "refund",
    "rent": "rent",
    "internet": "internet",
    "phone": "phone",
    "entertainment": "entertainment",
    "car maintenance": "car maintenance",
    "car_maintenance": "car maintenance",
}


def decode_file_bytes(file_bytes: bytes) -> str:
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode file. Supported encodings failed.")


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower().replace(" ", "_")).strip("_")


def parse_date(value: str) -> date:
    value = value.strip()

    date_formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%d-%m-%Y",
        "%b %d, %Y",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Invalid date format: {value}")


def parse_amount(value: str) -> float:
    cleaned = value.replace(",", "").replace("$", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return float(cleaned)


def normalize_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"income", "credit", "deposit"}:
        return "income"
    if normalized in {"expense", "debit", "withdrawal"}:
        return "expense"
    raise ValueError(f"Invalid transaction type: {value}")


def normalize_category_name(value: str | None) -> str:
    if not value:
        return "other"

    cleaned = value.strip().lower()
    cleaned = cleaned.replace("&", "and")
    cleaned = re.sub(r"[_\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return "other"

    if cleaned in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cleaned]

    singular_map = {
        "restaurants": "restaurant",
        "transfers": "transfer",
        "utilities": "utilities",
        "groceries": "groceries",
    }
    if cleaned in singular_map:
        return singular_map[cleaned]

    return cleaned


def sniff_csv_dialect(text: str) -> csv.Dialect:
    sample = text[:5000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;|\t")
    except csv.Error:
        return csv.get_dialect("excel")


def resolve_header_mapping(fieldnames: list[str]) -> dict[str, str]:
    normalized = [normalize_header(name) for name in fieldnames]
    mapping: dict[str, str] = {}

    for canonical, aliases in HEADER_ALIASES.items():
        for header in normalized:
            if header in aliases:
                mapping[canonical] = header
                break

    if not mapping.get("date") or not mapping.get("description"):
        raise ValueError("Statement must include at least date and description columns.")

    if not (
        mapping.get("amount")
        or (mapping.get("debit") and mapping.get("credit"))
        or mapping.get("type")
    ):
        raise ValueError("Statement must include amount, or debit/credit columns.")

    return mapping


def read_csv_rows(text: str) -> tuple[list[dict], dict[str, str]]:
    dialect = sniff_csv_dialect(text)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    if not reader.fieldnames:
        raise ValueError("CSV file is missing headers.")

    normalized_headers = [normalize_header(field) for field in reader.fieldnames]
    reader.fieldnames = normalized_headers
    header_mapping = resolve_header_mapping(normalized_headers)

    rows = []
    for row in reader:
        normalized_row = {normalize_header(k): (v or "").strip() for k, v in row.items()}
        rows.append(normalized_row)

    return rows, header_mapping


def infer_type_and_amount(row: dict, header_mapping: dict[str, str]) -> tuple[str, float]:
    amount_key = header_mapping.get("amount")
    debit_key = header_mapping.get("debit")
    credit_key = header_mapping.get("credit")
    type_key = header_mapping.get("type")

    if amount_key:
        amount = parse_amount(row.get(amount_key, "0"))
        if type_key and row.get(type_key):
            tx_type = normalize_type(row[type_key])
            return tx_type, abs(amount)

        if amount < 0:
            return "expense", abs(amount)
        return "income", abs(amount)

    debit_value = row.get(debit_key, "") if debit_key else ""
    credit_value = row.get(credit_key, "") if credit_key else ""

    if debit_value:
        return "expense", abs(parse_amount(debit_value))
    if credit_value:
        return "income", abs(parse_amount(credit_value))

    raise ValueError("Could not infer transaction amount/type.")


def normalize_description(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(r"\bpos\b|\bpurchase\b|\bpayment\b|\bdebit\b|\bcredit\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text or value.strip()


def learnable_category_from_memory(db: Session, owner_id: int, description: str, tx_type: str) -> str | None:
    lowered = description.lower()

    memories = (
        db.query(CategoryMemory)
        .filter(
            CategoryMemory.owner_id == owner_id,
            CategoryMemory.transaction_type == tx_type,
        )
        .all()
    )

    best_match = None
    for item in memories:
        keyword = item.keyword.lower().strip()
        if keyword and keyword in lowered:
            if best_match is None or len(keyword) > len(best_match[0]):
                best_match = (keyword, item.category)

    return normalize_category_name(best_match[1]) if best_match else None


def categorize_transaction(db: Session, owner_id: int, description: str, tx_type: str) -> str:
    memory_category = learnable_category_from_memory(db, owner_id, description, tx_type)
    if memory_category:
        return memory_category

    lowered = description.lower()

    if tx_type == "income":
        for keyword in CATEGORY_RULES["salary"]:
            if keyword in lowered:
                return "salary"
        if "refund" in lowered:
            return "refund"
        return "income"

    for category, keywords in CATEGORY_RULES.items():
        if category == "salary":
            continue
        for keyword in keywords:
            if keyword in lowered:
                return normalize_category_name(category)

    return "other"


def build_duplicate_key(
    owner_id: int,
    account_id: int,
    tx_date: date,
    description: str,
    amount: float,
    tx_type: str,
    category: str,
) -> tuple:
    return (
        owner_id,
        account_id,
        tx_date.isoformat(),
        description.strip().lower(),
        round(amount, 2),
        tx_type.strip().lower(),
        normalize_category_name(category),
    )


def get_existing_duplicate_keys(db: Session, owner_id: int, account_id: int | None = None) -> set[tuple]:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    existing_transactions = query.all()

    return {
        build_duplicate_key(
            owner_id=transaction.owner_id,
            account_id=transaction.account_id or 0,
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
    account_id: int,
    file_bytes: bytes,
) -> dict:
    text = decode_file_bytes(file_bytes)
    rows, header_mapping = read_csv_rows(text)

    existing_keys = get_existing_duplicate_keys(db, owner_id, account_id=account_id)
    seen_in_file = set()

    to_insert: list[Transaction] = []
    imported = 0
    duplicates_skipped = 0
    invalid_rows_skipped = 0

    for row in rows:
        try:
            tx_date = parse_date(row[header_mapping["date"]])
            raw_description = row[header_mapping["description"]]
            description = normalize_description(raw_description)

            tx_type, amount = infer_type_and_amount(row, header_mapping)

            if header_mapping.get("category") and row.get(header_mapping["category"]):
                category = normalize_category_name(row[header_mapping["category"]])
            else:
                category = categorize_transaction(db, owner_id, description, tx_type)

            if not description or not category:
                raise ValueError("Description and category are required.")

            duplicate_key = build_duplicate_key(
                owner_id=owner_id,
                account_id=account_id,
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
                    account_id=account_id,
                )
            )
            imported += 1

        except Exception:
            invalid_rows_skipped += 1

    if to_insert:
        db.bulk_save_objects(to_insert)
        db.commit()

    return {
        "message": "Statement import completed",
        "imported": imported,
        "duplicates_skipped": duplicates_skipped,
        "invalid_rows_skipped": invalid_rows_skipped,
    }


def get_transactions_for_user(db: Session, owner_id: int, account_id: int | None = None) -> list[Transaction]:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()


def get_uncategorized_candidates(db: Session, owner_id: int, account_id: int | None = None) -> list[Transaction]:
    query = (
        db.query(Transaction)
        .filter(Transaction.owner_id == owner_id)
        .filter(Transaction.category.in_(UNCATEGORIZED_VALUES))
    )

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    return query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()


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
        new_category = normalize_category_name(suggested_category_map.get(transaction.id))
        if new_category and transaction.category != new_category:
            transaction.category = new_category
            updated_count += 1

    if updated_count > 0:
        db.commit()

    return updated_count


def normalize_existing_categories_for_user(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> dict:
    query = db.query(Transaction).filter(Transaction.owner_id == owner_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    transactions = query.all()

    updated_count = 0
    changes: dict[str, str] = {}

    for transaction in transactions:
        old_category = transaction.category or "other"
        new_category = normalize_category_name(old_category)

        if old_category != new_category:
            transaction.category = new_category
            updated_count += 1
            if old_category not in changes:
                changes[old_category] = new_category

    if updated_count > 0:
        db.commit()

    return {
        "updated_count": updated_count,
        "changes": changes,
    }