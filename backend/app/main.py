from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routes.account_routes import router as account_router
from app.routes.analytics_routes import router as analytics_router
from app.routes.assistant_routes import router as assistant_router
from app.routes.auth_routes import router as auth_router
from app.routes.budget_routes import router as budget_router
from app.routes.transaction_routes import router as transaction_router
from app.routes.user_routes import router as user_router
from app.security import SecurityHeadersMiddleware, SimpleRateLimitMiddleware, get_allowed_origins
from app.services.database_maintenance_service import ensure_runtime_database_shape

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Smart Spending Analyzer API",
    version="1.0.0",
    description="Backend API for Smart Spending Analyzer",
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
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SimpleRateLimitMiddleware)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(account_router)
app.include_router(budget_router)
app.include_router(transaction_router)
app.include_router(analytics_router)
app.include_router(assistant_router)


@app.on_event("startup")
def on_startup() -> None:
    ensure_runtime_database_shape(engine)
    logger.info("Smart Spending Analyzer API started")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error at %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Smart Spending Analyzer API is running"}


@app.head("/")
def root_head() -> Response:
    return Response(status_code=200)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.head("/health")
def health_head() -> Response:
    return Response(status_code=200)
