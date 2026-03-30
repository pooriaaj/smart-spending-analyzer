from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_user
from app.models import Transaction, User, CategoryMemory
from app.schemas import (
    TransactionCreate,
    TransactionResponse,
    CategorySuggestionRequest,
    CategorySuggestionResponse,
    BulkCategorySuggestionItem,
    BulkCategorySuggestionResponse,
    BulkCategoryApplyRequest,
    BulkCategoryApplyResponse,
)
import csv
import io
from datetime import datetime

router = APIRouter(prefix="/transactions", tags=["Transactions"])


def normalize_text(value: str) -> str:
    return (value or "").strip().lower()


CATEGORY_KEYWORDS = {
    "expense": {
        "Groceries": [
            "walmart", "costco", "metro", "loblaws", "nofrills", "superstore",
            "freshco", "grocery", "groceries", "market", "food basics"
        ],
        "Transport": [
            "uber", "lyft", "ttc", "presto", "gas", "fuel", "shell", "esso",
            "petro", "transit", "bus", "train", "subway", "taxi", "parking"
        ],
        "Rent": [
            "rent", "landlord", "lease"
        ],
        "Utilities": [
            "hydro", "electric", "electricity", "water", "internet", "wifi",
            "rogers", "bell", "fido", "telus", "utility", "utilities", "phone bill"
        ],
        "Dining": [
            "restaurant", "cafe", "coffee", "starbucks", "tim hortons",
            "mcdonald", "burger", "pizza", "shawarma", "eat", "dinner", "lunch"
        ],
        "Entertainment": [
            "netflix", "spotify", "youtube", "cinema", "movie", "game",
            "steam", "playstation", "xbox", "entertainment"
        ],
        "Shopping": [
            "amazon", "mall", "store", "clothes", "clothing", "shoes",
            "zara", "h&m", "uniqlo", "shopping"
        ],
        "Health": [
            "pharmacy", "shoppers", "medicine", "doctor", "clinic",
            "hospital", "health", "dental", "dentist"
        ],
        "Education": [
            "tuition", "course", "udemy", "coursera", "book", "books",
            "university", "college", "education"
        ],
        "Travel": [
            "airbnb", "hotel", "flight", "air canada", "porter", "westjet",
            "travel", "vacation"
        ],
        "Subscriptions": [
            "subscription", "monthly plan", "icloud", "google one", "prime",
            "adobe", "notion"
        ],
        "Other": []
    },
    "income": {
        "Salary": [
            "salary", "payroll", "pay cheque", "paycheck", "wage", "income"
        ],
        "Freelance": [
            "freelance", "contract", "client payment", "project payment"
        ],
        "Refund": [
            "refund", "reversal", "returned"
        ],
        "Gift": [
            "gift", "etransfer", "e-transfer", "transfer from friend"
        ],
        "Investment": [
            "dividend", "interest", "investment", "capital gain"
        ],
        "Other Income": []
    }
}


def extract_memory_keyword(description: str) -> str | None:
    words = normalize_text(description).split()
    words = [word for word in words if len(word) >= 3]
    if not words:
        return None
    return words[0]


def suggest_category(description: str, transaction_type: str, db: Session, current_user: User):
    normalized_description = normalize_text(description)
    normalized_type = normalize_text(transaction_type)

    if normalized_type not in CATEGORY_KEYWORDS:
        return {
            "suggested_category": "Other",
            "confidence": 0.20,
            "matched_keyword": None,
            "reason": "Unknown transaction type"
        }

    memory_matches = db.query(CategoryMemory).filter(
        CategoryMemory.owner_id == current_user.id,
        CategoryMemory.transaction_type == normalized_type
    ).all()

    for memory in memory_matches:
        if memory.keyword in normalized_description:
            return {
                "suggested_category": memory.category,
                "confidence": 0.98,
                "matched_keyword": memory.keyword,
                "reason": f"Matched your saved preference for '{memory.keyword}'"
            }

    for category, keywords in CATEGORY_KEYWORDS[normalized_type].items():
        for keyword in keywords:
            if keyword in normalized_description:
                return {
                    "suggested_category": category,
                    "confidence": 0.92,
                    "matched_keyword": keyword,
                    "reason": f"Matched keyword '{keyword}' in description"
                }

    fallback_category = "Other" if normalized_type == "expense" else "Other Income"

    return {
        "suggested_category": fallback_category,
        "confidence": 0.35,
        "matched_keyword": None,
        "reason": "No rule matched, used fallback category"
    }


