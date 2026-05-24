from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.dependencies import get_current_user, get_db
from app.models import MerchantCategoryProfile, User, UserLearningPreference
from app.schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    MessageResponse,
    UserLearningPreferenceUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.transaction_service import (
    merchant_profile_base_key,
    refresh_community_merchant_profile_cache,
)

router = APIRouter(prefix="/users", tags=["Users"])


def normalize_email_address(email: str) -> str:
    return str(email or "").strip().lower()


def get_community_learning_preference(db: Session, owner_id: int) -> UserLearningPreference | None:
    return (
        db.query(UserLearningPreference)
        .filter(UserLearningPreference.owner_id == owner_id)
        .one_or_none()
    )


def get_or_create_community_learning_preference(
    db: Session,
    owner_id: int,
) -> UserLearningPreference:
    preference = get_community_learning_preference(db, owner_id)
    if preference:
        return preference

    preference = UserLearningPreference(owner_id=owner_id, community_learning_enabled=True)
    db.add(preference)
    db.flush()
    return preference


def build_profile_response(db: Session, user: User) -> UserProfileResponse:
    preference = get_community_learning_preference(db, user.id)
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        community_learning_enabled=(
            True if preference is None else bool(preference.community_learning_enabled)
        ),
    )


def refresh_user_community_learning_contributions(db: Session, owner_id: int) -> None:
    profiles = (
        db.query(MerchantCategoryProfile)
        .filter(MerchantCategoryProfile.owner_id == owner_id)
        .all()
    )
    profile_keys = {
        (merchant_profile_base_key(profile.merchant_key), profile.transaction_type)
        for profile in profiles
        if profile.merchant_key and profile.transaction_type
    }
    for merchant_key, tx_type in profile_keys:
        if merchant_key:
            refresh_community_merchant_profile_cache(db, merchant_key, tx_type)


@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    return build_profile_response(db, current_user)


@router.put("/me", response_model=UserProfileResponse)
def update_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    normalized_email = normalize_email_address(payload.email)
    existing_user = (
        db.query(User)
        .filter(func.lower(User.email) == normalized_email, User.id != current_user.id)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use",
        )

    current_user.email = normalized_email
    db.commit()
    db.refresh(current_user)
    return build_profile_response(db, current_user)


@router.put("/me/learning", response_model=UserProfileResponse)
def update_my_learning_preferences(
    payload: UserLearningPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    preference = get_or_create_community_learning_preference(db, current_user.id)
    preference.community_learning_enabled = payload.community_learning_enabled
    db.flush()

    refresh_user_community_learning_contributions(db, current_user.id)

    db.commit()
    return build_profile_response(db, current_user)


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
    current_user.password_changed_at = datetime.now(timezone.utc)
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
