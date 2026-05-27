from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.routes.route_guards import resolve_account_scope_label
from app.schemas import (
    AssistantHistoryClearResponse,
    AssistantHistoryItem,
    AssistantHistoryResponse,
    AssistantLearningClearResponse,
    AssistantLearningExampleResponse,
    AssistantLearningFeedbackRequest,
    AssistantLearningSummaryResponse,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantStatusResponse,
    AssistantSuggestionsResponse,
    AssistantTrainingExportResponse,
)
from app.services.assistant_service import (
    generate_assistant_response,
    generate_assistant_suggestions,
)
from app.services.assistant_memory_service import (
    assistant_llm_usage_allowed,
    build_assistant_training_export,
    clear_assistant_learning_examples,
    clear_assistant_history,
    get_assistant_learning_summary,
    get_assistant_usage_status,
    get_recent_assistant_history_payload,
    get_recent_assistant_messages,
    record_assistant_usage_event,
    save_assistant_exchange,
    save_assistant_learning_example,
    update_assistant_learning_example_quality,
)
from app.services.llm_service import get_active_llm_provider, get_llm_provider_status

router = APIRouter(prefix="/assistant", tags=["Assistant"])
logger = logging.getLogger(__name__)


def resolve_assistant_account_scope(
    db: Session,
    current_user: User,
    account_id: int | None,
) -> str:
    return resolve_account_scope_label(db, current_user, account_id)


def assistant_history_item_content(item) -> str:
    if isinstance(item, dict):
        return str(item.get("content") or "")
    return str(getattr(item, "content", "") or "")


