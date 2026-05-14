from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Transaction


INCOME_SOURCES = [
    ("salary", "Monthly salary deposit", (2800, 4200)),
    ("freelance", "Freelance project payment", (250, 1200)),
    ("refund", "Refund received", (20, 180)),
]

EXPENSE_PATTERNS = [
    ("rent", ["Apartment rent", "Monthly rent payment"], (1200, 2200), 1),
    ("grocery", ["Walmart grocery", "Costco groceries", "FreshCo supermarket"], (45, 180), 6),
    ("transport", ["Uber ride", "TTC transit reload", "Shell gas station"], (12, 90), 8),
    ("cafe", ["Starbucks coffee", "Tim Hortons coffee", "Cafe drink"], (4, 18), 8),
    ("restaurant", ["McDonald's meal", "Pizza order", "Restaurant dinner"], (12, 65), 6),
    ("internet", ["Rogers internet bill", "Bell internet payment"], (55, 110), 1),
    ("phone", ["Phone bill", "Mobile payment"], (35, 90), 1),
    ("entertainment", ["Netflix subscription", "Spotify subscription", "Cinema ticket"], (10, 45), 3),
    ("shopping", ["Amazon order", "Clothing purchase", "Household item purchase"], (20, 160), 4),
]

SPIKE_PATTERNS = [
    ("shopping", "Large electronics purchase", (350, 1400)),
    ("travel", "Flight booking", (250, 1100)),
    ("medical", "Pharmacy and medical expense", (80, 400)),
]


def random_amount(low: int, high: int) -> float:
    return round(random.uniform(low, high), 2)


def random_day_in_month(year: int, month: int) -> date:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    delta_days = (end - start).days
    return start + timedelta(days=random.randint(0, delta_days))


def previous_months(count: int) -> list[tuple[int, int]]:
    today = date.today()
    months = []
    year = today.year
    month = today.month

    for _ in range(count):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    months.reverse()
    return months


def seed_realistic_transactions(
    db: Session,
    owner_id: int,
    months: int = 6,
    clear_existing: bool = False,
) -> dict:
    if clear_existing:
        db.query(Transaction).filter(Transaction.owner_id == owner_id).delete()
        db.commit()

    month_list = previous_months(months)
    transactions_to_add: list[Transaction] = []

    for year, month in month_list:
        salary_day = min(28, random.randint(25, 28))
        salary_date = date(year, month, salary_day)

        salary_category, salary_desc, salary_range = INCOME_SOURCES[0]
        transactions_to_add.append(
            Transaction(
                owner_id=owner_id,
                amount=random_amount(*salary_range),
                category=salary_category,
                description=salary_desc,
                date=salary_date,
                type="income",
                entry_source="seed",
            )
        )

        if random.random() < 0.35:
            category, desc, amount_range = INCOME_SOURCES[1]
            transactions_to_add.append(
                Transaction(
                    owner_id=owner_id,
                    amount=random_amount(*amount_range),
                    category=category,
                    description=desc,
                    date=random_day_in_month(year, month),
                    type="income",
                    entry_source="seed",
                )
            )

        if random.random() < 0.2:
            category, desc, amount_range = INCOME_SOURCES[2]
            transactions_to_add.append(
                Transaction(
                    owner_id=owner_id,
                    amount=random_amount(*amount_range),
                    category=category,
                    description=desc,
                    date=random_day_in_month(year, month),
                    type="income",
                    entry_source="seed",
                )
            )

        for category, descriptions, amount_range, frequency in EXPENSE_PATTERNS:
            for _ in range(frequency):
                transactions_to_add.append(
                    Transaction(
                        owner_id=owner_id,
                        amount=random_amount(*amount_range),
                        category=category,
                        description=random.choice(descriptions),
                        date=random_day_in_month(year, month),
                        type="expense",
                        entry_source="seed",
                    )
                )

        if random.random() < 0.45:
            spike_category, spike_desc, spike_range = random.choice(SPIKE_PATTERNS)
            transactions_to_add.append(
                Transaction(
                    owner_id=owner_id,
                    amount=random_amount(*spike_range),
                    category=spike_category,
                    description=spike_desc,
                    date=random_day_in_month(year, month),
                    type="expense",
                    entry_source="seed",
                )
            )

        if random.random() < 0.3:
            transactions_to_add.append(
                Transaction(
                    owner_id=owner_id,
                    amount=random_amount(10, 90),
                    category=random.choice(["other", "misc", "uncategorized"]),
                    description=random.choice(
                        [
                            "Unknown store payment",
                            "Card purchase",
                            "Unclear bank transaction",
                            "POS transaction",
                        ]
                    ),
                    date=random_day_in_month(year, month),
                    type="expense",
                    entry_source="seed",
                )
            )

    db.bulk_save_objects(transactions_to_add)
    db.commit()

    return {
        "message": "Realistic seed data created successfully",
        "months_generated": months,
        "transactions_created": len(transactions_to_add),
        "existing_data_cleared": clear_existing,
    }
