from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Transaction
from app.services.analytics_service import (
    build_financial_snapshot,
    build_future_balance_simulation,
    build_future_simulation_recommendations,
    build_recurring_savings_opportunities,
    build_saved_scenario_projection_snapshots,
    format_category_label,
    format_currency,
    format_signed_currency,
    get_account_comparison_snapshot,
    get_budget_progress_snapshot,
    get_category_trends,
    get_overspending_alerts,
    get_recent_transactions,
    get_recurring_expense_patterns,
    get_summary,
    get_top_categories_with_transactions,
    get_top_expense_categories,
    get_transactions_for_category,
    normalize_text_for_matching,
)
from app.services.assistant_guard_service import (
    build_assistant_security_refusal,
    extract_recent_context,
    is_security_sensitive_assistant_request,
)
from app.services.budget_metrics import build_budget_action_insights, get_default_budget_month
from app.services.llm_service import generate_llm_assistant_response
from app.services.saved_scenario_service import list_saved_scenarios
from app.services.transaction_service import get_transaction_data_quality_report


def build_data_quality_supporting_point(data_quality: dict[str, Any]) -> str | None:
    quality_level = str(data_quality.get("quality_level") or "empty").lower()
    if quality_level == "high":
        return None

    score = float(data_quality.get("quality_score") or 0.0)
    action_count = len(data_quality.get("actions") or [])
    message = str(data_quality.get("message") or "Review transaction data before relying on predictions.")
    return (
        f"Data quality: {quality_level} ({score * 100:.0f}% confidence). "
        f"{message} Review items: {action_count}."
    )


def get_saved_scenario_risk_rank(risk_level: str | None) -> int:
    if risk_level == "healthy":
        return 2
    if risk_level == "watch":
        return 1
    return 0


def detect_saved_scenario_comparison_focus(question: str, context_text: str) -> str:
    normalized_text = normalize_text_for_matching(f"{context_text} {question}")

    if any(
        phrase in normalized_text
        for phrase in [
            "safest",
            "safe plan",
            "safer",
            "lowest risk",
            "least risky",
            "most stable",
            "risk",
        ]
    ):
        return "risk"

    if any(
        phrase in normalized_text
        for phrase in [
            "monthly net",
            "cash flow",
            "net change",
            "per month",
        ]
    ):
        return "monthly_net"

    if any(
        phrase in normalized_text
        for phrase in [
            "target",
            "goal",
            "reach",
            "hit",
        ]
    ):
        return "goal"

    return "end_balance"


def is_saved_scenario_plan_comparison_question(question: str, context_text: str) -> bool:
    normalized_text = normalize_text_for_matching(f"{context_text} {question}")

    return any(
        phrase in normalized_text
        for phrase in [
            "which plan",
            "best plan",
            "better plan",
            "strongest plan",
            "safest plan",
            "which one is safest",
            "which one is stronger",
            "which one is best",
            "best cash flow plan",
            "best monthly net plan",
            "closest to my goal",
            "closest to my target",
            "goal leader",
        ]
    )


def build_saved_scenario_comparison_key(
    scenario: dict[str, Any],
    comparison_focus: str,
) -> tuple[Any, ...]:
    projected_end_balance = float(scenario["projected_end_balance"])
    monthly_net_change = float(scenario["monthly_net_change"])
    risk_rank = get_saved_scenario_risk_rank(scenario.get("risk_level"))
    lowest_balance = float(scenario.get("lowest_balance") or 0.0)
    goal_balance = scenario.get("goal_balance")
    goal_gap_amount = scenario.get("goal_gap_amount")
    has_goal = goal_balance is not None
    goal_achieved = bool(has_goal and goal_gap_amount is not None and goal_gap_amount <= 0)
    goal_progress_key = (
        -float(goal_gap_amount)
        if goal_gap_amount is not None
        else float("-inf")
    )

    if comparison_focus == "risk":
        return (
            risk_rank,
            lowest_balance,
            projected_end_balance,
            monthly_net_change,
            scenario["name"].lower(),
        )

    if comparison_focus == "monthly_net":
        return (
            monthly_net_change,
            risk_rank,
            projected_end_balance,
            scenario["name"].lower(),
        )

    if comparison_focus == "goal":
        return (
            1 if has_goal else 0,
            1 if goal_achieved else 0,
            goal_progress_key,
            projected_end_balance,
            monthly_net_change,
            scenario["name"].lower(),
        )

    return (
        projected_end_balance,
        monthly_net_change,
        risk_rank,
        scenario["name"].lower(),
    )


def build_saved_scenario_supporting_point(
    scenario: dict[str, Any],
    comparison_focus: str = "end_balance",
) -> str:
    point = (
        f"{scenario['name']}: ends at {format_currency(scenario['projected_end_balance'])}, "
        f"net {format_currency(scenario['monthly_net_change'])}/month, risk {scenario['risk_level']}"
    )

    if comparison_focus == "risk":
        point += f", floor {format_currency(scenario.get('lowest_balance') or 0.0)}"

    if scenario.get("goal_balance") is not None:
        goal_balance = float(scenario["goal_balance"])
        goal_gap_amount = scenario.get("goal_gap_amount")
        if goal_gap_amount is not None and goal_gap_amount <= 0:
            point += f". Goal met: target {format_currency(goal_balance)}"
        elif goal_gap_amount is not None:
            point += (
                f". Goal gap: {format_currency(float(goal_gap_amount))} short of "
                f"{format_currency(goal_balance)}"
            )
        else:
            point += f". Target: {format_currency(goal_balance)}"

    if scenario["goal_note"]:
        point += f". {scenario['goal_note']}"
    if scenario["one_time_event_amount"] is not None and scenario["one_time_event_month"]:
        point += (
            f". Event: {scenario['one_time_event_label']} in {scenario['one_time_event_month']} "
            f"for {format_signed_currency(scenario['one_time_event_amount'])}"
        )

    return point