def save_category_memory(description: str, transaction_type: str, category: str, db: Session, current_user: User):
    keyword = extract_memory_keyword(description)
    if not keyword:
        return

    existing_memory = db.query(CategoryMemory).filter(
        CategoryMemory.owner_id == current_user.id,
        CategoryMemory.keyword == keyword,
        CategoryMemory.transaction_type == normalize_text(transaction_type)
    ).first()

    if existing_memory:
        existing_memory.category = category
    else:
        db.add(
            CategoryMemory(
                keyword=keyword,
                category=category,
                transaction_type=normalize_text(transaction_type),
                owner_id=current_user.id
            )
        )


def filter_transactions(
    transactions,
    month: str | None,
    start_date: str | None,
    end_date: str | None,
    transaction_type: str | None,
    category: str | None
):
    result = transactions

    if month:
        result = [
            transaction
            for transaction in result
            if transaction.date.strftime("%Y-%m") == month
        ]

    if start_date:
        start = datetime.fromisoformat(start_date).date()
        result = [
            transaction
            for transaction in result
            if transaction.date >= start
        ]

    if end_date:
        end = datetime.fromisoformat(end_date).date()
        result = [
            transaction
            for transaction in result
            if transaction.date <= end
        ]

    if transaction_type:
        result = [
            transaction
            for transaction in result
            if transaction.type == transaction_type
        ]

    if category:
        result = [
            transaction
            for transaction in result
            if transaction.category == category
        ]

    return result


