from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def build_engine_kwargs(database_url: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "future": True,
    }
    driver_name = make_url(database_url).drivername
    if driver_name.startswith("sqlite"):
        return kwargs

    kwargs.update(
        {
            "pool_size": _bounded_int_env("DB_POOL_SIZE", 5, 1, 50),
            "max_overflow": _bounded_int_env("DB_MAX_OVERFLOW", 10, 0, 100),
            "pool_timeout": _bounded_int_env("DB_POOL_TIMEOUT_SECONDS", 30, 1, 120),
            "pool_recycle": _bounded_int_env("DB_POOL_RECYCLE_SECONDS", 1800, 60, 7200),
        }
    )
    return kwargs


engine = create_engine(DATABASE_URL, **build_engine_kwargs(DATABASE_URL))

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)

Base = declarative_base()
