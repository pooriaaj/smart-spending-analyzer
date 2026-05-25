from __future__ import annotations

import os
import re
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterable
from urllib.parse import urlparse

from fastapi import Request, UploadFile, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_BATCH_FILES = 24
DEFAULT_MAX_BATCH_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_CSV_ROWS = 5000
DEFAULT_MAX_API_REQUEST_BODY_BYTES = 1 * 1024 * 1024

ALLOWED_IMPORT_EXTENSIONS = {".csv", ".pdf", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMPORT_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

FILE_SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),
}

SENSITIVE_RESPONSE_MARKERS = (
    "api key",
    "apikey",
    "authorization:",
    "bearer ",
    "client_secret",
    "secret_key",
    "secret key",
    "database_url",
    "database url",
    "openai_api_key",
    "postgresql://",
    "private_key",
    "refresh_token",
    "reset token",
    "reset_token",
    "sk-",
    "token=",
)

VALIDATION_ERROR_MESSAGE = "Please check the highlighted fields and try again."


def is_production() -> bool:
    return os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).lower() == "production"


def parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


def get_allowed_origins() -> list[str]:
    origins = parse_csv_env(os.getenv("ALLOWED_ORIGINS"))
    frontend_url = (os.getenv("FRONTEND_URL") or "").strip().rstrip("/")
    if frontend_url:
        origins.append(frontend_url)

    if not is_production():
        origins.extend(
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
        )

    safe_origins = []
    for origin in dict.fromkeys(origins):
        if origin == "*":
            continue
        if is_production() and origin.startswith(("http://localhost", "http://127.0.0.1")):
            continue
        safe_origins.append(origin)
    return safe_origins


def get_allowed_hosts() -> list[str]:
    hosts = parse_csv_env(os.getenv("ALLOWED_HOSTS"))
    backend_url = (os.getenv("BACKEND_URL") or "").strip()
    frontend_url = (os.getenv("FRONTEND_URL") or "").strip()

    for url in (backend_url, frontend_url):
        parsed = urlparse(url)
        if parsed.hostname:
            hosts.append(parsed.hostname)

    if not is_production():
        hosts.extend(["localhost", "127.0.0.1", "testserver"])
    else:
        hosts.append("*.onrender.com")

    return list(dict.fromkeys(hosts))


def validate_password_strength(password: str) -> None:
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must be 128 characters or fewer.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must include at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must include at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must include at least one number.")
    if password.lower() in {"password", "password1", "password123", "qwerty123"}:
        raise ValueError("Password is too common.")


def normalize_validation_errors(errors: Iterable[dict]) -> list[dict[str, str]]:
    safe_errors: list[dict[str, str]] = []

    for item in errors:
        if not isinstance(item, dict):
            continue

        loc_parts = [
            str(part)
            for part in item.get("loc", [])
            if str(part) not in {"body", "query", "path"}
        ]
        safe_errors.append(
            {
                "loc": ".".join(loc_parts) or "request",
                "msg": str(item.get("msg") or "Invalid value."),
                "type": str(item.get("type") or "validation_error"),
            }
        )

    return safe_errors


def build_validation_error_response(errors: Iterable[dict]) -> dict[str, object]:
    return {
        "detail": VALIDATION_ERROR_MESSAGE,
        "message": VALIDATION_ERROR_MESSAGE,
        "errors": normalize_validation_errors(errors),
    }