@router.post("/", response_model=TransactionResponse)
def create_transaction(
    transaction_data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transaction = Transaction(
        amount=transaction_data.amount,
        category=transaction_data.category,
        description=transaction_data.description,
        date=transaction_data.date,
        type=transaction_data.type,
        owner_id=current_user.id
    )
    db.add(transaction)

    save_category_memory(
        description=transaction_data.description,
        transaction_type=transaction_data.type,
        category=transaction_data.category,
        db=db,
        current_user=current_user
    )

    db.commit()
    db.refresh(transaction)
    return transaction


@router.post("/categorize/suggest", response_model=CategorySuggestionResponse)
def categorize_transaction_suggestion(
    payload: CategorySuggestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = suggest_category(payload.description, payload.type, db, current_user)
    return CategorySuggestionResponse(**result)


@router.get("/categorize/bulk-preview", response_model=BulkCategorySuggestionResponse)
def categorize_bulk_preview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    candidate_categories = {"other", "misc", "uncategorized", "unknown"}

    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    suggestions = []

    for transaction in transactions:
        current_category = normalize_text(transaction.category)

        if current_category not in candidate_categories:
            continue

        result = suggest_category(transaction.description, transaction.type, db, current_user)

        if result["suggested_category"].lower() == current_category:
            continue

        suggestions.append(
            BulkCategorySuggestionItem(
                transaction_id=transaction.id,
                current_category=transaction.category,
                description=transaction.description,
                type=transaction.type,
                suggested_category=result["suggested_category"],
                confidence=result["confidence"],
                matched_keyword=result["matched_keyword"],
                reason=result["reason"],
            )
        )

    return BulkCategorySuggestionResponse(
        total_candidates=len(suggestions),
        suggestions=suggestions
    )


@router.post("/categorize/bulk-apply", response_model=BulkCategoryApplyResponse)
def categorize_bulk_apply(
    payload: BulkCategoryApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    updated_count = 0

    for transaction_id in payload.transaction_ids:
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.owner_id == current_user.id
        ).first()

        if not transaction:
            continue

        result = suggest_category(transaction.description, transaction.type, db, current_user)
        transaction.category = result["suggested_category"]

        save_category_memory(
            description=transaction.description,
            transaction_type=transaction.type,
            category=transaction.category,
            db=db,
            current_user=current_user
        )

        updated_count += 1

    db.commit()

    return BulkCategoryApplyResponse(updated_count=updated_count)


@router.get("/", response_model=list[TransactionResponse])
def get_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Transaction).filter(Transaction.owner_id == current_user.id).all()


@router.post("/seed-dummy")
def seed_dummy_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from datetime import date

    dummy_data = [
        Transaction(
            amount=3200.00,
            category="Salary",
            description="Monthly salary",
            date=date(2026, 3, 1),
            type="income",
            owner_id=current_user.id
        ),
        Transaction(
            amount=120.50,
            category="Groceries",
            description="Walmart groceries",
            date=date(2026, 3, 3),
            type="expense",
            owner_id=current_user.id
        ),
        Transaction(
            amount=65.00,
            category="Transport",
            description="Monthly transit pass",
            date=date(2026, 3, 5),
            type="expense",
            owner_id=current_user.id
        ),
        Transaction(
            amount=950.00,
            category="Rent",
            description="Monthly rent payment",
            date=date(2026, 3, 2),
            type="expense",
            owner_id=current_user.id
        )
    ]

    db.add_all(dummy_data)
    db.commit()

    return {"message": "Dummy transactions added successfully"}


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.owner_id == current_user.id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(transaction)
    db.commit()

    return {"message": "Transaction deleted successfully"}


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    transaction_data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.owner_id == current_user.id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction.amount = transaction_data.amount
    transaction.category = transaction_data.category
    transaction.description = transaction_data.description
    transaction.date = transaction_data.date
    transaction.type = transaction_data.type

    save_category_memory(
        description=transaction_data.description,
        transaction_type=transaction_data.type,
        category=transaction_data.category,
        db=db,
        current_user=current_user
    )

    db.commit()
    db.refresh(transaction)

    return transaction


@router.get("/export/csv")
def export_transactions_csv(
    month: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transactions = db.query(Transaction).filter(
        Transaction.owner_id == current_user.id
    ).all()

    transactions = filter_transactions(
        transactions,
        month,
        start_date,
        end_date,
        transaction_type,
        category
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Date", "Type", "Category", "Description", "Amount"])

    for transaction in sorted(transactions, key=lambda t: t.date, reverse=True):
        writer.writerow([
            transaction.id,
            transaction.date,
            transaction.type,
            transaction.category,
            transaction.description,
            transaction.amount
        ])

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=transactions_export.csv"
        }
    )


@router.post("/import/csv")
async def import_transactions_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    try:
        content = await file.read()

        decoded_content = None
        for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin-1"]:
            try:
                decoded_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if decoded_content is None:
            raise HTTPException(
                status_code=400,
                detail="Could not read CSV file encoding"
            )

        sample = decoded_content[:2048]

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except Exception:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(decoded_content), dialect=dialect)

        if not reader.fieldnames:
            raise HTTPException(
                status_code=400,
                detail="CSV file is missing headers"
            )

        normalized_fieldnames = [field.strip().lower() for field in reader.fieldnames]
        reader.fieldnames = normalized_fieldnames

        required_columns = {"date", "description", "amount", "type", "category"}
        if not required_columns.issubset(set(reader.fieldnames)):
            raise HTTPException(
                status_code=400,
                detail=f"CSV headers found: {reader.fieldnames}. Required: date, description, amount, type, category"
            )

        imported_count = 0
        duplicate_count = 0
        invalid_count = 0

        for row in reader:
            try:
                normalized_row = {
                    key.strip().lower(): (value.strip() if value else "")
                    for key, value in row.items()
                }

                transaction_type = normalized_row["type"].lower()
                if transaction_type not in ["income", "expense"]:
                    invalid_count += 1
                    continue

                amount = float(normalized_row["amount"])
                category = normalized_row["category"]
                description = normalized_row["description"]
                date_value = datetime.strptime(
                    normalized_row["date"], "%Y-%m-%d"
                ).date()

                existing_transaction = db.query(Transaction).filter(
                    Transaction.owner_id == current_user.id,
                    Transaction.amount == amount,
                    Transaction.category == category,
                    Transaction.description == description,
                    Transaction.date == date_value,
                    Transaction.type == transaction_type
                ).first()

                if existing_transaction:
                    duplicate_count += 1
                    continue

                transaction = Transaction(
                    amount=amount,
                    category=category,
                    description=description,
                    date=date_value,
                    type=transaction_type,
                    owner_id=current_user.id
                )

                db.add(transaction)
                imported_count += 1

            except Exception:
                invalid_count += 1
                continue

        db.commit()

        return {
            "message": "CSV import completed",
            "imported": imported_count,
            "duplicates_skipped": duplicate_count,
            "invalid_rows_skipped": invalid_count
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CSV import failed: {str(e)}"
        )