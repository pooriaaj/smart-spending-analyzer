from __future__ import annotations

import os
import re
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AssistantChatMessage, AssistantLearningExample, AssistantUsageEvent
from app.security import redact_sensitive_text

ASSISTANT_MESSAGE_MAX_CHARS = 1800
ASSISTANT_HISTORY_DEFAULT_LIMIT = 30
ASSISTANT_HISTORY_MAX_STORED_PER_SCOPE = 120
ASSISTANT_LEARNING_DEFAULT_LIMIT = 50
ASSISTANT_LEARNING_EXPORT_MAX_LIMIT = 500
ASSISTANT_LEARNING_CONTEXT_MAX_CHARS = 1400


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def assistant_daily_llm_limit() -> int:
    return _bounded_int_env("ASSISTANT_DAILY_LLM_LIMIT", 100, 1, 5000)


def assistant_daily_llm_char_limit() -> int:
    return _bounded_int_env("ASSISTANT_DAILY_LLM_CHAR_LIMIT", 150_000, 1_000, 5_000_000)


def assistant_learning_max_examples_per_user() -> int:
    return _bounded_int_env("ASSISTANT_LEARNING_MAX_EXAMPLES_PER_USER", 2000, 100, 50_000)


def _scope_filter(query, account_id: int | None):
    if account_id is None:
        return query.filter(AssistantChatMessage.account_id.is_(None))
    return query.filter(AssistantChatMessage.account_id == account_id)


def _learning_scope_filter(query, account_id: int | None):
    if account_id is None:
        return query
    return query.filter(AssistantLearningExample.account_id == account_id)


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


def infer_assistant_learning_intent(question: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(question or "")).lower()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "general"
    if any(
        marker in text
        for marker in (
            "api_key",
            "apikey",
            "secret",
            "token",
            "password",
            "database_url",
            "jwt",
            "bearer ",
        )
    ):
        return "security_refusal"

    keyword_groups = (
        ("budget", ("budget", "over budget", "under budget", "target", "monthly limit")),
        ("transactions", ("transaction", "spending", "expense", "income", "merchant", "purchase", "charge")),
        ("statement_import", ("statement", "upload", "csv", "pdf", "import", "bank file")),
        ("categorization", ("category", "categorize", "classified", "learn this merchant", "merchant learning")),
        ("account_summary", ("balance", "account", "cash flow", "net worth", "standing")),
        ("saving_advice", ("save", "saving", "cut", "reduce", "subscription", "goal")),
        ("external_learning", ("youtube", "video", "link", "learn how", "recipe", "tutorial")),
        ("auth_help", ("login", "password", "reset", "email", "verify")),
    )
    for intent, keywords in keyword_groups:
        if any(keyword in text for keyword in keywords):
            return intent
    return "general"


