from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    MessageResponse,
    UserProfileResponse,
    UserProfileUpdate,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.put("/me", response_model=UserProfileResponse)
def update_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    existing_user = (
        db.query(User)
        .filter(User.email == payload.email, User.id != current_user.id)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use",
        )

    current_user.email = payload.email
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/me/password", response_model=MessageResponse)
def change_my_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    current_user.password_hash = hash_password(payload.new_password)
    db.commit()

    return MessageResponse(message="Password changed successfully")


@router.delete("/me", response_model=MessageResponse)
def delete_my_account(
    payload: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is incorrect",
        )

    db.delete(current_user)
    db.commit()

    return MessageResponse(message="Account deleted successfully")