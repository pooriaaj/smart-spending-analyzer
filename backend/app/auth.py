from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt
from dotenv import load_dotenv
from starlette.responses import Response

from app.security import is_production, validate_password_strength

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "")
LEGACY_PBKDF2_ITERATIONS = 100000
BCRYPT_HASH_PREFIXES = ("$2a$", "$2b$", "$2y$")
SUPPORTED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _jwt_algorithm_env() -> str:
    algorithm = os.getenv("ALGORITHM", "HS256").strip().upper()
    if algorithm not in SUPPORTED_JWT_ALGORITHMS:
        return "HS256"
    return algorithm


ALGORITHM = _jwt_algorithm_env()
ACCESS_TOKEN_EXPIRE_MINUTES = _bounded_int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 60, 5, 24 * 60)
BCRYPT_ROUNDS = _bounded_int_env("BCRYPT_ROUNDS", 12, 4, 16)
ACCESS_TOKEN_COOKIE_NAME = os.getenv("ACCESS_TOKEN_COOKIE_NAME", "access_token")


def _auth_cookie_secure_env() -> bool:
    configured = os.getenv("AUTH_COOKIE_SECURE")
    if configured is None:
        return is_production()
    return configured.strip().lower() in {"1", "true", "yes", "on"}


def _auth_cookie_samesite_env() -> str:
    configured = os.getenv(
        "AUTH_COOKIE_SAMESITE",
        "none" if is_production() else "lax",
    ).strip().lower()
    if configured not in {"lax", "strict", "none"}:
        return "none" if is_production() else "lax"
    return configured


AUTH_COOKIE_SECURE = _auth_cookie_secure_env()
AUTH_COOKIE_SAMESITE = _auth_cookie_samesite_env()
if AUTH_COOKIE_SAMESITE == "none" and not AUTH_COOKIE_SECURE:
    AUTH_COOKIE_SAMESITE = "lax"

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set.")
if is_production() and len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters in production.")


def _bcrypt_secret(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) <= 72:
        return raw
    return hashlib.sha256(raw).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    return bcrypt.hashpw(_bcrypt_secret(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def hash_password_legacy_pbkdf2(password: str) -> str:
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        LEGACY_PBKDF2_ITERATIONS,
    )
    return f"{salt}${password_hash.hex()}"


def verify_legacy_pbkdf2_password(password: str, stored_password: str) -> bool:
    try:
        salt, saved_hash = stored_password.split("$", 1)
    except ValueError:
        return False

    if not salt or not saved_hash:
        return False

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        LEGACY_PBKDF2_ITERATIONS,
    ).hex()

    return hmac.compare_digest(password_hash, saved_hash)


def verify_password(password: str, stored_password: str) -> bool:
    if not stored_password:
        return False

    if stored_password.startswith(BCRYPT_HASH_PREFIXES):
        try:
            return bcrypt.checkpw(_bcrypt_secret(password), stored_password.encode("utf-8"))
        except (TypeError, ValueError):
            return False

    return verify_legacy_pbkdf2_password(password, stored_password)


def create_access_token(data: dict) -> str:
    subject = data.get("sub")
    to_encode = {"sub": str(subject)}
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def set_access_token_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
    )


def clear_access_token_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        path="/",
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None
