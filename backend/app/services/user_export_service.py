from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AssistantChatMessage,
    AssistantLearningExample,
    AssistantUsageEvent,
    BudgetPlan,
    CategoryLearningEvent,
    CategoryMemory,
    MerchantCategoryProfile,
    SavedScenario,
    Transaction,
    User,
    UserLearningPreference,
)


SENSITIVE_USER_FIELDS = {
    "password_hash",
    "reset_token_hash",
    "reset_token_expires_at",
}


EXPORT_MODEL_GROUPS = (
    ("accounts", Account),
    ("transactions", Transaction),
    ("category_memories", CategoryMemory),
    ("merchant_category_profiles", MerchantCategoryProfile),
    ("user_learning_preferences", UserLearningPreference),
    ("assistant_chat_messages", AssistantChatMessage),
    ("assistant_usage_events", AssistantUsageEvent),
    ("assistant_learning_examples", AssistantLearningExample),
    ("category_learning_events", CategoryLearningEvent),
    ("budget_plans", BudgetPlan),
    ("saved_scenarios", SavedScenario),
)


def serialize_export_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def serialize_model(instance: object, *, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded_fields = exclude or set()
    mapper = inspect(instance).mapper
    return {
        column.key: serialize_export_value(getattr(instance, column.key))
        for column in mapper.column_attrs
        if column.key not in excluded_fields
    }


def owner_rows(db: Session, model: type, owner_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(model)
        .filter(model.owner_id == owner_id)
        .order_by(model.id.asc())
        .all()
    )
    return [serialize_model(row) for row in rows]


def build_user_data_export(db: Session, user: User) -> dict[str, Any]:
    exported_at = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "exported_at": exported_at,
        "user": serialize_model(user, exclude=SENSITIVE_USER_FIELDS),
        "excluded": [
            "Password hashes are not exported.",
            "Password reset token hashes and reset expiry timestamps are not exported.",
            "Shared merchant lookup cache rows are not exported because they are not user-owned rows.",
            "Provider logs, backups, and third-party records are not included in this app-level export.",
        ],
    }

    for key, model in EXPORT_MODEL_GROUPS:
        payload[key] = owner_rows(db, model, user.id)

    return payload
