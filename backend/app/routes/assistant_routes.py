from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantStatusResponse,
    AssistantSuggestionsResponse,
)
from app.services.account_service import get_account_for_user
from app.services.assistant_service import (
    generate_assistant_response,
    generate_assistant_suggestions,
)
from app.services.llm_service import get_llm_provider_status

router = APIRouter(prefix="/assistant", tags=["Assistant"])


def resolve_assistant_account_scope(
    db: Session,
    current_user: User,
    account_id: int | None,
) -> str:
    if account_id is None:
        return "All accounts combined"

    account = get_account_for_user(db, current_user.id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return f"{account.name} ({account.type})"


@router.get("/status", response_model=AssistantStatusResponse)
def get_assistant_status_route(
    current_user: User = Depends(get_current_user),
) -> AssistantStatusResponse:
    _ = current_user
    return get_llm_provider_status()


@router.post("/response", response_model=AssistantQueryResponse)
def get_assistant_response_route(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssistantQueryResponse:
    scope_label = resolve_assistant_account_scope(db, current_user, payload.account_id)
    return generate_assistant_response(
        db,
        current_user.id,
        payload.question,
        payload.history,
        payload.mode,
        account_id=payload.account_id,
        scope_label=scope_label,
    )


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
