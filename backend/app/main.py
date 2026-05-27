from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.database import Base, SessionLocal, engine
from app.routes.account_routes import router as account_router
from app.routes.analytics_routes import router as analytics_router
from app.routes.assistant_routes import router as assistant_router
from app.routes.auth_routes import router as auth_router
from app.routes.budget_routes import router as budget_router
from app.routes.transaction_routes import router as transaction_router
from app.routes.user_routes import router as user_router
from app.security import (
    RequestBodySizeLimitMiddleware,
    RequestIdMiddleware,
    CsrfOriginMiddleware,
    SecurityHeadersMiddleware,
    SimpleRateLimitMiddleware,
    build_validation_error_response,
    get_allowed_hosts,
    get_allowed_origins,
)
from app.services.database_maintenance_service import ensure_runtime_database_shape
from app.services.transaction_service import rebuild_community_merchant_profile_cache

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


def on_startup() -> None:
    ensure_runtime_database_shape(engine)
    if os.getenv("REBUILD_MERCHANT_CACHE_ON_STARTUP", "false").lower() == "true":
        try:
            with SessionLocal() as db:
                stats = rebuild_community_merchant_profile_cache(db)
                db.commit()
                logger.info("Community category learning cache refreshed: %s", stats)
        except Exception:
            logger.exception("Community category learning cache refresh skipped")
    logger.info("Smart Spending Analyzer API started")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    on_startup()
    yield


app = FastAPI(
    title="Smart Spending Analyzer API",
    version="1.0.0",
    description="Backend API for Smart Spending Analyzer",
    lifespan=lifespan,
)

Base.metadata.create_all(bind=engine)

allowed_origins = get_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_allowed_hosts())
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CsrfOriginMiddleware, allowed_origins=allowed_origins)
app.add_middleware(RequestBodySizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SimpleRateLimitMiddleware)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(account_router)
app.include_router(budget_router)
app.include_router(transaction_router)
app.include_router(analytics_router)
app.include_router(assistant_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled API error at %s request_id=%s", request.url.path, request_id)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.info("Validation error at %s request_id=%s", request.url.path, request_id)
    content = build_validation_error_response(exc.errors())
    content["request_id"] = request_id
    return JSONResponse(
        status_code=422,
        content=content,
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Smart Spending Analyzer API is running"}


@app.head("/")
def root_head() -> Response:
    return Response(status_code=200)


def check_database_ready() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def readiness_response() -> JSONResponse:
    try:
        check_database_ready()
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "unavailable"},
        )
    return JSONResponse(content={"status": "ok", "database": "ok"})


@app.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.head("/live")
def live_head() -> Response:
    return Response(status_code=200)


@app.get("/ready")
def ready() -> JSONResponse:
    return readiness_response()


@app.head("/ready")
def ready_head() -> Response:
    response = readiness_response()
    return Response(status_code=response.status_code)


@app.get("/health")
def health() -> JSONResponse:
    return readiness_response()


@app.head("/health")
def health_head() -> Response:
    response = readiness_response()
    return Response(status_code=response.status_code)