def sanitize_import_text(value: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if text[:1] in {"=", "+", "-", "@"}:
        return f"'{text}"
    return text


def max_upload_bytes() -> int:
    return _bounded_int_env("MAX_IMPORT_FILE_BYTES", DEFAULT_MAX_UPLOAD_BYTES, 1024, 100 * 1024 * 1024)


def max_batch_files() -> int:
    return _bounded_int_env("MAX_IMPORT_BATCH_FILES", DEFAULT_MAX_BATCH_FILES, 1, 100)


def max_batch_upload_bytes() -> int:
    return _bounded_int_env("MAX_IMPORT_BATCH_BYTES", DEFAULT_MAX_BATCH_UPLOAD_BYTES, 1024, 250 * 1024 * 1024)


def max_csv_rows() -> int:
    return _bounded_int_env("MAX_IMPORT_CSV_ROWS", DEFAULT_MAX_CSV_ROWS, 1, 100_000)


def max_api_request_body_bytes() -> int:
    return _bounded_int_env("MAX_API_REQUEST_BODY_BYTES", DEFAULT_MAX_API_REQUEST_BODY_BYTES, 1024, 50 * 1024 * 1024)


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _file_extension(filename: str | None) -> str:
    _, ext = os.path.splitext(filename or "")
    return ext.lower()


def validate_import_filename_and_type(filename: str | None, content_type: str | None) -> str:
    extension = _file_extension(filename)
    if extension not in ALLOWED_IMPORT_EXTENSIONS:
        raise ValueError("Unsupported file extension. Upload CSV, PDF, JPG, PNG, or WEBP files.")

    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_content_type and normalized_content_type not in ALLOWED_IMPORT_CONTENT_TYPES:
        raise ValueError("Unsupported file content type.")
    return extension


def validate_import_file_signature(file_bytes: bytes, extension: str) -> None:
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    signatures = FILE_SIGNATURES.get(extension)
    if signatures and not any(file_bytes.startswith(signature) for signature in signatures):
        raise ValueError("Uploaded file content does not match its extension.")

    if extension == ".webp" and file_bytes[8:12] != b"WEBP":
        raise ValueError("Uploaded file content does not match its extension.")

    if extension == ".csv":
        sample = file_bytes[:2048]
        if b"\x00" in sample:
            raise ValueError("CSV file appears to contain binary data.")


async def read_upload_file_limited(file: UploadFile, *, max_bytes: int | None = None) -> bytes:
    limit = max_bytes or max_upload_bytes()
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"File is too large. Maximum upload size is {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)

    return b"".join(chunks)


async def read_validated_import_upload(file: UploadFile) -> tuple[bytes, str, str | None]:
    extension = validate_import_filename_and_type(file.filename, file.content_type)
    file_bytes = await read_upload_file_limited(file)
    validate_import_file_signature(file_bytes, extension)
    return file_bytes, file.filename or f"statement{extension}", file.content_type


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if request.url.path.startswith(("/auth", "/users", "/assistant")):
            response.headers.setdefault("Cache-Control", "no-store")
        if is_production():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", request_id):
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request_id)
        return response


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_bytes: int | None = None):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes or max_api_request_body_bytes()

    async def dispatch(self, request: Request, call_next):
        if self._is_exempt_path(request.url.path) or request.method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                request_size = int(content_length)
            except ValueError:
                request_size = 0
            if request_size > self.max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": "Request body is too large."},
                )

        return await call_next(request)

    @staticmethod
    def _is_exempt_path(path: str) -> bool:
        return path.startswith("/transactions/import/")


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rules: dict[str, tuple[int, int]] | None = None):
        super().__init__(app)
        self.rules = rules or {
            "/auth/login": (10, 60),
            "/auth/register": (5, 60),
            "/auth/forgot-password": (5, 300),
            "/auth/reset-password": (5, 300),
            "/assistant/response": (30, 60),
            "/transactions/import/file": (10, 300),
            "/transactions/import/files": (5, 300),
        }
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.max_tracked_keys = _bounded_int_env("RATE_LIMIT_MAX_TRACKED_KEYS", 10000, 100, 100000)

    async def dispatch(self, request: Request, call_next):
        rule = self._matching_rule(request.url.path)
        if rule and request.method not in {"GET", "HEAD", "OPTIONS"}:
            limit, window_seconds = rule
            client_id = self._client_id(request)
            key = (client_id, request.url.path)
            now = time.monotonic()
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests. Please wait and try again."},
                )
            hits.append(now)
            self._trim_tracking(now)
        return await call_next(request)

    def _matching_rule(self, path: str) -> tuple[int, int] | None:
        for prefix, rule in self.rules.items():
            if path == prefix or path.startswith(f"{prefix}/"):
                return rule
        return None

    def _trim_tracking(self, now: float) -> None:
        if len(self._hits) <= self.max_tracked_keys:
            return

        expired_keys = []
        for key, hits in self._hits.items():
            rule = self._matching_rule(key[1])
            if not rule:
                expired_keys.append(key)
                continue
            _, window_seconds = rule
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if not hits:
                expired_keys.append(key)

        for key in expired_keys:
            self._hits.pop(key, None)

        if len(self._hits) <= self.max_tracked_keys:
            return

        overflow = len(self._hits) - self.max_tracked_keys
        oldest_keys = sorted(
            self._hits,
            key=lambda item: self._hits[item][0] if self._hits[item] else now,
        )[:overflow]
        for key in oldest_keys:
            self._hits.pop(key, None)

    @staticmethod
    def _client_id(request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        return request.client.host if request.client else "unknown"


def redact_sensitive_text(value: str) -> str:
    lowered = value.lower()
    if any(marker in lowered for marker in SENSITIVE_RESPONSE_MARKERS):
        return "Sensitive value redacted."
    return value


def ensure_batch_file_count(files: Iterable[UploadFile]) -> list[UploadFile]:
    file_list = list(files)
    if len(file_list) > max_batch_files():
        raise ValueError(f"Too many files in one import batch. Maximum is {max_batch_files()}.")
    return file_list


def ensure_batch_payload_size(file_payloads: Iterable[tuple[bytes, str, str | None]]) -> None:
    total_bytes = sum(len(payload[0]) for payload in file_payloads)
    limit = max_batch_upload_bytes()
    if total_bytes > limit:
        raise ValueError(
            f"Import batch is too large. Maximum combined upload size is {limit // (1024 * 1024)} MB."
        )
