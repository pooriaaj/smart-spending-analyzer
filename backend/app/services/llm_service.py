from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
USE_LLM_ASSISTANT = os.getenv("USE_LLM_ASSISTANT", "false").lower() == "true"

_client: OpenAI | None = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def llm_assistant_enabled() -> bool:
    return USE_LLM_ASSISTANT and _client is not None


def _safe_text(value: Any) -> str:
    if value is None:
        return "None"
    return str(value)


def build_finance_prompt(
    question: str,
    conversation_context: str,
    account_context: dict[str, Any],
) -> str:
    return f"""
You are a smart personal finance assistant inside a finance app.

Your job is to answer like a helpful financial coach, not like a dashboard widget.

You must:
- answer naturally and conversationally
- personalize the answer using the user's account data
- explain the likely reason behind spending or balance patterns
- give practical suggestions when useful
- avoid repeating the same phrases
- avoid always pushing the user to analytics
- only suggest navigation if it truly helps
- sometimes suggest no action at all
- sometimes suggest reviewing transactions instead of charts
- sometimes suggest educational resources outside the app when appropriate
- never invent account data
- if data is limited, say so honestly

You may choose one action type:
- none
- transactions
- dashboard
- analytics
- external_resource

External resources are allowed only when helpful for education or guidance, such as:
- budgeting basics
- debt reduction basics
- beginner finance learning
- financial literacy resources
Do not suggest random websites. Keep it general and reputable.

User question:
{question}

Recent conversation context:
{conversation_context or "None"}

ACCOUNT CONTEXT
-------------
Balance summary:
- Total income: {_safe_text(account_context.get("total_income"))}
- Total expenses: {_safe_text(account_context.get("total_expenses"))}
- Balance: {_safe_text(account_context.get("balance"))}

Monthly context:
- Current month: {_safe_text(account_context.get("current_month"))}
- Previous month: {_safe_text(account_context.get("previous_month"))}
- Current month expenses: {_safe_text(account_context.get("current_month_expenses"))}
- Previous month expenses: {_safe_text(account_context.get("previous_month_expenses"))}
- Expense change percent: {_safe_text(account_context.get("expense_change_percent"))}

Category context:
- Top expense category: {_safe_text(account_context.get("top_category"))}
- Top expense category amount: {_safe_text(account_context.get("top_category_amount"))}
- Top category share percent: {_safe_text(account_context.get("top_category_share_percent"))}
- Fastest-growing category: {_safe_text(account_context.get("primary_driver"))}

Overspending alerts:
{_safe_text(account_context.get("alerts_text"))}

Recent transactions:
{_safe_text(account_context.get("recent_transactions_text"))}

Category trend summary:
{_safe_text(account_context.get("trend_summary_text"))}

Your response MUST follow this exact format:

ANSWER:
<write a helpful natural answer>

SUPPORTING_POINTS:
- point 1
- point 2
- point 3

FOLLOWUPS:
- followup 1
- followup 2
- followup 3

ACTION_TYPE:
<one of: none, transactions, dashboard, analytics, external_resource>

ACTION_LABEL:
<short label or None>

ACTION_REASON:
<why this action helps or None>

ACTION_TARGET:
<for transactions/dashboard/analytics/external_resource provide a short target like category name, section name, or resource topic; otherwise None>
""".strip()


def parse_llm_response(text: str) -> dict[str, Any]:
    result = {
        "answer": "",
        "supporting_points": [],
        "suggested_followups": [],
        "action_type": "none",
        "action_label": None,
        "action_reason": None,
        "action_target": None,
    }

    section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        upper = line.upper()
        if upper == "ANSWER:":
            section = "answer"
            continue
        if upper == "SUPPORTING_POINTS:":
            section = "points"
            continue
        if upper == "FOLLOWUPS:":
            section = "followups"
            continue
        if upper == "ACTION_TYPE:":
            section = "action_type"
            continue
        if upper == "ACTION_LABEL:":
            section = "action_label"
            continue
        if upper == "ACTION_REASON:":
            section = "action_reason"
            continue
        if upper == "ACTION_TARGET:":
            section = "action_target"
            continue

        if section == "answer":
            result["answer"] = f'{result["answer"]} {line}'.strip()
        elif section == "points" and line.startswith("-"):
            result["supporting_points"].append(line[1:].strip())
        elif section == "followups" and line.startswith("-"):
            result["suggested_followups"].append(line[1:].strip())
        elif section == "action_type":
            result["action_type"] = line.lower()
        elif section == "action_label":
            result["action_label"] = None if line.lower() == "none" else line
        elif section == "action_reason":
            result["action_reason"] = None if line.lower() == "none" else line
        elif section == "action_target":
            result["action_target"] = None if line.lower() == "none" else line

    if not result["answer"]:
        result["answer"] = "I could not generate a useful answer from the language model."

    result["supporting_points"] = result["supporting_points"][:5]
    result["suggested_followups"] = result["suggested_followups"][:5]

    if result["action_type"] not in {
        "none",
        "transactions",
        "dashboard",
        "analytics",
        "external_resource",
    }:
        result["action_type"] = "none"

    return result


def build_account_context(
    snapshot: dict[str, Any],
    category_trends: dict[str, Any],
    overspending_alerts: dict[str, Any],
    recent_transactions: list[Any],
) -> dict[str, Any]:
    primary_driver = None
    if category_trends.get("top_increases"):
        primary_driver = category_trends["top_increases"][0]["category"]

    alerts = overspending_alerts.get("alerts", [])[:3]
    alerts_text = "\n".join(
        f"- [{alert['level']}] {alert['title']}: {alert['message']}"
        for alert in alerts
    ) or "- None"

    recent_transactions_text = "\n".join(
        f"- {tx.date} | {tx.type} | {tx.category} | {tx.description} | ${tx.amount:.2f}"
        for tx in recent_transactions[:5]
    ) or "- None"

    trend_summary = category_trends.get("summary", [])
    trend_summary_text = "\n".join(f"- {item}" for item in trend_summary) or "- None"

    context = dict(snapshot)
    context["primary_driver"] = primary_driver
    context["alerts_text"] = alerts_text
    context["recent_transactions_text"] = recent_transactions_text
    context["trend_summary_text"] = trend_summary_text
    return context


def generate_llm_assistant_response(
    question: str,
    conversation_context: str,
    snapshot: dict[str, Any],
    category_trends: dict[str, Any],
    overspending_alerts: dict[str, Any],
    recent_transactions: list[Any],
) -> dict[str, Any] | None:
    print("===== LLM DEBUG START =====")
    print("LLM enabled:", llm_assistant_enabled())
    print("Model:", OPENAI_MODEL)
    print("API key exists:", bool(OPENAI_API_KEY))
    print("Question:", question)

    if not llm_assistant_enabled():
        print("LLM disabled or client not initialized.")
        print("===== LLM DEBUG END =====")
        return None

    try:
        account_context = build_account_context(
            snapshot=snapshot,
            category_trends=category_trends,
            overspending_alerts=overspending_alerts,
            recent_transactions=recent_transactions,
        )

        prompt = build_finance_prompt(
            question=question,
            conversation_context=conversation_context,
            account_context=account_context,
        )

        print("Calling OpenAI...")
        response = _client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
        )

        print("OpenAI call succeeded.")
        print("Response preview:", response.output_text[:300] if response.output_text else "EMPTY")
        print("===== LLM DEBUG END =====")

        return parse_llm_response(response.output_text)

    except Exception as e:
        print("LLM ERROR:", str(e))
        print("===== LLM DEBUG END =====")
        return None