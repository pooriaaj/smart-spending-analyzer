from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.routes.route_guards import resolve_account_scope_label
from app.schemas import (
    AssistantHistoryClearResponse,
    AssistantHistoryItem,
    AssistantHistoryResponse,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantStatusResponse,
    AssistantSuggestionsResponse,
)
from app.services.assistant_service import (
    generate_assistant_response,
    generate_assistant_suggestions,
)
from app.services.assistant_memory_service import (
    assistant_llm_usage_allowed,
    clear_assistant_history,
    get_assistant_usage_status,
    get_recent_assistant_history_payload,
    get_recent_assistant_messages,
    record_assistant_usage_event,
    save_assistant_exchange,
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


@router.post("/response", response_model=AssistantQueryResponse)
def get_assistant_response_route(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantQueryResponse:
    scope_label = resolve_assistant_account_scope(db, current_user, payload.account_id)
    active_llm_provider = get_active_llm_provider()
    llm_allowed = True
    if active_llm_provider is not None:
        estimated_request_chars = len(payload.question or "") + sum(
            len(str(item.content or ""))
            for item in (payload.history or [])
        )
        llm_allowed = assistant_llm_usage_allowed(
            db,
            current_user.id,
            estimated_request_chars=estimated_request_chars,
        )

    history = payload.history or get_recent_assistant_history_payload(
        db,
        current_user.id,
        account_id=payload.account_id,
        limit=8,
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