def save_assistant_learning_example(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None,
    mode: str,
    scope_label: str,
    question: str,
    answer: str,
    source: str = "assistant_exchange",
    quality_score: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> AssistantLearningExample | None:
    clean_question = clean_assistant_message(question, limit=1200)
    clean_answer = clean_assistant_message(answer)
    if not clean_question or not clean_answer:
        return None

    safe_score = None
    if quality_score is not None:
        safe_score = max(0.0, min(float(quality_score), 1.0))

    example = AssistantLearningExample(
        question=clean_question,
        answer=clean_answer,
        intent=infer_assistant_learning_intent(question),
        mode=(mode or "balanced")[:20],
        scope_label=(scope_label or "All accounts combined")[:160],
        source=(source or "assistant_exchange")[:40],
        quality_score=safe_score,
        metadata_json=json.dumps(metadata or {}, sort_keys=True)[:4000] if metadata else None,
        owner_id=owner_id,
        account_id=account_id,
    )
    db.add(example)
    db.flush()
    trim_assistant_learning_examples(db, owner_id)
    return example


def trim_assistant_learning_examples(
    db: Session,
    owner_id: int,
    *,
    max_examples: int | None = None,
) -> int:
    safe_max = max_examples or assistant_learning_max_examples_per_user()
    keep_ids = [
        item.id
        for item in db.query(AssistantLearningExample.id)
        .filter(AssistantLearningExample.owner_id == owner_id)
        .order_by(AssistantLearningExample.created_at.desc(), AssistantLearningExample.id.desc())
        .limit(safe_max)
        .all()
    ]
    if not keep_ids:
        return 0

    deleted_count = (
        db.query(AssistantLearningExample)
        .filter(
            AssistantLearningExample.owner_id == owner_id,
            ~AssistantLearningExample.id.in_(keep_ids),
        )
        .delete(synchronize_session=False)
    )
    return int(deleted_count or 0)


def get_assistant_learning_examples(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None = None,
    intent: str | None = None,
    limit: int = ASSISTANT_LEARNING_DEFAULT_LIMIT,
) -> list[AssistantLearningExample]:
    safe_limit = max(1, min(int(limit or ASSISTANT_LEARNING_DEFAULT_LIMIT), ASSISTANT_LEARNING_EXPORT_MAX_LIMIT))
    query = db.query(AssistantLearningExample).filter(AssistantLearningExample.owner_id == owner_id)
    query = _learning_scope_filter(query, account_id)
    if intent:
        query = query.filter(AssistantLearningExample.intent == intent[:80])
    return list(
        query.order_by(AssistantLearningExample.created_at.desc(), AssistantLearningExample.id.desc())
        .limit(safe_limit)
        .all()
    )


def update_assistant_learning_example_quality(
    db: Session,
    owner_id: int,
    example_id: int,
    *,
    quality_score: float,
) -> AssistantLearningExample | None:
    example = (
        db.query(AssistantLearningExample)
        .filter(
            AssistantLearningExample.id == example_id,
            AssistantLearningExample.owner_id == owner_id,
        )
        .one_or_none()
    )
    if example is None:
        return None

    example.quality_score = max(0.0, min(float(quality_score), 1.0))
    db.flush()
    return example


def _learning_tokens(value: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "again",
        "also",
        "because",
        "before",
        "could",
        "from",
        "have",
        "help",
        "into",
        "that",
        "the",
        "this",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
        "your",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", str(value or "").lower())
        if token not in stopwords
    }


def get_relevant_assistant_learning_examples(
    db: Session,
    owner_id: int,
    *,
    question: str,
    account_id: int | None = None,
    limit: int = 3,
) -> list[AssistantLearningExample]:
    intent = infer_assistant_learning_intent(question)
    question_tokens = _learning_tokens(question)
    if not question_tokens:
        return []

    query = db.query(AssistantLearningExample).filter(
        AssistantLearningExample.owner_id == owner_id,
        AssistantLearningExample.intent == intent,
    )
    if account_id is not None:
        query = query.filter(
            (AssistantLearningExample.account_id == account_id)
            | (AssistantLearningExample.account_id.is_(None))
        )
    query = query.filter(
        (AssistantLearningExample.quality_score.is_(None))
        | (AssistantLearningExample.quality_score >= 0.4)
    )
    candidates = (
        query.order_by(AssistantLearningExample.created_at.desc(), AssistantLearningExample.id.desc())
        .limit(80)
        .all()
    )

    scored: list[tuple[float, AssistantLearningExample]] = []
    for example in candidates:
        example_tokens = _learning_tokens(f"{example.question} {example.answer}")
        if not example_tokens:
            continue
        overlap = len(question_tokens & example_tokens)
        if overlap <= 0:
            continue
        quality_bonus = 0.5 if example.quality_score is None else float(example.quality_score)
        score = overlap + quality_bonus
        scored.append((score, example))

    scored.sort(key=lambda item: (item[0], item[1].created_at, item[1].id), reverse=True)
    return [example for _, example in scored[: max(1, min(limit, 5))]]


def build_assistant_learning_context(
    db: Session,
    owner_id: int,
    *,
    question: str,
    account_id: int | None = None,
    limit: int = 3,
) -> str:
    examples = get_relevant_assistant_learning_examples(
        db,
        owner_id,
        question=question,
        account_id=account_id,
        limit=limit,
    )
    if not examples:
        return ""

    lines = [
        "Relevant past assistant answer patterns. Use these for style and intent only; do not copy old financial facts."
    ]
    for example in examples:
        lines.append(
            "- User asked: "
            f"{clean_assistant_message(example.question, limit=220)} | "
            f"Assistant answered: {clean_assistant_message(example.answer, limit=320)}"
        )

    text = "\n".join(lines)
    if len(text) > ASSISTANT_LEARNING_CONTEXT_MAX_CHARS:
        return f"{text[:ASSISTANT_LEARNING_CONTEXT_MAX_CHARS].rstrip()}..."
    return text


def get_assistant_learning_summary(db: Session, owner_id: int) -> dict[str, Any]:
    total = (
        db.query(func.count(AssistantLearningExample.id))
        .filter(AssistantLearningExample.owner_id == owner_id)
        .scalar()
    )
    intent_rows = (
        db.query(AssistantLearningExample.intent, func.count(AssistantLearningExample.id))
        .filter(AssistantLearningExample.owner_id == owner_id)
        .group_by(AssistantLearningExample.intent)
        .order_by(func.count(AssistantLearningExample.id).desc())
        .all()
    )
    recent_examples = get_assistant_learning_examples(db, owner_id, limit=5)
    return {
        "total_examples": int(total or 0),
        "intent_counts": {str(intent): int(count or 0) for intent, count in intent_rows},
        "recent_examples": recent_examples,
    }


def build_assistant_training_export(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None = None,
    intent: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    examples = get_assistant_learning_examples(
        db,
        owner_id,
        account_id=account_id,
        intent=intent,
        limit=limit,
    )
    return [
        {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Smart Spending Analyzer's assistant. Answer simply and use the "
                        "user's real financial data only when the question is about their finances."
                    ),
                },
                {"role": "user", "content": example.question},
                {"role": "assistant", "content": example.answer},
            ],
            "metadata": {
                "intent": example.intent,
                "mode": example.mode,
                "scope_label": example.scope_label,
                "source": example.source,
                "created_at": example.created_at.isoformat() if example.created_at else None,
            },
        }
        for example in examples
    ]


