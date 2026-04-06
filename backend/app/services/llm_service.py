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

USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
LOCAL_LLM_PROVIDER = os.getenv("LOCAL_LLM_PROVIDER", "ollama").lower()
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "ollama")

_openai_client: OpenAI | None = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_local_client: OpenAI | None = (
    OpenAI(base_url=LOCAL_LLM_BASE_URL, api_key=LOCAL_LLM_API_KEY)
    if USE_LOCAL_LLM and LOCAL_LLM_PROVIDER == "ollama"
    else None
)


def llm_assistant_enabled() -> bool:
    return USE_LLM_ASSISTANT and (_local_client is not None or _openai_client is not None)


def _safe_text(value: Any) -> str:
    if value is None:
        return "None"
    return str(value)


def get_mode_instructions(mode: str) -> str:
    normalized = (mode or "balanced").lower()

    if normalized == "strict":
        return """
Personality mode: STRICT

Behavior:
- be direct, disciplined, and clear
- call out overspending plainly
- focus on accountability and prioritization
- do not be rude, but do not soften avoidable financial mistakes
- keep praise limited and earned
- emphasize consequences of poor spending patterns
""".strip()

    if normalized == "coach":
        return """
Personality mode: COACH

Behavior:
- be supportive, motivating, and practical
- focus on progress, encouragement, and next steps
- frame advice as achievable improvements
- keep the user engaged and hopeful
- still be honest about risks, but present them constructively
""".strip()

    return """
Personality mode: BALANCED

Behavior:
- be neutral, practical, and helpful
- combine clarity with calm guidance
- explain issues honestly without being harsh
- avoid sounding robotic or overly emotional
""".strip()


def build_finance_prompt(
    question: str,
    conversation_context: str,
    account_context: dict[str, Any],
    mode: str,
) -> str:
    mode_instructions = get_mode_instructions(mode)

    return f"""
You are a smart personal finance assistant inside a finance app.

{mode_instructions}

Your role:
- answer naturally, like a helpful human assistant
- use the user's account data to explain what is happening
- answer the exact question asked, not a generic overview
- understand follow-up questions using the recent conversation context
- avoid repeating the same phrasing in every answer
- do not always send the user to analytics
- sometimes recommend transactions first
- sometimes recommend dashboard or analytics
- sometimes recommend no action at all
- sometimes recommend an outside learning resource when the user wants education, not just account analysis
- never invent data
- if data is limited, say so honestly

Reasoning policy:
- if the user asks "why", explain the likely driver from categories, spending change, alerts, and recent transactions
- if the user asks what to review first, prefer transactions over charts when the goal is root-cause investigation
- if the user asks for learning or guidance, an external resource is allowed
- if the user asks about their money going somewhere, focus on top categories and recent spending
- if the user asks about risk, focus on alerts and spending concentration
- if the user asks a follow-up, use the recent conversation context before changing topics

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

Return this exact format:

ANSWER:
<write a natural helpful answer in 2 to 5 sentences>

SUPPORTING_POINTS:
- point 1
- point 2
- point 3

FOLLOWUPS:
- short followup 1
- short followup 2
- short followup 3

ACTION_TYPE:
<one of: none, transactions, dashboard, analytics, external_resource>

ACTION_LABEL:
<short action label or None>

ACTION_REASON:
<brief reason or None>

ACTION_TARGET:
<target like category, section, or topic; otherwise None>
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
            point = line[1:].strip()
            if point and point not in result["supporting_points"]:
                result["supporting_points"].append(point)
        elif section == "followups" and line.startswith("-"):
            followup = line[1:].strip()
            if followup and followup not in result["suggested_followups"]:
                result["suggested_followups"].append(followup)
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


def _call_model(client: OpenAI, model_name: str, prompt: str) -> dict[str, Any] | None:
    response = client.responses.create(
        model=model_name,
        input=prompt,
    )
    return parse_llm_response(response.output_text)


def generate_llm_assistant_response(
    question: str,
    conversation_context: str,
    snapshot: dict[str, Any],
    category_trends: dict[str, Any],
    overspending_alerts: dict[str, Any],
    recent_transactions: list[Any],
    mode: str = "balanced",
) -> dict[str, Any] | None:
    if not llm_assistant_enabled():
        return None

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
        mode=mode,
    )

    try:
        if _local_client is not None:
            return _call_model(_local_client, LOCAL_LLM_MODEL, prompt)

        if _openai_client is not None:
            return _call_model(_openai_client, OPENAI_MODEL, prompt)

    except Exception:
        return None

    return None