@router.get("/status", response_model=AssistantStatusResponse)
def get_assistant_status_route(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantStatusResponse:
    status = get_llm_provider_status()
    status.update(get_assistant_usage_status(db, current_user.id))
    return status


@router.get("/history", response_model=AssistantHistoryResponse)
def get_assistant_history_route(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantHistoryResponse:
    resolve_assistant_account_scope(db, current_user, account_id)
    messages = get_recent_assistant_messages(
        db,
        current_user.id,
        account_id=account_id,
        limit=limit,
    )
    return AssistantHistoryResponse(
        messages=[
            AssistantHistoryItem(
                role=message.role,
                content=message.content,
                mode=message.mode,
                scope_label=message.scope_label,
                account_id=message.account_id,
                created_at=message.created_at,
            )
            for message in messages
            if message.role in {"user", "assistant"}
        ]
    )


@router.delete("/history", response_model=AssistantHistoryClearResponse)
def clear_assistant_history_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantHistoryClearResponse:
    resolve_assistant_account_scope(db, current_user, account_id)
    deleted_count = clear_assistant_history(db, current_user.id, account_id=account_id)
    db.commit()
    return AssistantHistoryClearResponse(
        message="Assistant conversation history cleared.",
        deleted_count=deleted_count,
    )


@router.get("/learning-summary", response_model=AssistantLearningSummaryResponse)
def get_assistant_learning_summary_route(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantLearningSummaryResponse:
    summary = get_assistant_learning_summary(db, current_user.id)
    return AssistantLearningSummaryResponse(
        total_examples=summary["total_examples"],
        intent_counts=summary["intent_counts"],
        recent_examples=[
            AssistantLearningExampleResponse(
                id=example.id,
                question=example.question,
                answer=example.answer,
                intent=example.intent,
                mode=example.mode,
                scope_label=example.scope_label,
                source=example.source,
                quality_score=example.quality_score,
                account_id=example.account_id,
                created_at=example.created_at,
            )
            for example in summary["recent_examples"]
        ],
    )


@router.get("/training-export", response_model=AssistantTrainingExportResponse)
def get_assistant_training_export_route(
    account_id: int | None = Query(default=None),
    intent: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantTrainingExportResponse:
    resolve_assistant_account_scope(db, current_user, account_id)
    return AssistantTrainingExportResponse(
        items=build_assistant_training_export(
            db,
            current_user.id,
            account_id=account_id,
            intent=intent,
            limit=limit,
        )
    )


@router.delete("/training-examples", response_model=AssistantLearningClearResponse)
def clear_assistant_training_examples_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantLearningClearResponse:
    resolve_assistant_account_scope(db, current_user, account_id)
    deleted_count = clear_assistant_learning_examples(db, current_user.id, account_id=account_id)
    db.commit()
    return AssistantLearningClearResponse(
        message="Assistant training examples cleared.",
        deleted_count=deleted_count,
    )


@router.post("/training-examples/{example_id}/feedback", response_model=AssistantLearningExampleResponse)
def update_assistant_training_example_feedback_route(
    example_id: int,
    payload: AssistantLearningFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantLearningExampleResponse:
    example = update_assistant_learning_example_quality(
        db,
        current_user.id,
        example_id,
        quality_score=payload.quality_score,
    )
    if example is None:
        raise HTTPException(status_code=404, detail="Assistant training example not found.")
    db.commit()
    db.refresh(example)
    return AssistantLearningExampleResponse(
        id=example.id,
        question=example.question,
        answer=example.answer,
        intent=example.intent,
        mode=example.mode,
        scope_label=example.scope_label,
        source=example.source,
        quality_score=example.quality_score,
        account_id=example.account_id,
        created_at=example.created_at,
    )


@router.post("/response", response_model=AssistantQueryResponse)
def get_assistant_response_route(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantQueryResponse:
    scope_label = resolve_assistant_account_scope(db, current_user, payload.account_id)
    active_llm_provider = get_active_llm_provider()
    history = payload.history or get_recent_assistant_history_payload(
        db,
        current_user.id,
        account_id=payload.account_id,
        limit=8,
    )
    llm_allowed = True
    if active_llm_provider is not None:
        estimated_request_chars = len(payload.question or "") + sum(
            len(assistant_history_item_content(item))
            for item in history
        )
        llm_allowed = assistant_llm_usage_allowed(
            db,
            current_user.id,
            estimated_request_chars=estimated_request_chars,
        )

    response = generate_assistant_response(
        db,
        current_user.id,
        payload.question,
        history,
        payload.mode,
        account_id=payload.account_id,
        scope_label=scope_label,
        llm_allowed=llm_allowed,
    )
    if active_llm_provider is not None and not llm_allowed:
        response["supporting_points"] = [
            "Assistant daily safety limit reached, so this answer used the safe rule-based fallback.",
            *response.get("supporting_points", []),
        ][:5]

    try:
        save_assistant_exchange(
            db=db,
            owner_id=current_user.id,
            account_id=payload.account_id,
            mode=payload.mode,
            scope_label=scope_label,
            question=payload.question,
            answer=response["answer"],
        )
        save_assistant_learning_example(
            db=db,
            owner_id=current_user.id,
            account_id=payload.account_id,
            mode=payload.mode,
            scope_label=scope_label,
            question=payload.question,
            answer=response["answer"],
            metadata={
                "active_provider": active_llm_provider or "rule_based",
                "llm_allowed": llm_allowed,
            },
        )
        if active_llm_provider is not None and llm_allowed:
            record_assistant_usage_event(
                db,
                current_user.id,
                provider=active_llm_provider,
                request_chars=len(payload.question or ""),
                response_chars=len(response.get("answer") or ""),
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "Assistant history or usage side effects skipped for user_id=%s",
            current_user.id,
            exc_info=True,
        )

    return response


@router.get("/suggestions", response_model=AssistantSuggestionsResponse)
def get_assistant_suggestions_route(
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantSuggestionsResponse:
    resolve_assistant_account_scope(db, current_user, account_id)
    return {
        "suggestions": generate_assistant_suggestions(
            db,
            current_user.id,
            account_id=account_id,
        )
    }
