from __future__ import annotations

import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from html import escape
import json


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
    return bool(_resend_is_configured() or _smtp_is_configured())


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    if not password_reset_email_is_configured():
        logger.info("Password reset email skipped because no email provider is configured.")
        return False

    if _resend_is_configured():
        return _send_password_reset_email_with_resend(to_email, reset_url)

    return _send_password_reset_email_with_smtp(to_email, reset_url)


def _smtp_is_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"))


def _resend_is_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY") and _from_email())


def _from_email() -> str:
    return os.getenv("EMAIL_FROM") or os.getenv("RESEND_FROM_EMAIL") or os.getenv("SMTP_FROM_EMAIL", "")


def _from_name() -> str:
    return os.getenv("EMAIL_FROM_NAME") or os.getenv("SMTP_FROM_NAME", "Smart Spending Analyzer")


def _password_reset_text(reset_url: str) -> str:
    return "\n".join(
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


def _password_reset_html(reset_url: str) -> str:
    safe_reset_url = escape(reset_url, quote=True)
    return f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#111827">
      <h2>Reset your password</h2>
      <p>Use this secure link to reset your Smart Spending Analyzer password:</p>
      <p><a href="{safe_reset_url}">Reset password</a></p>
      <p>This link expires in 30 minutes. If you did not request it, you can ignore this email.</p>
    </div>
    """.strip()


def _send_password_reset_email_with_smtp(to_email: str, reset_url: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    port = _env_int("SMTP_PORT", 587)
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_email = _from_email()
    from_name = _from_name()
    use_tls = _env_bool("SMTP_USE_TLS", True)
    timeout_seconds = _env_int("SMTP_TIMEOUT_SECONDS", 10)

    message = EmailMessage()
    message["Subject"] = "Reset your Smart Spending Analyzer password"
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.set_content(_password_reset_text(reset_url))

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


def _send_password_reset_email_with_resend(to_email: str, reset_url: str) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "")
    from_email = _from_email()
    from_name = _from_name()
    timeout_seconds = _env_int("EMAIL_TIMEOUT_SECONDS", 10)
    payload = {
        "from": f"{from_name} <{from_email}>",
        "to": [to_email],
        "subject": "Reset your Smart Spending Analyzer password",
        "text": _password_reset_text(reset_url),
        "html": _password_reset_html(reset_url),
    }
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= response.status < 300
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        logger.exception("Password reset email could not be sent with Resend.")
        return False
