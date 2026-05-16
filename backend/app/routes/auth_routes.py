from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password, verify_password
from app.database import SessionLocal
from app.models import User
from app.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    Token,
    UserCreate,
)
from app.security import is_production

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expose_reset_url_in_response() -> bool:
    configured = os.getenv("EXPOSE_RESET_LINK_IN_RESPONSE")
    if configured is not None:
        return configured.lower() == "true"
    return not is_production()


@router.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)) -> Token:
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    new_user = User(
        email=user.email,
        password_hash=hash_password(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token({"sub": str(new_user.id)})

    return Token(access_token=access_token, token_type="bearer")


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token({"sub": str(user.id)})

    return Token(access_token=access_token, token_type="bearer")


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> ForgotPasswordResponse:
    user = db.query(User).filter(User.email == payload.email).first()

    generic_message = "If an account with that email exists, a reset link has been generated."

    if not user:
        return ForgotPasswordResponse(message=generic_message)

    raw_token = secrets.token_urlsafe(32)
    user.reset_token_hash = hash_reset_token(raw_token)
    user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    db.commit()

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    reset_url = f"{frontend_url}/reset-password?token={quote(raw_token)}"

    return ForgotPasswordResponse(
        message=generic_message,
        reset_url=(reset_url if expose_reset_url_in_response() else None),
    )


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    token_hash = hash_reset_token(payload.token)

    user = (
        db.query(User)
        .filter(User.reset_token_hash == token_hash)
        .first()
    )

    if not user or not user.reset_token_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    expires_at = user.reset_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )

    user.password_hash = hash_password(payload.new_password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    db.commit()

    return {"message": "Password has been reset successfully"}
