from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routes.analytics_routes import router as analytics_router
from app.routes.auth_routes import router as auth_router
from app.routes.transaction_routes import router as transaction_router

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

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

allowed_origins = [
    "http://localhost:5173",
    frontend_url,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(allowed_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(transaction_router)
app.include_router(analytics_router)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Smart Spending Analyzer API started")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Smart Spending Analyzer API is running"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}