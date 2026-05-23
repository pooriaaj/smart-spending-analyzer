from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage


logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def password_reset_email_is_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"))


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    if not password_reset_email_is_configured():
        logger.info("Password reset email skipped because SMTP is not configured.")
        return False

    host = os.getenv("SMTP_HOST", "")
    port = _env_int("SMTP_PORT", 587)
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("SMTP_FROM_EMAIL", "")
    from_name = os.getenv("SMTP_FROM_NAME", "Smart Spending Analyzer")
    use_tls = _env_bool("SMTP_USE_TLS", True)
    timeout_seconds = _env_int("SMTP_TIMEOUT_SECONDS", 10)

    message = EmailMessage()
    message["Subject"] = "Reset your Smart Spending Analyzer password"
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "Hi,",
                "",
                "Use this secure link to reset your password:",
                reset_url,
                "",
                "This link expires in 30 minutes. If you did not request it, you can ignore this email.",
                "",
                "Smart Spending Analyzer",
            ]
        )
    )

    try:
        with smtplib.SMTP(host, port, timeout=timeout_seconds) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception:
        logger.exception("Password reset email could not be sent.")
        return False

    return True