def build_saved_scenario_portfolio_summary(
    saved_scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    strongest = (
        sorted(
            saved_scenarios,
            key=lambda item: build_saved_scenario_comparison_key(item, "end_balance"),
            reverse=True,
        )[0]
        if saved_scenarios
        else None
    )
    safest = (
        sorted(
            saved_scenarios,
            key=lambda item: build_saved_scenario_comparison_key(item, "risk"),
            reverse=True,
        )[0]
        if saved_scenarios
        else None
    )
    monthly_net_leader = (
        sorted(
            saved_scenarios,
            key=lambda item: build_saved_scenario_comparison_key(item, "monthly_net"),
            reverse=True,
        )[0]
        if saved_scenarios
        else None
    )
    goal_candidates = [item for item in saved_scenarios if item.get("goal_balance") is not None]
    goal_leader = (
        sorted(
            goal_candidates,
            key=lambda item: build_saved_scenario_comparison_key(item, "goal"),
            reverse=True,
        )[0]
        if goal_candidates
        else None
    )

    return {
        "total": len(saved_scenarios),
        "healthy_count": sum(1 for item in saved_scenarios if item.get("risk_level") == "healthy"),
        "attention_count": sum(
            1 for item in saved_scenarios if item.get("risk_level") in {"watch", "high"}
        ),
        "goal_count": len(goal_candidates),
        "event_count": sum(1 for item in saved_scenarios if item.get("one_time_event_amount") is not None),
        "strongest": strongest,
        "safest": safest,
        "monthly_net_leader": monthly_net_leader,
        "goal_leader": goal_leader,
    }

def get_distinct_categories(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> list[str]:
    query = db.query(Transaction.category).filter(Transaction.owner_id == user_id)

    if account_id is not None:
        query = query.filter(Transaction.account_id == account_id)

    categories = {
        (row[0] or "").strip()
        for row in query.distinct().all()
        if row[0] and str(row[0]).strip()
    }

    return sorted(
        categories,
        key=lambda item: (-len(normalize_text_for_matching(item)), item.lower()),
    )


def detect_focus_category(
    question: str,
    context_text: str,
    categories: list[str],
) -> str | None:
    normalized_text = f" {normalize_text_for_matching(f'{context_text} {question}')} "

    for category in categories:
        normalized_category = normalize_text_for_matching(category)
        if not normalized_category:
            continue

        variants = {normalized_category}
        if normalized_category.endswith("ies") and len(normalized_category) > 3:
            variants.add(f"{normalized_category[:-3]}y")
        elif normalized_category.endswith("s") and len(normalized_category) > 1:
            variants.add(normalized_category[:-1])

        if any(f" {variant} " in normalized_text for variant in variants if variant):
            return category

    return None


def detect_named_saved_scenarios(
    question: str,
    context_text: str,
    saved_scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_text = f" {normalize_text_for_matching(f'{context_text} {question}')} "
    matches: list[dict[str, Any]] = []

    for scenario in sorted(saved_scenarios, key=lambda item: len(item["name"]), reverse=True):
        normalized_name = normalize_text_for_matching(scenario["name"])
        if not normalized_name:
            continue

        if f" {normalized_name} " in normalized_text:
            matches.append(scenario)

    deduped: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for scenario in matches:
        if scenario["id"] in seen_ids:
            continue
        deduped.append(scenario)
        seen_ids.add(scenario["id"])

    return deduped


def build_category_focus_snapshot(
    db: Session,
    user_id: int,
    category: str,
    snapshot: dict[str, Any],
    account_id: int | None = None,
) -> dict[str, Any]:
    overall_summary = get_summary(
        db,
        user_id,
        category=category,
        account_id=account_id,
    )
    focus_type = (
        "income"
        if overall_summary["total_income"] > overall_summary["total_expenses"]
        else "expense"
    )
    total_amount = (
        float(overall_summary["total_income"])
        if focus_type == "income"
        else float(overall_summary["total_expenses"])
    )

    current_month = snapshot.get("current_month")
    previous_month = snapshot.get("previous_month")

    current_summary = (
        get_summary(
            db,
            user_id,
            month=current_month,
            category=category,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if current_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )
    previous_summary = (
        get_summary(
            db,
            user_id,
            month=previous_month,
            category=category,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if previous_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )

    current_month_amount = (
        float(current_summary["total_income"])
        if focus_type == "income"
        else float(current_summary["total_expenses"])
    )
    previous_month_amount = (
        float(previous_summary["total_income"])
        if focus_type == "income"
        else float(previous_summary["total_expenses"])
    )

    change_amount = current_month_amount - previous_month_amount
    change_percent = None
    if previous_month_amount > 0:
        change_percent = (change_amount / previous_month_amount) * 100

    month_scope_summary = (
        get_summary(
            db,
            user_id,
            month=current_month,
            transaction_type=focus_type,
            account_id=account_id,
        )
        if current_month
        else {"total_income": 0.0, "total_expenses": 0.0}
    )
    month_scope_total = (
        float(month_scope_summary["total_income"])
        if focus_type == "income"
        else float(month_scope_summary["total_expenses"])
    )
    current_share_percent = None
    if month_scope_total > 0 and current_month_amount > 0:
        current_share_percent = (current_month_amount / month_scope_total) * 100

    recent_transactions = get_transactions_for_category(
        db,
        user_id,
        category,
        account_id=account_id,
        limit=3,
    )

    return {
        "category": category,
        "transaction_type": focus_type,
        "total_amount": total_amount,
        "current_month": current_month,
        "previous_month": previous_month,
        "current_month_amount": current_month_amount,
        "previous_month_amount": previous_month_amount,
        "change_amount": change_amount,
        "change_percent": change_percent,
        "current_share_percent": current_share_percent,
        "recent_transactions": recent_transactions,
        "is_top_category": snapshot.get("top_category") == category,
    }


def build_category_focus_supporting_points(
    focus_snapshot: dict[str, Any],
) -> list[str]:
    category = focus_snapshot["category"]
    current_month = focus_snapshot["current_month"]
    previous_month = focus_snapshot["previous_month"]

    points = [
        f"{category} total in this scope: {format_currency(focus_snapshot['total_amount'])}",
    ]

    if current_month:
        points.append(
            f"{current_month}: {format_currency(focus_snapshot['current_month_amount'])}"
        )

    if previous_month and focus_snapshot["previous_month_amount"] > 0:
        direction = "up" if focus_snapshot["change_amount"] >= 0 else "down"
        points.append(
            f"Month-over-month: {direction} {format_currency(abs(focus_snapshot['change_amount']))} from {previous_month}"
        )

    if focus_snapshot["current_share_percent"] is not None:
        share_label = "income" if focus_snapshot["transaction_type"] == "income" else "spending"
        points.append(
            f"{category} makes up {focus_snapshot['current_share_percent']:.1f}% of current-month {share_label}"
        )

    if focus_snapshot["recent_transactions"]:
        recent_text = ", ".join(
            f"{tx.description} ({format_currency(tx.amount)})"
            for tx in focus_snapshot["recent_transactions"]
        )
        points.append(f"Recent matching transactions: {recent_text}")

    return points[:5]


def build_category_focus_answer(
    intent: str,
    mode: str,
    focus_snapshot: dict[str, Any],
    top_category: str | None,
) -> str:
    category = focus_snapshot["category"]
    total_amount = format_currency(focus_snapshot["total_amount"])
    current_month = focus_snapshot["current_month"]
    current_month_amount = format_currency(focus_snapshot["current_month_amount"])
    change_amount = focus_snapshot["change_amount"]
    change_percent = focus_snapshot["change_percent"]
    is_expense = focus_snapshot["transaction_type"] == "expense"
    recent_transactions = focus_snapshot["recent_transactions"]

    change_text = ""
    if current_month:
        change_text = f" In {current_month}, it is {current_month_amount}."
    if change_percent is not None:
        direction = "up" if change_amount >= 0 else "down"
        change_text += f" That is {direction} {abs(change_percent):.1f}% from the previous month."

    if intent == "category_transactions" or intent == "recent":
        recent_hint = (
            f" Recent items include {', '.join(tx.description for tx in recent_transactions[:2])}."
            if recent_transactions
            else ""
        )
        if mode == "strict":
            return f"{category} is where the detail is.{change_text or f' It totals {total_amount} in this scope.'}{recent_hint}"
        if mode == "coach":
            return f"{category} is a good place to zoom in.{change_text or f' It totals {total_amount} in this scope.'}{recent_hint}"
        return f"Here is the focused view for {category}. It totals {total_amount} in this scope.{change_text}{recent_hint}"

    if intent in {"saving_advice", "spending_change", "driver", "alerts"} and is_expense:
        if mode == "strict":
            return f"{category} is worth reviewing closely. It totals {total_amount} in this scope.{change_text}"
        if mode == "coach":
            return f"{category} looks like a practical place to focus. It totals {total_amount} in this scope.{change_text}"
        return f"{category} is a meaningful spending category here. It totals {total_amount} in this scope.{change_text}"

    if focus_snapshot["is_top_category"]:
        return f"{category} is currently your top category in this scope at {total_amount}.{change_text}"

    comparator = f" {top_category} is currently higher." if top_category and top_category != category else ""
    return f"{category} totals {total_amount} in this scope.{change_text}{comparator}"


def classify_question(question: str, context_text: str) -> str:
    text = f"{context_text} {question}".lower().strip()
    has_month_horizon = re.search(r"\d+\s+month", text) is not None
    has_goal_amount = parse_target_balance(text) is not None
    has_one_time_event = (
        parse_one_time_event_amount(text) is not None
        and parse_one_time_event_offset(text) is not None
    )

    if any(
        phrase in text
        for phrase in [
            "future balance",
            "simulate",
            "simulation",
            "forecast my balance",
            "project my balance",
            "months from now",
            "next few months",
            "what will my balance look like",
        ]
    ):
        return "future_balance"

    if has_month_horizon and has_goal_amount and any(
        phrase in text
        for phrase in [
            "reach",
            "get to",
            "grow to",
            "save each month",
            "need to save",
            "target balance",
            "end with",
        ]
    ):
        return "future_balance"

    if has_one_time_event and any(
        phrase in text
        for phrase in [
            "what if",
            "happen",
            "look like",
            "forecast",
            "project",
            "affect",
            "impact",
            "balance",
        ]
    ):
        return "future_balance"

    if any(
        phrase in text
        for phrase in [
            "should i review charts or transactions first",
            "charts or transactions first",
            "review charts or transactions",
            "what should i review first",
            "where should i start",
        ]
    ):
        return "review_path"

    if "compare" in text and "account" in text:
        return "account_comparison"

    if any(
        phrase in text
        for phrase in [
            "saved scenario",
            "saved scenarios",
            "saved plan",
            "saved plans",
            "saved simulator",
            "saved simulation",
        ]
    ):
        if any(
            phrase in text
            for phrase in [
                "compare",
                "best",
                "better",
                "strongest",
                "which one",
                "which plan",
                "safest",
                "lowest risk",
                "least risky",
                "most stable",
                "goal",
                "target",
                "cash flow",
                "monthly net",
            ]
        ):
            return "saved_scenario_compare"
        return "saved_scenario_list"

    if any(
        phrase in text
        for phrase in [
            "savings scenario",
            "saving scenario",
            "simulator plan",
            "scenario should i try",
            "which plan should i try",
            "best plan to try",
            "best savings plan",
            "best scenario to try",
        ]
    ):
        return "savings_scenario"

    if any(
        phrase in text
        for phrase in [
            "subscription",
            "subscriptions",
            "recurring charge",
            "recurring charges",
            "recurring expense",
            "recurring expenses",
            "monthly charges",
            "memberships",
        ]
    ):
        return "recurring_expenses"

    if any(
        phrase in text
        for phrase in [
            "compare accounts",
            "which account",
            "account is driving",
            "driving my spending by account",
            "highest spending account",
            "most expensive account",
        ]
    ):
        return "account_comparison"

    if any(
        phrase in text
        for phrase in [
            "top 3",
            "top three",
            "biggest 3",
            "largest 3",
            "top categories",
            "where is my money going",
            "where does my money go",
        ]
    ):
        return "top_categories_multi"

    if any(
        phrase in text
        for phrase in [
            "their transactions",
            "show transactions",
            "show me transactions",
            "category transactions",
            "transactions for category",
        ]
    ):
        return "category_transactions"

    if any(word in text for word in ["balance", "left over", "how much do i have"]):
        return "balance"

    if any(word in text for word in ["top expense", "top category", "biggest category", "most spent"]):
        return "top_category"

    if any(
        phrase in text
        for phrase in [
            "budget",
            "budgets",
            "on track",
            "over budget",
            "left in my budget",
            "remaining budget",
            "budget limit",
            "close to the limit",
            "budget forecast",
            "projected to go over",
            "projected budget",
        ]
    ):
        return "budget_status"

    if any(word in text for word in ["increase", "decrease", "trend", "last month", "this month", "overspend", "spending change"]):
        return "spending_change"

    if any(word in text for word in ["save", "saving", "advice", "reduce", "cut spending", "budget"]):
        return "saving_advice"

    if any(word in text for word in ["summary", "summarize", "overview", "my finances"]):
        return "summary"

    if any(word in text for word in ["driving this", "which category", "what caused", "reason for increase"]):
        return "driver"

    if any(word in text for word in ["alert", "warning", "problem", "risk"]):
        return "alerts"

    if any(word in text for word in ["recent", "latest transactions", "last transactions"]):
        return "recent"

    if any(word in text for word in ["youtube", "google", "resource", "article", "learn more", "guide"]):
        return "education"

    return "general"


def build_assistant_actions(
    snapshot: dict[str, Any],
    intent: str,
    account_id: int | None = None,
    driver_category: str | None = None,
    focus_category: str | None = None,
    focus_transaction_type: str = "expense",
    simulation_months: int | None = None,
    simulation_target_balance: float | None = None,
    simulation_income_adjustment: float | None = None,
    simulation_expense_adjustment: float | None = None,
    simulation_event_month_offset: int | None = None,
    simulation_event_amount: float | None = None,
    simulation_event_label: str | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    top_category = snapshot["top_category"]
    current_month = snapshot["current_month"]
    target_category = focus_category or driver_category or top_category
    target_transaction_type = focus_transaction_type if focus_category else "expense"
    target_label_suffix = "transactions" if target_transaction_type == "income" else "expenses"
    data_quality_level = str(snapshot.get("data_quality_level") or "high").lower()

    if data_quality_level in {"empty", "low", "medium"}:
        actions.append(
            {
                "label": "Review data quality",
                "page": "transactions",
                "section": "review",
                "account_id": account_id,
            }
        )

    if intent == "balance":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
                "account_id": account_id,
            }
        )

    elif intent == "future_balance":
        actions.append(
            {
                "label": "Open simulator",
                "page": "simulator",
                "months_ahead": simulation_months,
                "account_id": account_id,
                "target_balance": simulation_target_balance,
                "income_adjustment": simulation_income_adjustment,
                "expense_adjustment": simulation_expense_adjustment,
                "event_month_offset": simulation_event_month_offset,
                "event_amount": simulation_event_amount,
                "event_label": simulation_event_label,
            }
        )
        actions.append(
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": snapshot.get("current_month") or get_default_budget_month(),
                "account_id": account_id,
            }
        )

    elif intent == "account_comparison":
        actions.append(
            {
                "label": "Open accounts",
                "page": "accounts",
            }
        )

    elif intent == "top_category":
        if target_category:
            actions.append(
                {
                    "label": f"Open {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )
            actions.append(
                {
                    "label": "View category ranking",
                    "page": "analytics",
                    "section": "categories",
                    "account_id": account_id,
                }
            )

    elif intent == "spending_change":
        actions.append(
            {
                "label": "Inspect overspending alerts",
                "page": "analytics",
                "section": "alerts",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "View category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

    elif intent == "saving_advice":
        actions.append(
            {
                "label": "Open spending insights",
                "page": "analytics",
                "section": "insights",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": snapshot.get("current_month"),
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Review {target_category} transactions",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )

    elif intent == "summary":
        actions.append(
            {
                "label": "Open monthly summary",
                "page": "analytics",
                "section": "monthly",
                "month": current_month,
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "View all transactions",
                "page": "transactions",
                "account_id": account_id,
            }
        )

    elif intent == "driver":
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )
        if target_category:
            actions.append(
                {
                    "label": f"Inspect {target_category} {target_label_suffix}",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

    elif intent == "alerts":
        actions.append(
            {
                "label": "Open overspending alerts",
                "page": "analytics",
                "section": "alerts",
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )

    elif intent == "recent":
        if target_category:
            actions.append(
                {
                    "label": f"Open {target_category} transactions",
                    "page": "transactions",
                    "category": target_category,
                    "transaction_type": target_transaction_type,
                    "account_id": account_id,
                }
            )
        else:
            actions.append(
                {
                    "label": "View all transactions",
                    "page": "transactions",
                    "account_id": account_id,
                }
            )

    elif intent == "general" and target_category:
        actions.append(
            {
                "label": f"Open {target_category} transactions",
                "page": "transactions",
                "category": target_category,
                "transaction_type": target_transaction_type,
                "account_id": account_id,
            }
        )
        actions.append(
            {
                "label": "Open category trends",
                "page": "analytics",
                "section": "trends",
                "account_id": account_id,
            }
        )

    return actions[:3]


def generate_mode_intro(mode: str) -> str:
    if mode == "strict":
        return "Strict view:"
    if mode == "coach":
        return "Coach view:"
    return ""


def generate_dynamic_followups(
    intent: str,
    mode: str,
    top_category: str | None,
    driver_category: str | None,
    focus_category: str | None = None,
) -> list[str]:
    if focus_category:
        return [
            f"Show me recent {focus_category} transactions",
            f"How has {focus_category} changed month to month?",
            f"How can I improve my {focus_category} spending?",
        ]

    if intent == "future_balance":
        return [
            "What if my monthly expenses go up by 200?",
            "What if I increase my income by 500 a month?",
            "What if I have a 1200 repair in 2 months?",
            "Should I build next month's budgets from this pace?",
        ]

    if intent == "account_comparison":
        return [
            "Which account should I review first?",
            "Show me transactions from the highest-spending account.",
            "Which account has the healthiest balance?",
        ]

    if intent == "budget_status":
        return [
            "Which budget is closest to the limit?",
            "Which budget is projected to go over?",
            "How can I get back on track?",
        ]

    if intent == "recurring_expenses":
        return [
            "Which recurring charge costs me the most each year?",
            "Which subscriptions should I review first?",
            "Did any recurring charge increase lately?",
            "What happens if I cancel my biggest subscription?",
            "Open my transactions",
        ]

    if intent == "savings_scenario":
        return [
            "Which savings scenario should I try first?",
            "Open the strongest simulator plan",
            "What happens if I cancel my biggest subscription?",
        ]

    if mode == "strict":
        if intent in {"spending_change", "driver", "alerts"}:
            return [
                "What should I cut first?",
                "Show me the transactions causing this.",
                f"Is {driver_category or top_category or 'this category'} the main problem?",
            ]
        return [
            "What is hurting my budget most?",
            "Where should I cut first?",
            "Show me the transactions behind this.",
        ]

    if mode == "coach":
        if intent in {"saving_advice", "summary"}:
            return [
                "What is one easy improvement I can make this week?",
                "Where can I save without feeling restricted?",
                "Show me the best place to start improving.",
            ]
        return [
            "What is one smart next step?",
            "Where can I improve gradually?",
            "Show me the best starting point.",
        ]

    if intent == "top_categories_multi":
        return [
            "Show me their transactions",
            "Which one is growing fastest?",
            "How can I reduce them?",
        ]
    if intent == "category_transactions":
        return [
            "Which category is driving my spending most?",
            "How can I reduce these expenses?",
            "Open those transactions",
        ]
    if intent == "spending_change":
        return [
            "What category caused the increase?",
            "Show me the recent transactions behind this.",
            "What should I review first?",
        ]
    if intent == "saving_advice":
        return [
            "Where should I start cutting back?",
            "Which category gives me the biggest savings opportunity?",
            "Show me the transactions I should review first.",
        ]
    return [
        "Show me my top 3 spending categories",
        "Show me their transactions",
        "Give me saving advice",
    ]


def build_driver_explanation(
    expense_change_percent: float | None,
    top_category: str | None,
    driver_category: str | None,
    recent_transactions: list[Any],
) -> list[str]:
    reasons: list[str] = []

    if expense_change_percent is not None:
        if expense_change_percent > 0:
            reasons.append(f"overall expenses increased by {expense_change_percent:.1f}%")
        elif expense_change_percent < 0:
            reasons.append(f"overall expenses decreased by {abs(expense_change_percent):.1f}%")

    if driver_category:
        reasons.append(f"{driver_category} appears to be the fastest-growing category")
    elif top_category:
        reasons.append(f"{top_category} is currently the biggest spending category")

    if recent_transactions:
        recent_labels = ", ".join(tx.description for tx in recent_transactions[:2])
        if recent_labels:
            reasons.append(f"recent transactions such as {recent_labels} may be contributing")

    return reasons


def parse_projection_months(question: str) -> int:
    match = re.search(r"(\d+)\s+month", question.lower())
    if not match:
        return 3

    return max(1, min(int(match.group(1)), 12))


def parse_target_balance(question: str) -> float | None:
    lowered = question.lower()
    patterns = [
        r"(?:reach|get to|grow to|balance of|balance at|target balance(?: of)?|end with)\s+\$?(\d+(?:,\d{3})*(?:\.\d+)?)",
        r"\$?(\d+(?:,\d{3})*(?:\.\d+)?)\s+(?:balance|saved)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1).replace(",", ""))

    return None


def parse_one_time_event_amount(question: str) -> float | None:
    lowered = question.lower()
    expense_keywords = [
        "trip",
        "vacation",
        "repair",
        "car repair",
        "purchase",
        "buy",
        "bill",
        "payment",
        "expense",
        "cost",
        "tuition",
        "wedding",
        "medical",
    ]
    income_keywords = [
        "bonus",
        "refund",
        "tax refund",
        "windfall",
        "sale",
        "sell",
        "rebate",
        "gift",
        "payout",
    ]
    keyword_group = "|".join(
        sorted(
            [re.escape(keyword) for keyword in expense_keywords + income_keywords],
            key=len,
            reverse=True,
        )
    )
    patterns = [
        rf"\$?(\d+(?:,\d{{3}})*(?:\.\d+)?)(?:[^a-z0-9]{{0,24}})(?:{keyword_group})",
        rf"(?:{keyword_group})(?:[^0-9$]{{0,24}})\$?(\d+(?:,\d{{3}})*(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue

        trailing_context = lowered[match.end(): min(len(lowered), match.end() + 16)]
        if re.match(r"\s*months?\b", trailing_context):
            continue

        amount = float(match.group(1).replace(",", ""))
        context = lowered[max(0, match.start() - 32): min(len(lowered), match.end() + 32)]
        if any(keyword in context for keyword in income_keywords):
            return amount
        if any(keyword in context for keyword in expense_keywords):
            return -amount

    return None


def parse_one_time_event_offset(question: str) -> int | None:
    lowered = question.lower()
    if "next month" in lowered:
        return 1

    patterns = [
        r"in\s+(\d+)\s+month",
        r"(\d+)\s+months?\s+from\s+now",
        r"month\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return max(1, min(int(match.group(1)), 12))

    return None


def derive_one_time_event_label(question: str, event_amount: float | None) -> str | None:
    if event_amount is None:
        return None

    lowered = question.lower()
    label_map = [
        ("tax refund", "Tax refund"),
        ("car repair", "Car repair"),
        ("repair", "Repair"),
        ("trip", "Planned trip"),
        ("vacation", "Vacation"),
        ("bonus", "Bonus"),
        ("refund", "Refund"),
        ("purchase", "Planned purchase"),
        ("bill", "Bill"),
        ("payment", "Payment"),
        ("tuition", "Tuition"),
        ("wedding", "Wedding"),
        ("medical", "Medical expense"),
        ("gift", "Gift"),
        ("sale", "Sale"),
    ]

    for keyword, label in label_map:
        if keyword in lowered:
            return label

    return "One-time income" if event_amount > 0 else "One-time expense"


def parse_simulation_adjustments(question: str) -> tuple[float, float]:
    lower_question = question.lower()

    def extract_amount(keywords: list[str]) -> float:
        keyword_group = "|".join(re.escape(keyword) for keyword in keywords)
        match = re.search(
            rf"(?:{keyword_group})(?:[^0-9-]{{0,24}})(\d+(?:\.\d+)?)",
            lower_question,
        )
        if not match:
            return 0.0

        amount = float(match.group(1))
        context = lower_question[max(0, match.start() - 24): match.end()]
        negative_signals = ("down", "decrease", "less", "lower", "reduce", "cut")
        positive_signals = ("up", "increase", "more", "higher", "raise")

        if any(signal in context for signal in negative_signals) and not any(
            signal in context for signal in positive_signals
        ):
            return -amount

        return amount

    income_adjustment = extract_amount(["income", "salary", "earn", "earning", "pay"])
    expense_adjustment = extract_amount(["expense", "expenses", "spend", "spending", "costs"])
    return income_adjustment, expense_adjustment


def generate_assistant_response(
    db: Session,
    user_id: int,
    question: str,
    history: list[Any] | None = None,
    mode: str = "balanced",
    account_id: int | None = None,
    scope_label: str = "All accounts combined",
    llm_allowed: bool = True,
) -> dict[str, Any]:
    history = history or []
    context_text = extract_recent_context(history)
    if is_security_sensitive_assistant_request(question, context_text):
        return build_assistant_security_refusal(scope_label)

    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)
    snapshot["scope_label"] = scope_label
    data_quality = get_transaction_data_quality_report(db, user_id, account_id=account_id)
    snapshot["data_quality_level"] = data_quality["quality_level"]
    snapshot["data_quality_score"] = data_quality["quality_score"]
    snapshot["data_quality_message"] = data_quality["message"]
    snapshot["data_review_action_count"] = len(data_quality["actions"])
    category_trends = get_category_trends(db, user_id, account_id=account_id)
    overspending_alerts = get_overspending_alerts(db, user_id, account_id=account_id)
    recent_transactions = get_recent_transactions(
        db,
        user_id,
        account_id=account_id,
        limit=5,
    )

    q = (question or "").strip().lower()
    intent = classify_question(q, context_text)
    likely_saved_scenario_question = any(
        phrase in q
        for phrase in [
            "compare",
            "better",
            "best",
            "strongest",
            "plan",
            "scenario",
            "safest",
            "risk",
            "goal",
            "target",
            "cash flow",
            "monthly net",
        ]
    )
    saved_scenario_name_candidates = (
        [
            {
                "id": item.id,
                "name": item.name,
            }
            for item in list_saved_scenarios(
                db=db,
                owner_id=user_id,
                account_id=account_id,
            )
        ]
        if likely_saved_scenario_question
        else []
    )
    named_saved_scenarios_in_question = detect_named_saved_scenarios(
        question=question,
        context_text=context_text,
        saved_scenarios=saved_scenario_name_candidates,
    )
    if len(named_saved_scenarios_in_question) >= 2:
        intent = "saved_scenario_compare"

    current_month = snapshot["current_month"]
    budget_snapshot = get_budget_progress_snapshot(
        db,
        user_id,
        month=current_month or get_default_budget_month(),
        account_id=account_id,
    )
    budget_action_insights = build_budget_action_insights(budget_snapshot["items"])
    budget_categories = [item["category"] for item in budget_snapshot["items"]]
    focus_categories = get_distinct_categories(db, user_id, account_id=account_id)
    seen_focus_categories = {
        normalize_text_for_matching(item)
        for item in focus_categories
    }
    for category in budget_categories:
        normalized_category = normalize_text_for_matching(category)
        if normalized_category and normalized_category not in seen_focus_categories:
            focus_categories.append(category)
            seen_focus_categories.add(normalized_category)

    focus_category = detect_focus_category(
        question=question,
        context_text=context_text,
        categories=sorted(
            focus_categories,
            key=lambda item: (-len(normalize_text_for_matching(item)), item.lower()),
        ),
    )
    if focus_category and "transaction" in q:
        intent = "category_transactions"

    total_income = snapshot["total_income"]
    total_expenses = snapshot["total_expenses"]
    balance = snapshot["balance"]
    top_category = snapshot["top_category"]
    top_category_amount = snapshot["top_category_amount"]
    top_category_share_percent = snapshot["top_category_share_percent"]
    expense_change_percent = snapshot["expense_change_percent"]

    primary_driver = None
    if category_trends.get("top_increases"):
        primary_driver = category_trends["top_increases"][0]["category"]

    focus_snapshot = (
        build_category_focus_snapshot(
            db,
            user_id,
            focus_category,
            snapshot,
            account_id=account_id,
        )
        if focus_category
        else None
    )
    focused_budget = next(
        (
            item
            for item in budget_snapshot["items"]
            if normalize_text_for_matching(item["category"]) == normalize_text_for_matching(focus_category or "")
        ),
        None,
    )
    saved_scenario_snapshots = (
        build_saved_scenario_projection_snapshots(
            db=db,
            user_id=user_id,
            account_id=account_id,
            scope_label=scope_label,
        )
        if intent in {"saved_scenario_list", "saved_scenario_compare"} or likely_saved_scenario_question
        else []
    )
    recurring_expenses = (
        get_recurring_expense_patterns(
            db=db,
            user_id=user_id,
            account_id=account_id,
            limit=5,
        )
        if intent in {"recurring_expenses", "saving_advice"}
        else []
    )
    simulation_recommendations = (
        build_future_simulation_recommendations(
            db=db,
            user_id=user_id,
            account_id=account_id,
            months=6,
            scope_label=scope_label,
        )
        if intent == "savings_scenario"
        else {"items": []}
    )
    if (
        intent not in {"saved_scenario_list", "saved_scenario_compare"}
        and saved_scenario_snapshots
        and is_saved_scenario_plan_comparison_question(question, context_text)
    ):
        intent = "saved_scenario_compare"

    if intent == "saved_scenario_list":
        if not saved_scenario_snapshots:
            return {
                "answer": (
                    f"You do not have any saved simulator scenarios in {scope_label} yet. "
                    "Save a few plans in the simulator first and I can help compare them."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    "Saved scenarios found: 0",
                ],
                "suggested_followups": [
                    "What will my balance look like in 3 months?",
                    "How much do I need to save each month to hit my target?",
                ],
                "suggested_actions": [
                    {
                        "label": "Open simulator",
                        "page": "simulator",
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        portfolio_summary = build_saved_scenario_portfolio_summary(saved_scenario_snapshots)
        supporting_points = [
            (
                f"Portfolio: {portfolio_summary['healthy_count']} healthy, "
                f"{portfolio_summary['attention_count']} need attention, "
                f"{portfolio_summary['goal_count']} goal-based, "
                f"{portfolio_summary['event_count']} event-driven"
            )
        ]
        if portfolio_summary["strongest"] is not None:
            supporting_points.append(
                f"Strongest finish: {build_saved_scenario_supporting_point(portfolio_summary['strongest'])}"
            )
        if (
            portfolio_summary["safest"] is not None
            and portfolio_summary["safest"]["id"] != portfolio_summary["strongest"]["id"]
        ):
            supporting_points.append(
                f"Safest cushion: {build_saved_scenario_supporting_point(portfolio_summary['safest'], comparison_focus='risk')}"
            )
        if portfolio_summary["goal_leader"] is not None:
            supporting_points.append(
                f"Goal leader: {build_saved_scenario_supporting_point(portfolio_summary['goal_leader'], comparison_focus='goal')}"
            )

        return {
            "answer": (
                f"You have {len(saved_scenario_snapshots)} saved simulator plan"
                f"{'' if len(saved_scenario_snapshots) == 1 else 's'} in {scope_label}. "
                f"{portfolio_summary['healthy_count']} look healthy right now and "
                f"{portfolio_summary['attention_count']} need attention. "
                f"{portfolio_summary['strongest']['name']} currently has the strongest projected finish."
            ),
            "supporting_points": supporting_points,
            "suggested_followups": [
                "Which saved scenario looks strongest?",
                "Which saved scenario is safest?",
                "Which saved scenario has the best monthly cash flow?",
                "Which saved scenario gets me closest to my goal?",
                "What will my balance look like in 3 months?",
            ],
            "suggested_actions": [
                *(
                    [
                        {
                            "label": f"Compare {portfolio_summary['strongest']['name']} vs {portfolio_summary['safest']['name']}",
                            "page": "simulator",
                            "account_id": account_id,
                            "saved_scenario_id": portfolio_summary["strongest"]["id"],
                            "compare_saved_scenario_id": portfolio_summary["safest"]["id"],
                        }
                    ]
                    if portfolio_summary["strongest"] is not None
                    and portfolio_summary["safest"] is not None
                    and portfolio_summary["strongest"]["id"] != portfolio_summary["safest"]["id"]
                    else []
                ),
                *(
                    [
                        {
                            "label": f"Open {portfolio_summary['strongest']['name']}",
                            "page": "simulator",
                            "account_id": account_id,
                            "saved_scenario_id": portfolio_summary["strongest"]["id"],
                        }
                    ]
                    if portfolio_summary["strongest"] is not None
                    else []
                ),
                {
                    "label": "Open simulator",
                    "page": "simulator",
                    "account_id": account_id,
                },
            ],
            "scope_label": scope_label,
        }

    if intent == "saved_scenario_compare":
        if len(saved_scenario_snapshots) < 2:
            return {
                "answer": (
                    f"I need at least two saved scenarios in {scope_label} before I can compare them."
                ),
                "supporting_points": [
                    f"Saved scenarios found: {len(saved_scenario_snapshots)}",
                ],
                "suggested_followups": [
                    "What will my balance look like in 3 months?",
                    "How much do I need to save each month to hit my target?",
                ],
                "suggested_actions": [
                    {
                        "label": "Open simulator",
                        "page": "simulator",
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        named_scenarios = detect_named_saved_scenarios(
            question=question,
            context_text=context_text,
            saved_scenarios=saved_scenario_snapshots,
        )
        comparison_set = named_scenarios[:2] if len(named_scenarios) >= 2 else saved_scenario_snapshots[:2]
        comparison_focus = detect_saved_scenario_comparison_focus(question, context_text)
        comparison_set = sorted(
            comparison_set,
            key=lambda item: build_saved_scenario_comparison_key(item, comparison_focus),
            reverse=True,
        )

        best_scenario = comparison_set[0]
        runner_up = comparison_set[1]
        projected_gap = (
            float(best_scenario["projected_end_balance"])
            - float(runner_up["projected_end_balance"])
        )
        monthly_net_gap = (
            float(best_scenario["monthly_net_change"])
            - float(runner_up["monthly_net_change"])
        )
        safer_floor_gap = (
            float(best_scenario.get("lowest_balance") or 0.0)
            - float(runner_up.get("lowest_balance") or 0.0)
        )
        goal_balance = best_scenario.get("goal_balance")
        goal_gap_amount = best_scenario.get("goal_gap_amount")

        if comparison_focus == "risk":
            if mode == "strict":
                answer = (
                    f"{best_scenario['name']} is the safest saved plan right now. "
                    f"It carries {best_scenario['risk_level']} risk and keeps the balance floor "
                    f"{format_currency(safer_floor_gap)} higher than {runner_up['name']}."
                )
            elif mode == "coach":
                answer = (
                    f"{best_scenario['name']} looks like the safest path to lean on right now. "
                    f"It gives you the steadiest balance cushion through the scenario window."
                )
            else:
                answer = (
                    f"{best_scenario['name']} currently looks like the safest saved scenario. "
                    f"It keeps a stronger balance floor than {runner_up['name']} while staying "
                    f"at {best_scenario['risk_level']} risk."
                )
        elif comparison_focus == "monthly_net":
            if mode == "strict":
                answer = (
                    f"{best_scenario['name']} has the strongest monthly cash flow. "
                    f"It runs {format_currency(monthly_net_gap)} per month ahead of {runner_up['name']}."
                )
            elif mode == "coach":
                answer = (
                    f"{best_scenario['name']} gives you the cleanest month-to-month breathing room. "
                    f"It improves your ongoing cash flow the most."
                )
            else:
                answer = (
                    f"{best_scenario['name']} currently has the strongest monthly net change, "
                    f"running {format_currency(monthly_net_gap)} per month ahead of {runner_up['name']}."
                )
        elif comparison_focus == "goal" and goal_balance is not None:
            if goal_gap_amount is not None and goal_gap_amount <= 0:
                answer = (
                    f"{best_scenario['name']} is your strongest goal-focused saved plan right now. "
                    f"It already reaches its target balance of {format_currency(goal_balance)}."
                )
            else:
                answer = (
                    f"{best_scenario['name']} is currently the closest saved plan to its target balance. "
                    f"It still needs about {format_currency(float(goal_gap_amount or 0.0))} to get there."
                )
        elif comparison_focus == "goal":
            answer = (
                f"None of these saved scenarios has a target balance attached yet, "
                f"so {best_scenario['name']} is leading on ending balance instead."
            )
        elif mode == "strict":
            answer = (
                f"{best_scenario['name']} is the strongest saved plan right now. "
                f"It finishes {format_currency(projected_gap)} ahead of {runner_up['name']}."
            )
        elif mode == "coach":
            answer = (
                f"{best_scenario['name']} looks like your strongest saved path so far. "
                f"It gives you the most room by the end of the scenario window."
            )
        else:
            answer = (
                f"{best_scenario['name']} currently projects the highest ending balance, "
                f"finishing {format_currency(projected_gap)} ahead of {runner_up['name']}."
            )

        supporting_points = []
        for item in comparison_set:
            supporting_points.append(
                build_saved_scenario_supporting_point(item, comparison_focus=comparison_focus)
            )

        if len(named_scenarios) < 2:
            supporting_points.append(
                "Tip: mention two saved plan names if you want a direct head-to-head comparison."
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:4],
            "suggested_followups": [
                f"Open {best_scenario['name']}",
                "Which saved scenario is safest?",
                "Which saved scenario has the best monthly cash flow?",
                "What will my balance look like in 3 months?",
            ],
            "suggested_actions": [
                {
                    "label": f"Compare {best_scenario['name']} vs {runner_up['name']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "saved_scenario_id": best_scenario["id"],
                    "compare_saved_scenario_id": runner_up["id"],
                },
                {
                    "label": f"Open {best_scenario['name']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "saved_scenario_id": best_scenario["id"],
                },
                {
                    "label": "Open simulator",
                    "page": "simulator",
                    "account_id": account_id,
                },
            ],
            "scope_label": scope_label,
        }

    if intent == "savings_scenario":
        recommendation_items = simulation_recommendations.get("items", [])
        if not recommendation_items:
            return {
                "answer": (
                    f"I do not have a strong simulator recommendation for {scope_label} yet. "
                    "A little more recurring, budget, or monthly history would help me rank the best plan."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    "Recommended plans found: 0",
                ],
                "suggested_followups": [
                    "What subscriptions or recurring charges do I have?",
                    "Give me saving advice",
                ],
                "suggested_actions": [
                    {
                        "label": "Open simulator",
                        "page": "simulator",
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        lead_recommendation = recommendation_items[0]
        runner_up = recommendation_items[1] if len(recommendation_items) > 1 else None

        if mode == "strict":
            answer = (
                f"{lead_recommendation['label']} is the strongest simulator plan to try first in {scope_label}. "
                f"It improves the projection by {format_currency(lead_recommendation['scenario_impact_amount'])}."
            )
        elif mode == "coach":
            answer = (
                f"{lead_recommendation['label']} looks like the most practical scenario to try first in {scope_label}. "
                f"It gives you the clearest upside without overcomplicating the plan."
            )
        else:
            answer = (
                f"{lead_recommendation['label']} is the strongest simulator recommendation I see for {scope_label}. "
                f"It projects about {format_currency(lead_recommendation['projected_end_balance'])} at the end of the window."
            )

        supporting_points = [
            (
                f"{item['label']}: {item['description']} "
                f"Projected end {format_currency(item['projected_end_balance'])}, "
                f"impact {format_currency(item['scenario_impact_amount'])}, "
                f"risk {item['risk_level']}."
            )
            for item in recommendation_items[:3]
        ]

        suggested_actions = [
            {
                "label": f"Apply {lead_recommendation['label']}",
                "page": "simulator",
                "account_id": account_id,
                "scenario_name": lead_recommendation["label"],
                "months_ahead": lead_recommendation["months"],
                "income_adjustment": lead_recommendation["income_adjustment"],
                "expense_adjustment": lead_recommendation["expense_adjustment"],
                "target_balance": lead_recommendation.get("target_balance"),
                "event_month_offset": lead_recommendation.get("event_month_offset"),
                "event_amount": lead_recommendation.get("event_amount"),
                "event_label": lead_recommendation.get("event_label"),
            }
        ]
        if runner_up is not None:
            suggested_actions.append(
                {
                    "label": f"Try {runner_up['label']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "scenario_name": runner_up["label"],
                    "months_ahead": runner_up["months"],
                    "income_adjustment": runner_up["income_adjustment"],
                    "expense_adjustment": runner_up["expense_adjustment"],
                    "target_balance": runner_up.get("target_balance"),
                    "event_month_offset": runner_up.get("event_month_offset"),
                    "event_amount": runner_up.get("event_amount"),
                    "event_label": runner_up.get("event_label"),
                }
            )

        suggested_actions.append(
            {
                "label": "Open simulator",
                "page": "simulator",
                "account_id": account_id,
            }
        )

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    if intent == "recurring_expenses":
        if not recurring_expenses:
            return {
                "answer": (
                    f"I do not see any strong recurring expense patterns in {scope_label} yet. "
                    "If you track a couple more months of subscription or bill activity, I can flag them more reliably."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    "Recurring patterns found: 0",
                ],
                "suggested_followups": [
                    "Show my recent transactions",
                    "What category is driving my spending most?",
                ],
                "suggested_actions": [
                    {
                        "label": "Open transactions",
                        "page": "transactions",
                    }
                ],
                "scope_label": scope_label,
            }

        recurring_total = round(sum(item["average_amount"] for item in recurring_expenses), 2)
        annualized_total = round(sum(item["annualized_amount"] for item in recurring_expenses), 2)
        savings_opportunities = build_recurring_savings_opportunities(recurring_expenses)
        review_candidate = savings_opportunities[0]
        increased_items = [
            item
            for item in recurring_expenses
            if (item.get("latest_change_percent") or 0.0) >= 8
        ]
        combined_review_cut = round(
            sum(float(item.get("average_amount") or 0.0) for item in savings_opportunities[:2]),
            2,
        )
        review_words = ("review", "cancel", "cut", "first", "trim")
        wants_review = any(word in q for word in review_words)
        wants_savings_model = any(
            phrase in q
            for phrase in [
                "cancel",
                "cut",
                "drop",
                "remove",
                "save if",
                "what happens if",
                "what if i cancel",
            ]
        )
        wants_increase_focus = any(
            phrase in q
            for phrase in [
                "increase",
                "increased",
                "went up",
                "higher",
                "price change",
                "price increase",
            ]
        )

        if wants_increase_focus and increased_items:
            leading_item = increased_items[0]
            answer = (
                f"{leading_item['description']} is the clearest recurring charge increase in {scope_label}. "
                f"Its latest charge landed about {leading_item['latest_change_percent']:.0f}% above its usual amount."
            )
        elif wants_savings_model:
            answer = (
                f"If you cancel {review_candidate['description']}, you would free up about "
                f"{format_currency(review_candidate['average_amount'])} per month or "
                f"{format_currency(review_candidate['annualized_amount'])} per year in {scope_label}. "
                "I can open that as a simulator cut so you can see the balance impact."
            )
        elif wants_review:
            answer = (
                f"{review_candidate['description']} is the first recurring charge I would review in {scope_label}. "
                f"{review_candidate['review_reason']}"
            )
        elif mode == "strict":
            answer = (
                f"I found {len(recurring_expenses)} likely recurring expense pattern"
                f"{'' if len(recurring_expenses) == 1 else 's'} in {scope_label}, worth about "
                f"{format_currency(recurring_total)} per month. {review_candidate['description']} is the first one to review."
            )
        elif mode == "coach":
            answer = (
                f"You have {len(recurring_expenses)} likely recurring charge"
                f"{'' if len(recurring_expenses) == 1 else 's'} in {scope_label}, adding up to about "
                f"{format_currency(recurring_total)} a month. {review_candidate['description']} looks like the first one to review."
            )
        else:
            answer = (
                f"I found {len(recurring_expenses)} likely recurring expense pattern"
                f"{'' if len(recurring_expenses) == 1 else 's'} in {scope_label}. "
                f"Together they add up to about {format_currency(recurring_total)} a month "
                f"or {format_currency(annualized_total)} a year."
            )

        supporting_points = [
            (
                f"{item['description']}: {item['cadence']}, avg {format_currency(item['average_amount'])}, "
                f"latest {format_currency(item['latest_amount'])} on {item['latest_date'].isoformat()}, "
                f"about {format_currency(item['annualized_amount'])}/year. "
                f"{item['review_reason']}"
                f"{' Next expected around ' + item['next_expected_date'].isoformat() + '.' if item.get('next_expected_date') else ''}"
            )
            for item in recurring_expenses
        ]

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": f"Review {review_candidate['description']}",
                    "page": "transactions",
                    "section": "recurring",
                    "description": review_candidate["description"],
                    "category": review_candidate["category"],
                    "transaction_type": "expense",
                    "account_id": account_id,
                },
                {
                    "label": f"Model cancelling {review_candidate['description']}",
                    "page": "simulator",
                    "account_id": account_id,
                    "scenario_name": f"Cancel {review_candidate['description']}",
                    "expense_adjustment": -float(review_candidate["average_amount"]),
                },
                *(
                    [
                        {
                            "label": "Model review-first recurring cuts",
                            "page": "simulator",
                            "account_id": account_id,
                            "scenario_name": "Review-first recurring cuts",
                            "expense_adjustment": -combined_review_cut,
                        }
                    ]
                    if combined_review_cut > float(review_candidate["average_amount"])
                    else []
                ),
                {
                    "label": "Open all recurring charges",
                    "page": "transactions",
                    "section": "recurring",
                    "transaction_type": "expense",
                    "account_id": account_id,
                }
            ],
            "scope_label": scope_label,
        }

    if intent == "account_comparison":
        if account_id is not None:
            return {
                "answer": (
                    f"You're currently focused on {scope_label}, so I can't compare accounts inside this scoped view. "
                    "Switch to all accounts and ask again if you want a cross-account comparison."
                ),
                "supporting_points": [
                    f"Current scope: {scope_label}",
                    f"Balance in this scope: {format_currency(balance)}",
                ],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": "Open accounts",
                        "page": "accounts",
                    }
                ],
                "scope_label": scope_label,
            }

        account_comparison = get_account_comparison_snapshot(db, user_id)
        if len(account_comparison) < 2:
            return {
                "answer": "I need at least two active accounts before I can compare which one is driving your spending.",
                "supporting_points": [
                    f"Active accounts found: {len(account_comparison)}",
                ],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": "Open accounts",
                        "page": "accounts",
                    }
                ],
                "scope_label": scope_label,
            }

        leading_account = account_comparison[0]
        runner_up = account_comparison[1]
        expense_gap = leading_account["total_expenses"] - runner_up["total_expenses"]

        if mode == "strict":
            answer = (
                f"{leading_account['name']} is driving the most spending at {format_currency(leading_account['total_expenses'])}. "
                f"That is {format_currency(expense_gap)} more than {runner_up['name']}, so start there first."
            )
        elif mode == "coach":
            answer = (
                f"{leading_account['name']} is the main spending driver right now at {format_currency(leading_account['total_expenses'])}. "
                f"That gives us a clear account to review first."
            )
        else:
            answer = (
                f"{leading_account['name']} currently has the highest expenses at {format_currency(leading_account['total_expenses'])}, "
                f"followed by {runner_up['name']} at {format_currency(runner_up['total_expenses'])}."
            )

        supporting_points = []
        for item in account_comparison[:3]:
            point = (
                f"{item['name']} ({item['type']}): expenses {format_currency(item['total_expenses'])}, "
                f"income {format_currency(item['total_income'])}, balance {format_currency(item['balance'])}"
            )
            if item["top_category"]:
                point += (
                    f", top category {item['top_category']} "
                    f"at {format_currency(item['top_category_amount'])}"
                )
            supporting_points.append(point)

        return {
            "answer": answer,
            "supporting_points": supporting_points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "Open accounts",
                    "page": "accounts",
                },
                {
                    "label": f"Review {leading_account['name']} transactions",
                    "page": "transactions",
                    "account_id": leading_account["account_id"],
                },
            ],
            "scope_label": scope_label,
        }

    if intent == "budget_status":
        budget_month = budget_snapshot["month"]

        if budget_snapshot["budget_count"] == 0:
            return {
                "answer": (
                    f"You do not have any budgets set for {budget_month} in {scope_label} yet. "
                    "Create a few category targets first so I can tell you what is on track or under pressure."
                ),
                "supporting_points": [
                    f"Current budget month: {budget_month}",
                    f"Current scope: {scope_label}",
                    f"Recorded expenses in this scope: {format_currency(total_expenses)}",
                ],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": "Open budgets",
                        "page": "budgets",
                        "month": budget_month,
                        "account_id": account_id,
                    }
                ],
                "scope_label": scope_label,
            }

        if focused_budget:
            focused_budget_label = format_category_label(focus_category or focused_budget["category"])
            remaining_text = (
                f"{format_currency(focused_budget['remaining_amount'])} remaining"
                if focused_budget["remaining_amount"] >= 0
                else f"{format_currency(abs(focused_budget['remaining_amount']))} over"
            )
            projected_finish_text = (
                f"Projected month-end: {format_currency(focused_budget['projected_spent_amount'])} spent, "
                f"{format_currency(focused_budget['projected_remaining_amount'])} remaining"
                if focused_budget["projected_remaining_amount"] >= 0
                else f"Projected month-end: {format_currency(focused_budget['projected_spent_amount'])} spent, "
                f"{format_currency(abs(focused_budget['projected_remaining_amount']))} over"
            )

            if focused_budget["status"] == "over_budget":
                if mode == "strict":
                    answer = (
                        f"{focused_budget_label} is already over budget for {budget_month}. "
                        f"You have used {focused_budget['usage_percent']:.1f}% of the limit."
                    )
                elif mode == "coach":
                    answer = (
                        f"{focused_budget_label} is over budget for {budget_month}, "
                        "so this is the clearest place to tighten up next."
                    )
                else:
                    answer = (
                        f"{focused_budget_label} is over budget for {budget_month}. "
                        f"You have used {focused_budget['usage_percent']:.1f}% of the target."
                    )
            elif focused_budget["status"] == "at_risk":
                if mode == "strict":
                    answer = (
                        f"{focused_budget_label} is getting close to the limit for {budget_month}. "
                        f"You have already used {focused_budget['usage_percent']:.1f}% of the budget."
                    )
                elif mode == "coach":
                    answer = (
                        f"{focused_budget_label} is still on the board for {budget_month}, "
                        "but it is close enough to the limit that it deserves attention now."
                    )
                else:
                    answer = (
                        f"{focused_budget_label} is at risk for {budget_month}. "
                        f"You have used {focused_budget['usage_percent']:.1f}% of the budget."
                    )
            else:
                answer = (
                    f"{focused_budget_label} is on track for {budget_month}. "
                    f"You have used {focused_budget['usage_percent']:.1f}% of the budget so far."
                )

            if (
                focused_budget["projected_status"] == "over_budget"
                and focused_budget["status"] != "over_budget"
            ):
                answer += (
                    f" At the current pace, it is projected to finish "
                    f"{format_currency(abs(focused_budget['projected_remaining_amount']))} over budget."
                )
            elif (
                focused_budget["projected_status"] == "at_risk"
                and focused_budget["status"] == "on_track"
            ):
                answer += (
                    f" At the current pace, it is projected to use "
                    f"{focused_budget['projected_usage_percent']:.1f}% of the budget by month end."
                )

            supporting_points = [
                f"Budget: {format_currency(focused_budget['amount'])}",
                f"Spent so far: {format_currency(focused_budget['spent_amount'])}",
                remaining_text,
                projected_finish_text,
            ]

            if focus_snapshot and focus_snapshot["recent_transactions"]:
                recent_text = ", ".join(
                    f"{tx.description} ({format_currency(tx.amount)})"
                    for tx in focus_snapshot["recent_transactions"][:3]
                )
                supporting_points.append(f"Recent {focused_budget_label} transactions: {recent_text}")
            else:
                supporting_points.append(f"Usage: {focused_budget['usage_percent']:.1f}%")

            return {
                "answer": answer,
                "supporting_points": supporting_points[:5],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [
                    {
                        "label": f"Open {focused_budget_label} budget",
                        "page": "budgets",
                        "month": budget_month,
                        "category": focused_budget["category"],
                        "account_id": account_id,
                    },
                    {
                        "label": f"Review {focused_budget_label} transactions",
                        "page": "transactions",
                        "category": focused_budget["category"],
                        "transaction_type": "expense",
                        "month": budget_month,
                        "account_id": account_id,
                    },
                ],
                "scope_label": scope_label,
            }

        use_projected_issue_view = (
            budget_snapshot["over_budget_count"] == 0
            and budget_snapshot["at_risk_count"] == 0
            and (
                budget_snapshot["projected_over_budget_count"] > 0
                or budget_snapshot["projected_at_risk_count"] > 0
            )
        )
        issue_items = (
            budget_snapshot["projected_issue_items"]
            if use_projected_issue_view
            else budget_snapshot["issue_items"]
        )
        lead_budget = issue_items[0] if issue_items else None

        if budget_snapshot["over_budget_count"] > 0:
            answer = (
                f"You are tracking {budget_snapshot['budget_count']} budgets for {budget_month}, "
                f"and {budget_snapshot['over_budget_count']} of them are already over budget."
            )
        elif budget_snapshot["projected_over_budget_count"] > 0:
            answer = (
                f"Your budgets for {budget_month} are not over budget yet, but "
                f"{budget_snapshot['projected_over_budget_count']} category budgets are projected "
                "to finish over budget at the current pace."
            )
        elif budget_snapshot["at_risk_count"] > 0:
            answer = (
                f"Your budgets for {budget_month} are mostly intact, but {budget_snapshot['at_risk_count']} "
                "category budgets are getting close to the limit."
            )
        elif budget_snapshot["projected_at_risk_count"] > 0:
            answer = (
                f"Your budgets for {budget_month} are still on track today, but "
                f"{budget_snapshot['projected_at_risk_count']} category budgets are projected to get tight "
                "if spending keeps this pace."
            )
        else:
            answer = (
                f"Your budgets for {budget_month} are on track right now. "
                f"You have {format_currency(budget_snapshot['total_remaining'])} of planned room left."
            )

        supporting_points = [
            f"Total budgeted: {format_currency(budget_snapshot['total_budgeted'])}",
            f"Total spent against budgets: {format_currency(budget_snapshot['total_spent'])}",
            f"Remaining budget room: {format_currency(budget_snapshot['total_remaining'])}",
            (
                f"Projected month-end room: {format_currency(budget_snapshot['projected_total_remaining'])}"
                if budget_snapshot["projected_total_remaining"] >= 0
                else f"Projected month-end overage: {format_currency(abs(budget_snapshot['projected_total_remaining']))}"
            ),
        ]

        for item in issue_items:
            if use_projected_issue_view:
                status_label = item["projected_status"].replace("_", " ")
                supporting_points.append(
                    f"{format_category_label(item['category'])}: projected {format_currency(item['projected_spent_amount'])} spent vs {format_currency(item['amount'])} budget ({item['projected_usage_percent']:.1f}% used, {status_label})"
                )
            else:
                status_label = item["status"].replace("_", " ")
                supporting_points.append(
                    f"{format_category_label(item['category'])}: {format_currency(item['spent_amount'])} spent vs {format_currency(item['amount'])} budget ({item['usage_percent']:.1f}% used, {status_label})"
                )

        suggested_actions = [
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": budget_month,
                "account_id": account_id,
            }
        ]

        if lead_budget:
            suggested_actions.append(
                {
                    "label": f"Review {format_category_label(lead_budget['category'])} transactions",
                    "page": "transactions",
                    "category": lead_budget["category"],
                    "transaction_type": "expense",
                    "month": budget_month,
                    "account_id": account_id,
                }
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    actionable_budget_insights = [
        item for item in budget_action_insights if item["severity"] in {"action", "watch"}
    ]
    if intent == "saving_advice" and actionable_budget_insights:
        lead_budget_insight = actionable_budget_insights[0]
        lead_budget_label = format_category_label(lead_budget_insight["category"])

        if mode == "strict":
            answer = (
                f"{lead_budget_insight['title']}. {lead_budget_insight['detail']} "
                "That is the first place to tighten up."
            )
        elif mode == "coach":
            answer = (
                f"{lead_budget_insight['title']}. {lead_budget_insight['detail']} "
                "A small change there would have the clearest payoff."
            )
        else:
            answer = f"{lead_budget_insight['title']}. {lead_budget_insight['detail']}"

        supporting_points = [
            f"{item['title']}: {item['detail']}"
            for item in actionable_budget_insights[:3]
        ]
        supporting_points.append(f"Current scope: {scope_label}")

        suggested_actions = [
            {
                "label": "Open budgets",
                "page": "budgets",
                "month": budget_snapshot["month"],
                "account_id": account_id,
                "amount": lead_budget_insight.get("recommended_amount"),
            }
        ]
        if lead_budget_insight["category"]:
            suggested_actions.append(
                {
                    "label": f"Review {lead_budget_label} transactions",
                    "page": "transactions",
                    "category": lead_budget_insight["category"],
                    "transaction_type": "expense",
                    "month": budget_snapshot["month"],
                    "account_id": account_id,
                }
            )
            suggested_actions[0]["category"] = lead_budget_insight["category"]

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    recurring_savings_opportunities = build_recurring_savings_opportunities(recurring_expenses)
    if intent == "saving_advice" and recurring_savings_opportunities:
        lead_recurring = recurring_savings_opportunities[0]
        combined_recurring_cut = round(
            sum(float(item.get("average_amount") or 0.0) for item in recurring_savings_opportunities[:2]),
            2,
        )

        if mode == "strict":
            answer = (
                f"{lead_recurring['description']} is the cleanest recurring cost to pressure-test first. "
                f"Cutting it would free about {format_currency(lead_recurring['average_amount'])} per month."
            )
        elif mode == "coach":
            answer = (
                f"{lead_recurring['description']} looks like the easiest recurring place to create breathing room. "
                f"It is worth about {format_currency(lead_recurring['average_amount'])} per month."
            )
        else:
            answer = (
                f"{lead_recurring['description']} is the strongest recurring savings lever I see in {scope_label}. "
                f"It is worth about {format_currency(lead_recurring['average_amount'])} per month "
                f"or {format_currency(lead_recurring['annualized_amount'])} per year."
            )

        supporting_points = [
            (
                f"{item['description']}: {format_currency(item['average_amount'])}/month, "
                f"{format_currency(item['annualized_amount'])}/year. {item['review_reason']}"
            )
            for item in recurring_savings_opportunities[:3]
        ]
        supporting_points.append(f"Current scope: {scope_label}")

        suggested_actions = [
            {
                "label": f"Review {lead_recurring['description']}",
                "page": "transactions",
                "section": "recurring",
                "description": lead_recurring["description"],
                "category": lead_recurring["category"],
                "transaction_type": "expense",
                "account_id": account_id,
            },
            {
                "label": f"Model cancelling {lead_recurring['description']}",
                "page": "simulator",
                "account_id": account_id,
                "scenario_name": f"Cancel {lead_recurring['description']}",
                "expense_adjustment": -float(lead_recurring["average_amount"]),
            },
        ]
        if combined_recurring_cut > float(lead_recurring["average_amount"]):
            suggested_actions.append(
                {
                    "label": "Model top recurring cuts",
                    "page": "simulator",
                    "account_id": account_id,
                    "scenario_name": "Top recurring cuts",
                    "expense_adjustment": -combined_recurring_cut,
                }
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": [
                "Which subscriptions should I review first?",
                "What happens if I cancel my biggest subscription?",
                "Open my transactions",
            ],
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    llm_result = None
    if llm_allowed:
        llm_result = generate_llm_assistant_response(
            question=question,
            conversation_context=context_text,
            snapshot=snapshot,
            category_trends=category_trends,
            overspending_alerts=overspending_alerts,
            recent_transactions=recent_transactions,
            focus_category_context=focus_snapshot,
            mode=mode,
        )

    if llm_result:
        suggested_actions = []

        action_type = llm_result.get("action_type", "none")
        action_label = llm_result.get("action_label")
        action_target = llm_result.get("action_target")

        if action_type == "transactions":
            suggested_actions.append(
                {
                    "label": action_label or "Review transactions",
                    "page": "transactions",
                    "category": (
                        action_target
                        if action_target and action_target.lower() != "none"
                        else focus_category or primary_driver or top_category
                    ),
                    "transaction_type": (
                        focus_snapshot["transaction_type"]
                        if focus_snapshot
                        else "expense"
                    ),
                    "month": current_month,
                    "account_id": account_id,
                }
            )

        elif action_type == "dashboard":
            suggested_actions.append(
                {
                    "label": action_label or "Open dashboard",
                    "page": "dashboard",
                    "account_id": account_id,
                }
            )

        elif action_type == "analytics":
            target_section = "insights"
            if action_target:
                lower_target = action_target.lower()
                if "alert" in lower_target:
                    target_section = "alerts"
                elif "trend" in lower_target:
                    target_section = "trends"
                elif "month" in lower_target or "summary" in lower_target:
                    target_section = "monthly"
                elif "categor" in lower_target:
                    target_section = "categories"

            suggested_actions.append(
                {
                    "label": action_label or "Open analytics",
                    "page": "analytics",
                    "section": target_section,
                    "month": current_month,
                    "account_id": account_id,
                }
            )

        elif action_type == "external_resource":
            suggested_actions.append(
                {
                    "label": action_label or "Explore learning resources",
                    "page": "external_resource",
                    "section": action_target or "budgeting basics",
                    "account_id": account_id,
                }
            )

        followups = llm_result["suggested_followups"] or generate_dynamic_followups(
            intent=intent,
            mode=mode,
            top_category=top_category,
            driver_category=primary_driver,
            focus_category=focus_category,
        )

        return {
            "answer": llm_result["answer"],
            "supporting_points": llm_result["supporting_points"],
            "suggested_followups": followups,
            "suggested_actions": suggested_actions,
            "scope_label": scope_label,
        }

    if total_income == 0 and total_expenses == 0:
        answer = "I do not have enough financial activity yet to give a meaningful answer."
        intro = generate_mode_intro(mode)
        final_answer = f"{intro} {answer}".strip() if intro else answer

        return {
            "answer": final_answer,
            "supporting_points": [
                "No recorded income found yet.",
                "No recorded expenses found yet.",
            ],
            "suggested_followups": generate_dynamic_followups(
                intent="general",
                mode=mode,
                top_category=None,
                driver_category=None,
                focus_category=focus_category,
            ),
            "suggested_actions": [],
            "scope_label": scope_label,
        }

    if not q:
        answer = "Ask me about your balance, top categories, transactions, spending trends, saving ideas, alerts, and financial summaries."
        intro = generate_mode_intro(mode)
        final_answer = f"{intro} {answer}".strip() if intro else answer

        return {
            "answer": final_answer,
            "supporting_points": [],
            "suggested_followups": generate_dynamic_followups(
                intent="general",
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [],
            "scope_label": scope_label,
        }

    if intent == "future_balance":
        projection_months = parse_projection_months(question)
        target_balance = parse_target_balance(question)
        income_adjustment, expense_adjustment = parse_simulation_adjustments(question)
        one_time_event_amount = parse_one_time_event_amount(question)
        one_time_event_offset = parse_one_time_event_offset(question)
        one_time_event_label = derive_one_time_event_label(question, one_time_event_amount)
        simulation = build_future_balance_simulation(
            db,
            user_id,
            account_id=account_id,
            months=projection_months,
            income_adjustment=income_adjustment,
            expense_adjustment=expense_adjustment,
            target_balance=target_balance,
            event_month_offset=one_time_event_offset,
            event_amount=one_time_event_amount or 0.0,
            event_label=one_time_event_label,
            scope_label=scope_label,
        )

        if target_balance is not None and simulation["goal_note"]:
            if mode == "strict":
                answer = (
                    f"At this pace you will miss {format_currency(target_balance)}. "
                    f"{simulation['goal_note']}"
                )
            elif mode == "coach":
                answer = (
                    f"Your current pace points to {format_currency(simulation['projected_end_balance'])} "
                    f"in {projection_months} month(s). {simulation['goal_note']}"
                )
            else:
                answer = (
                    f"Your current pace projects {format_currency(simulation['projected_end_balance'])} "
                    f"in {projection_months} month(s). {simulation['goal_note']}"
                )
        elif mode == "strict":
            answer = (
                f"If nothing changes from this pace, your balance is heading toward "
                f"{format_currency(simulation['projected_end_balance'])} in {projection_months} month(s)."
            )
        elif mode == "coach":
            answer = (
                f"If your current pace holds, your balance could land around "
                f"{format_currency(simulation['projected_end_balance'])} in {projection_months} month(s)."
            )
        else:
            answer = (
                f"At the current pace, your balance is projected to be "
                f"{format_currency(simulation['projected_end_balance'])} in {projection_months} month(s)."
            )

        supporting_points = [
            f"Starting balance: {format_currency(simulation['starting_balance'])}",
            f"Monthly income used: {format_currency(simulation['adjusted_monthly_income'])}",
            f"Monthly expenses used: {format_currency(simulation['adjusted_monthly_expenses'])}",
            f"Projected monthly net change: {format_currency(simulation['monthly_net_change'])}",
        ]
        if simulation["one_time_event_amount"] is not None and simulation["one_time_event_month"]:
            supporting_points.append(
                f"One-time event: {simulation['one_time_event_label']} in {simulation['one_time_event_month']} for {format_signed_currency(simulation['one_time_event_amount'])}"
            )
        if simulation["goal_note"]:
            supporting_points.append(simulation["goal_note"])
        else:
            supporting_points.append(simulation["narrative"])

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent=intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                simulation_months=projection_months,
                simulation_target_balance=target_balance,
                simulation_income_adjustment=income_adjustment,
                simulation_expense_adjustment=expense_adjustment,
                simulation_event_month_offset=one_time_event_offset,
                simulation_event_amount=one_time_event_amount,
                simulation_event_label=one_time_event_label,
            ),
            "scope_label": scope_label,
        }

    if focus_snapshot and intent in {
        "category_transactions",
        "recent",
        "saving_advice",
        "spending_change",
        "driver",
        "alerts",
        "top_category",
        "general",
        "summary",
    }:
        return {
            "answer": build_category_focus_answer(
                intent=intent,
                mode=mode,
                focus_snapshot=focus_snapshot,
                top_category=top_category,
            ),
            "supporting_points": build_category_focus_supporting_points(focus_snapshot),
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent="recent" if intent == "category_transactions" else intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                focus_transaction_type=focus_snapshot["transaction_type"],
            ),
            "scope_label": scope_label,
        }

    if intent == "top_categories_multi":
        top_three = get_top_expense_categories(
            db,
            user_id,
            account_id=account_id,
            limit=3,
        )

        if not top_three:
            answer = "I do not have enough expense data yet to identify your top categories."
            intro = generate_mode_intro(mode)
            final_answer = f"{intro} {answer}".strip() if intro else answer

            return {
                "answer": final_answer,
                "supporting_points": [],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [],
                "scope_label": scope_label,
            }

        points = [
            f"{idx + 1}. {item['category']} — {format_currency(item['total'])}"
            for idx, item in enumerate(top_three)
        ]

        if mode == "strict":
            answer = "These categories are taking the biggest share of your money. If you want results, start here."
        elif mode == "coach":
            answer = "These are your top spending categories. They are the best places to look for realistic savings."
        else:
            answer = "These are your top spending categories ranked by total expense amount."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "View all transactions",
                    "page": "transactions",
                }
            ],
            "scope_label": scope_label,
        }

    if intent == "category_transactions":
        top_with_transactions = get_top_categories_with_transactions(
            db,
            user_id,
            account_id=account_id,
            category_limit=3,
            transaction_limit=2,
        )

        if not top_with_transactions:
            answer = "I do not have enough category transaction data yet."
            intro = generate_mode_intro(mode)
            final_answer = f"{intro} {answer}".strip() if intro else answer

            return {
                "answer": final_answer,
                "supporting_points": [],
                "suggested_followups": generate_dynamic_followups(
                    intent=intent,
                    mode=mode,
                    top_category=top_category,
                    driver_category=primary_driver,
                    focus_category=focus_category,
                ),
                "suggested_actions": [],
                "scope_label": scope_label,
            }

        points = []
        for item in top_with_transactions:
            tx_text = ", ".join(
                f"{tx.description} ({format_currency(tx.amount)})"
                for tx in item["transactions"]
            ) or "No recent transactions"
            points.append(
                f"{item['category']} — {format_currency(item['total'])}. Recent items: {tx_text}"
            )

        if mode == "strict":
            answer = "These transactions show where your money is actually going. Review them before looking at charts."
        elif mode == "coach":
            answer = "These transactions help explain your biggest categories. This is a good place to find practical improvements."
        else:
            answer = "Here are the recent transactions inside your biggest expense categories."

        return {
            "answer": answer,
            "supporting_points": points,
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": [
                {
                    "label": "Open transactions",
                    "page": "transactions",
                }
            ],
            "scope_label": scope_label,
        }

    if intent in {"spending_change", "driver", "alerts", "saving_advice", "summary", "balance", "top_category", "general"}:
        driver_reasons = build_driver_explanation(
            expense_change_percent=expense_change_percent,
            top_category=top_category,
            driver_category=primary_driver,
            recent_transactions=recent_transactions,
        )

        if mode == "strict":
            if intent == "saving_advice":
                answer = (
                    f"The clearest weakness is {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "That is where you should cut first if you want meaningful improvement."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The main issue looks straightforward: "
                    + (driver_reasons[0] if driver_reasons else "your spending pattern is under pressure")
                    + "."
                )
            else:
                answer = (
                    f"Your balance is {format_currency(balance)}, and the biggest pressure point is "
                    f"{top_category or 'your top expense area'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )

        elif mode == "coach":
            if intent == "saving_advice":
                answer = (
                    f"The best opportunity right now is {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "A small improvement there could make a noticeable difference."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The strongest signal right now is "
                    + (driver_reasons[0] if driver_reasons else "a change in your recent spending pattern")
                    + ", which gives us a clear place to start."
                )
            else:
                answer = (
                    f"You currently have {format_currency(balance)} available, and your biggest spending pressure is "
                    f"{top_category or 'your top expense area'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}. "
                    "That gives us a clear next step."
                )
        else:
            if intent == "saving_advice":
                answer = (
                    f"The biggest savings opportunity appears to be {top_category or 'your largest expense category'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )
            elif intent in {"spending_change", "driver", "alerts"}:
                answer = (
                    "The likely driver is "
                    + (driver_reasons[0] if driver_reasons else "your recent expense pattern")
                    + "."
                )
            else:
                answer = (
                    f"Your balance is {format_currency(balance)}, and your top expense category is "
                    f"{top_category or 'N/A'}"
                    f"{f' at {format_currency(top_category_amount)}' if top_category else ''}."
                )

        supporting_points = [
            f"Balance: {format_currency(balance)}",
            f"Total income: {format_currency(total_income)}",
            f"Total expenses: {format_currency(total_expenses)}",
        ]

        data_quality_point = build_data_quality_supporting_point(data_quality)
        if data_quality_point:
            supporting_points.append(data_quality_point)

        if top_category:
            supporting_points.append(
                f"Top expense category: {top_category} at {format_currency(top_category_amount)}"
            )

        if top_category_share_percent is not None:
            supporting_points.append(
                f"{top_category} represents {top_category_share_percent:.1f}% of all expenses"
            )

        if expense_change_percent is not None:
            supporting_points.append(
                f"Latest monthly expense change: {expense_change_percent:.1f}%"
            )

        return {
            "answer": answer,
            "supporting_points": supporting_points[:5],
            "suggested_followups": generate_dynamic_followups(
                intent=intent,
                mode=mode,
                top_category=top_category,
                driver_category=primary_driver,
                focus_category=focus_category,
            ),
            "suggested_actions": build_assistant_actions(
                snapshot=snapshot,
                intent=intent,
                account_id=account_id,
                driver_category=primary_driver,
                focus_category=focus_category,
                focus_transaction_type=focus_snapshot["transaction_type"] if focus_snapshot else "expense",
            ),
            "scope_label": scope_label,
        }

    return {
        "answer": "I can help with your balance, top categories, transactions, spending trends, saving ideas, alerts, and summaries.",
        "supporting_points": [
            f"Balance: {format_currency(balance)}",
            f"Top expense category: {top_category or 'N/A'}",
        ],
        "suggested_followups": generate_dynamic_followups(
            intent="general",
            mode=mode,
            top_category=top_category,
            driver_category=primary_driver,
            focus_category=focus_category,
        ),
        "suggested_actions": [],
        "scope_label": scope_label,
    }


def generate_assistant_suggestions(
    db: Session,
    user_id: int,
    account_id: int | None = None,
) -> list[str]:
    snapshot = build_financial_snapshot(db, user_id, account_id=account_id)
    category_trends = get_category_trends(db, user_id, account_id=account_id)
    budget_snapshot = get_budget_progress_snapshot(
        db,
        user_id,
        month=snapshot["current_month"] or get_default_budget_month(),
        account_id=account_id,
    )
    saved_scenarios = list_saved_scenarios(
        db=db,
        owner_id=user_id,
        account_id=account_id,
    )
    recurring_expenses = get_recurring_expense_patterns(
        db=db,
        user_id=user_id,
        account_id=account_id,
        limit=3,
    )
    simulation_recommendations = build_future_simulation_recommendations(
        db=db,
        user_id=user_id,
        account_id=account_id,
        months=6,
        scope_label=(
            "All accounts combined"
            if account_id is None
            else f"Account {account_id}"
        ),
    )

    suggestions: list[str] = ["What is my balance?"]

    if snapshot["top_category"]:
        suggestions.append(f"Why is {snapshot['top_category']} my top expense category?")
        suggestions.append(f"How can I reduce {snapshot['top_category']} spending?")

    if simulation_recommendations.get("items"):
        suggestions.append("Which savings scenario should I try first?")

    if budget_snapshot["budget_count"] > 0:
        if budget_snapshot["over_budget_count"] > 0:
            suggestions.append("Which category is over budget right now?")
        elif budget_snapshot["projected_over_budget_count"] > 0:
            suggestions.append("Which budget is projected to go over?")
        elif budget_snapshot["at_risk_count"] > 0:
            suggestions.append("Which budget is closest to the limit?")
        elif budget_snapshot["projected_at_risk_count"] > 0:
            suggestions.append("Which budget is projected to get tight?")
        else:
            suggestions.append("Am I on track with my budgets?")

    if category_trends.get("top_increases"):
        suggestions.append(
            f"Why did my {category_trends['top_increases'][0]['category']} spending increase?"
        )

    if snapshot["expense_change_percent"] is not None:
        if snapshot["expense_change_percent"] > 0:
            suggestions.append("Why did my spending increase?")
        elif snapshot["expense_change_percent"] < 0:
            suggestions.append("Why did my spending decrease?")

    if snapshot["current_month"]:
        suggestions.append(f"Summarize my finances for {snapshot['current_month']}")

    if saved_scenarios:
        suggestions.append("Which saved scenario looks strongest?")
        if len(saved_scenarios) > 1:
            suggestions.append("Which saved scenario is safest?")
            suggestions.append("Which saved scenario has the best monthly cash flow?")
            suggestions.append("Which saved scenario gets me closest to my goal?")
            suggestions.append("Compare my saved scenarios")

    if recurring_expenses:
        suggestions.append("What subscriptions or recurring charges do I have?")
        if any(item.get("review_priority") == "high" for item in recurring_expenses):
            suggestions.append("Which subscriptions should I review first?")
            suggestions.append("What happens if I cancel my biggest subscription?")
            if simulation_recommendations.get("items"):
                suggestions.append("Which savings scenario should I try first?")
        suggestions.append("Which recurring charge costs me the most each year?")

    if simulation_recommendations.get("items"):
        suggestions.append("Which savings scenario should I try first?")

    suggestions.append("What will my balance look like in 3 months?")
    suggestions.append("Show my recent transactions")
    suggestions.append("Give me saving advice")

    unique_suggestions: list[str] = []
    for item in suggestions:
        if item not in unique_suggestions:
            unique_suggestions.append(item)

    return unique_suggestions[:8]
