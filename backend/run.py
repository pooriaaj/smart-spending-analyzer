from __future__ import annotations

import os

import uvicorn


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def build_uvicorn_config() -> dict[str, object]:
    environment = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).lower()
    is_development = environment == "development"
    workers = 1 if is_development else _bounded_int_env("WEB_CONCURRENCY", 1, 1, 8)

    return {
        "app": "app.main:app",
        "host": os.getenv("HOST", "127.0.0.1" if is_development else "0.0.0.0"),
        "port": _bounded_int_env("PORT", 8000 if is_development else 10000, 1, 65535),
        "reload": is_development,
        "workers": workers,
        "proxy_headers": True,
        "forwarded_allow_ips": os.getenv("FORWARDED_ALLOW_IPS", "*"),
        "timeout_keep_alive": _bounded_int_env("UVICORN_TIMEOUT_KEEP_ALIVE", 5, 1, 120),
        "timeout_graceful_shutdown": _bounded_int_env("UVICORN_GRACEFUL_TIMEOUT", 30, 1, 120),
    }


if __name__ == "__main__":
    uvicorn.run(**build_uvicorn_config())