def clear_assistant_learning_examples(
    db: Session,
    owner_id: int,
    *,
    account_id: int | None = None,
) -> int:
    query = db.query(AssistantLearningExample).filter(AssistantLearningExample.owner_id == owner_id)
    query = _learning_scope_filter(query, account_id)
    deleted_count = query.delete(synchronize_session=False)
    return int(deleted_count or 0)


def assistant_usage_window_start() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=24)


def get_assistant_usage_status(db: Session, owner_id: int) -> dict[str, int]:
    limit = assistant_daily_llm_limit()
    char_limit = assistant_daily_llm_char_limit()
    base_query = db.query(AssistantUsageEvent).filter(
        AssistantUsageEvent.owner_id == owner_id,
        AssistantUsageEvent.created_at >= assistant_usage_window_start(),
    )
    used = base_query.count()
    used_chars = (
        db.query(
            func.coalesce(
                func.sum(AssistantUsageEvent.request_chars + AssistantUsageEvent.response_chars),
                0,
            )
        )
        .filter(
            AssistantUsageEvent.owner_id == owner_id,
            AssistantUsageEvent.created_at >= assistant_usage_window_start(),
        )
        .scalar()
    )
    remaining = max(0, limit - int(used or 0))
    chars_remaining = max(0, char_limit - int(used_chars or 0))
    return {
        "daily_limit": limit,
        "daily_used": int(used or 0),
        "daily_remaining": remaining,
        "daily_char_limit": char_limit,
        "daily_chars_used": int(used_chars or 0),
        "daily_chars_remaining": chars_remaining,
    }


def assistant_llm_usage_allowed(
    db: Session,
    owner_id: int,
    *,
    estimated_request_chars: int = 0,
) -> bool:
    status = get_assistant_usage_status(db, owner_id)
    if status["daily_remaining"] <= 0:
        return False

    estimated_chars = max(0, int(estimated_request_chars or 0))
    return status["daily_chars_remaining"] > estimated_chars


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
