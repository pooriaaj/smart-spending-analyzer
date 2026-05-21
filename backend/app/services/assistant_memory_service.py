from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AssistantChatMessage, AssistantUsageEvent
from app.security import redact_sensitive_text

ASSISTANT_MESSAGE_MAX_CHARS = 1800
ASSISTANT_HISTORY_DEFAULT_LIMIT = 30
ASSISTANT_HISTORY_MAX_STORED_PER_SCOPE = 120


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def assistant_daily_llm_limit() -> int:
    return _bounded_int_env("ASSISTANT_DAILY_LLM_LIMIT", 100, 1, 5000)


def _scope_filter(query, account_id: int | None):
    if account_id is None:
        return query.filter(AssistantChatMessage.account_id.is_(None))
    return query.filter(AssistantChatMessage.account_id == account_id)


def clean_assistant_message(value: Any, *, limit: int = ASSISTANT_MESSAGE_MAX_CHARS) -> str:
    text = redact_sensitive_text(str(value or ""))
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return f"{text[:limit].rstrip()}..."
    return text


def get_recent_assistant_messages(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None = None,
    limit: int = ASSISTANT_HISTORY_DEFAULT_LIMIT,
) -> list[AssistantChatMessage]:
    safe_limit = max(1, min(int(limit or ASSISTANT_HISTORY_DEFAULT_LIMIT), 100))
    query = db.query(AssistantChatMessage).filter(AssistantChatMessage.owner_id == owner_id)
    query = _scope_filter(query, account_id)
    messages = (
        query.order_by(AssistantChatMessage.created_at.desc(), AssistantChatMessage.id.desc())
        .limit(safe_limit)
        .all()
    )
    return list(reversed(messages))


def get_recent_assistant_history_payload(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None = None,
    limit: int = 8,
) -> list[dict[str, str]]:
    return [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in get_recent_assistant_messages(
            db,
            owner_id,
            account_id=account_id,
            limit=limit,
        )
        if message.role in {"user", "assistant"} and message.content
    ]


def save_assistant_exchange(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None,
    mode: str,
    scope_label: str,
    question: str,
    answer: str,
) -> None:
    user_content = clean_assistant_message(question, limit=1200)
    assistant_content = clean_assistant_message(answer)
    if not user_content or not assistant_content:
        return

    db.add_all(
        [
            AssistantChatMessage(
                role="user",
                content=user_content,
                mode=mode,
                scope_label=scope_label[:160],
                owner_id=owner_id,
                account_id=account_id,
            ),
            AssistantChatMessage(
                role="assistant",
                content=assistant_content,
                mode=mode,
                scope_label=scope_label[:160],
                owner_id=owner_id,
                account_id=account_id,
            ),
        ]
    )
    db.flush()
    trim_assistant_history(db, owner_id, account_id=account_id)


def trim_assistant_history(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None = None,
    max_messages: int = ASSISTANT_HISTORY_MAX_STORED_PER_SCOPE,
) -> int:
    query = db.query(AssistantChatMessage).filter(AssistantChatMessage.owner_id == owner_id)
    query = _scope_filter(query, account_id)
    keep_ids = [
        item.id
        for item in query.order_by(AssistantChatMessage.created_at.desc(), AssistantChatMessage.id.desc())
        .limit(max_messages)
        .all()
    ]
    if not keep_ids:
        return 0

    delete_query = db.query(AssistantChatMessage).filter(
        AssistantChatMessage.owner_id == owner_id,
        ~AssistantChatMessage.id.in_(keep_ids),
    )
    delete_query = _scope_filter(delete_query, account_id)
    deleted_count = delete_query.delete(synchronize_session=False)
    return int(deleted_count or 0)


def clear_assistant_history(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None = None,
) -> int:
    query = db.query(AssistantChatMessage).filter(AssistantChatMessage.owner_id == owner_id)
    query = _scope_filter(query, account_id)
    deleted_count = query.delete(synchronize_session=False)
    return int(deleted_count or 0)


def assistant_usage_window_start() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=24)


def get_assistant_usage_status(db: Session, owner_id: int) -> dict[str, int]:
    limit = assistant_daily_llm_limit()
    used = (
        db.query(AssistantUsageEvent)
        .filter(
            AssistantUsageEvent.owner_id == owner_id,
            AssistantUsageEvent.created_at >= assistant_usage_window_start(),
        )
        .count()
    )
    remaining = max(0, limit - int(used or 0))
    return {
        "daily_limit": limit,
        "daily_used": int(used or 0),
        "daily_remaining": remaining,
    }


def assistant_llm_usage_allowed(db: Session, owner_id: int) -> bool:
    return get_assistant_usage_status(db, owner_id)["daily_remaining"] > 0


def record_assistant_usage_event(
    db: Session,
    owner_id: int,
    *,
    provider: str,
    request_chars: int,
    response_chars: int,
) -> None:
    db.add(
        AssistantUsageEvent(
            provider=(provider or "unknown")[:40],
            request_chars=max(0, int(request_chars or 0)),
            response_chars=max(0, int(response_chars or 0)),
            owner_id=owner_id,
        )
    )
    db.flush()
