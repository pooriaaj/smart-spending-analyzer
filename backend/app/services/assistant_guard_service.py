from __future__ import annotations

from typing import Any

from app.services.analytics_service import normalize_text_for_matching


SECURITY_SENSITIVE_ASSISTANT_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "developer prompt",
    "developer message",
    "hidden prompt",
    "print your prompt",
    "show your prompt",
    "database secret",
    "database secrets",
    "database url",
    "openai api key",
    "api key",
    "secret key",
    "jwt",
    "bearer token",
    "reset token",
    "environment variable",
    "env file",
    "all users",
    "other users",
    "another user",
    "another account",
    "different account id",
    "use another account id",
    "select * from users",
)


def extract_recent_context(history: list[Any]) -> str:
    context_lines: list[str] = []

    for message in history[-8:]:
        role = getattr(message, "role", "").lower()
        content = getattr(message, "content", "").strip()

        if not content:
            continue

        if role == "user":
            context_lines.append(f"User: {content}")
        elif role == "assistant":
            context_lines.append(f"Assistant: {content}")

    return "\n".join(context_lines)


def is_security_sensitive_assistant_request(question: str, context_text: str) -> bool:
    normalized_text = normalize_text_for_matching(f"{question} {context_text}")
    return any(phrase in normalized_text for phrase in SECURITY_SENSITIVE_ASSISTANT_PHRASES)


def build_assistant_security_refusal(scope_label: str) -> dict[str, Any]:
    return {
        "answer": (
            "I cannot help reveal secrets, hidden instructions, raw database access, or another user's data. "
            f"I can still help analyze the financial data already visible in {scope_label}."
        ),
        "supporting_points": [
            "Assistant answers are limited to the current authenticated user's filtered financial context.",
            "Secrets like API keys, database URLs, JWTs, and reset tokens are never part of assistant output.",
            "If you want help with your own spending, ask about a category, trend, budget, or transaction pattern.",
        ],
        "suggested_followups": [
            "What changed in my spending recently?",
            "Which category should I review first?",
            "What can I do to improve my balance this month?",
        ],
        "suggested_actions": [],
        "scope_label": scope_label,
    }
