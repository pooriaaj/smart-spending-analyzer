from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any


def get_default_budget_month() -> str:
    return date.today().strftime("%Y-%m")


def compute_budget_status(
    amount: float,
    spent_amount: float,
) -> tuple[float, float, str]:
    remaining_amount = amount - spent_amount
    usage_percent = (spent_amount / amount) * 100 if amount > 0 else 0.0

    if spent_amount > amount:
        status = "over_budget"
    elif usage_percent >= 80:
        status = "at_risk"
    else:
        status = "on_track"

    return remaining_amount, usage_percent, status


def format_budget_currency(value: float) -> str:
    return f"${value:.2f}"


def resolve_budget_month_bounds(month: str) -> tuple[date, date, int]:
    month_start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    days_total = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=days_total)
    return month_start, month_end, days_total


def build_budget_pace_context(
    month: str,
    amount: float,
    spent_amount: float,
    remaining_amount: float,
    *,
    today: date | None = None,
) -> dict[str, int | float | str | None]:
    today = today or date.today()
    month_start, month_end, days_total = resolve_budget_month_bounds(month)

    daily_allowance: float | None = None
    daily_pace: float | None = None

    if today < month_start:
        days_elapsed = 0
        days_remaining = days_total
        daily_allowance = amount / days_total if days_total > 0 else None
        pace_note = (
            f"This budget has not started yet. Planned average pace is {format_budget_currency(daily_allowance or 0.0)} per day."
        )
    elif today > month_end:
        days_elapsed = days_total
        days_remaining = 0
        daily_pace = spent_amount / days_total if days_total > 0 else None
        if remaining_amount >= 0:
            pace_note = (
                f"This month closed with {format_budget_currency(remaining_amount)} remaining."
            )
        else:
            pace_note = (
                f"This month closed {format_budget_currency(abs(remaining_amount))} over budget."
            )
    else:
        days_elapsed = today.day
        days_remaining = days_total - today.day + 1
        daily_allowance = remaining_amount / days_remaining if days_remaining > 0 else None
        daily_pace = spent_amount / days_elapsed if days_elapsed > 0 else None

        expected_spend_to_date = (amount / days_total) * days_elapsed if days_total > 0 else 0.0
        pace_variance = spent_amount - expected_spend_to_date
        significance_threshold = max(amount * 0.05, 5.0)

        if remaining_amount < 0:
            pace_note = (
                f"Already {format_budget_currency(abs(remaining_amount))} over budget with {days_remaining} day(s) left."
            )
        elif pace_variance > significance_threshold:
            pace_note = (
                f"Running about {format_budget_currency(pace_variance)} ahead of pace for this point in the month."
            )
        elif pace_variance < -significance_threshold:
            pace_note = (
                f"Running about {format_budget_currency(abs(pace_variance))} under pace so far this month."
            )
        else:
            pace_note = "Spending is roughly on pace for this point in the month."

    return {
        "days_total": days_total,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "daily_allowance": daily_allowance,
        "daily_pace": daily_pace,
        "pace_note": pace_note,
    }


def build_budget_projection_context(
    month: str,
    amount: float,
    spent_amount: float,
    *,
    today: date | None = None,
) -> dict[str, float | str | None]:
    today = today or date.today()
    month_start, month_end, days_total = resolve_budget_month_bounds(month)

    if today < month_start:
        projected_spent_amount = spent_amount
        projected_remaining_amount, projected_usage_percent, projected_status = (
            compute_budget_status(amount, projected_spent_amount)
        )
        projection_note = (
            "This month has not started yet, so the forecast will update once spending begins."
        )
    elif today > month_end:
        projected_spent_amount = spent_amount
        projected_remaining_amount, projected_usage_percent, projected_status = (
            compute_budget_status(amount, projected_spent_amount)
        )
        if projected_remaining_amount >= 0:
            projection_note = (
                f"This month closed with {format_budget_currency(projected_remaining_amount)} remaining."
            )
        else:
            projection_note = (
                f"This month closed {format_budget_currency(abs(projected_remaining_amount))} over budget."
            )
    else:
        days_elapsed = max(today.day, 1)
        daily_pace = spent_amount / days_elapsed if days_elapsed > 0 else 0.0
        projected_spent_amount = daily_pace * days_total
        projected_remaining_amount, projected_usage_percent, projected_status = (
            compute_budget_status(amount, projected_spent_amount)
        )

        if spent_amount <= 0:
            projection_note = (
                "No spending is recorded yet, so the month-end forecast is still wide open."
            )
        elif projected_remaining_amount < 0:
            projection_note = (
                f"At the current pace, this budget is projected to finish {format_budget_currency(abs(projected_remaining_amount))} over budget."
            )
        elif projected_status == "at_risk":
            projection_note = (
                f"At the current pace, this budget is projected to use {projected_usage_percent:.1f}% of the limit by month end."
            )
        else:
            projection_note = (
                f"At the current pace, this budget is projected to finish with {format_budget_currency(projected_remaining_amount)} remaining."
            )

        if spent_amount > 0 and days_elapsed <= 3:
            projection_note += " Early-month forecasts can shift quickly."

    return {
        "projected_spent_amount": projected_spent_amount,
        "projected_remaining_amount": projected_remaining_amount,
        "projected_usage_percent": projected_usage_percent,
        "projected_status": projected_status,
        "projection_note": projection_note,
    }


def format_budget_category_label(category: str | None) -> str:
    if not category:
        return "This budget"
    return " ".join(word.capitalize() for word in str(category).replace("_", " ").split())


def _read_budget_item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def build_budget_action_insights(
    items: list[Any],
    limit: int = 3,
) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []

    for item in items:
        category = str(_read_budget_item_value(item, "category") or "")
        label = format_budget_category_label(category)
        status = str(_read_budget_item_value(item, "status") or "on_track")
        projected_status = str(
            _read_budget_item_value(item, "projected_status") or status
        )
        projected_remaining_amount = float(
            _read_budget_item_value(item, "projected_remaining_amount") or 0.0
        )
        projected_usage_percent = float(
            _read_budget_item_value(item, "projected_usage_percent") or 0.0
        )
        days_remaining = int(_read_budget_item_value(item, "days_remaining") or 0)
        daily_allowance = _read_budget_item_value(item, "daily_allowance")

        if projected_status == "over_budget":
            over_amount = abs(projected_remaining_amount)
            recommended_amount = round(
                max(
                    float(_read_budget_item_value(item, "amount") or 0.0),
                    float(_read_budget_item_value(item, "projected_spent_amount") or 0.0),
                ),
                2,
            )
            detail = f"Projected to finish {format_budget_currency(over_amount)} over budget."
            if days_remaining > 0:
                daily_gap = over_amount / days_remaining
                detail += (
                    f" To recover this month, trim about {format_budget_currency(daily_gap)} "
                    "per day from the current pace."
                )
            detail += (
                f" If you want next month to reflect the current pace, start around "
                f"{format_budget_currency(recommended_amount)}."
            )
            insights.append(
                {
                    "category": category,
                    "severity": "action",
                    "title": f"{label} needs attention now",
                    "detail": detail,
                    "recommended_amount": recommended_amount,
                    "impact": over_amount,
                }
            )
            continue

        if projected_status == "at_risk":
            recommended_amount = round(
                max(
                    float(_read_budget_item_value(item, "amount") or 0.0),
                    float(_read_budget_item_value(item, "projected_spent_amount") or 0.0),
                ),
                2,
            )
            detail = (
                f"Projected to use {projected_usage_percent:.1f}% of the budget by month end."
            )
            if daily_allowance is not None:
                allowance_value = abs(float(daily_allowance))
                if float(daily_allowance) >= 0:
                    detail += (
                        f" Staying near {format_budget_currency(allowance_value)} per day or less "
                        "should keep it manageable."
                    )
                else:
                    detail += (
                        f" It is already running about {format_budget_currency(allowance_value)} "
                        "per day over the safe pace."
                    )
            detail += (
                f" If you want a more realistic target for next month, start around "
                f"{format_budget_currency(recommended_amount)}."
            )
            insights.append(
                {
                    "category": category,
                    "severity": "watch",
                    "title": f"{label} is getting tight",
                    "detail": detail,
                    "recommended_amount": recommended_amount,
                    "impact": projected_usage_percent,
                }
            )
            continue

        if status == "on_track" and projected_remaining_amount > 0:
            insights.append(
                {
                    "category": category,
                    "severity": "positive",
                    "title": f"{label} is creating room",
                    "detail": (
                        f"Projected to finish with {format_budget_currency(projected_remaining_amount)} "
                        "remaining if the current pace holds."
                    ),
                    "impact": projected_remaining_amount,
                }
            )

    severity_order = {"action": 0, "watch": 1, "positive": 2}
    ordered = sorted(
        insights,
        key=lambda item: (
            severity_order.get(str(item["severity"]), 3),
            -float(item.get("impact", 0.0)),
            str(item["category"]).lower(),
        ),
    )

    return [
        {
            "category": item["category"],
            "severity": item["severity"],
            "title": item["title"],
            "detail": item["detail"],
            "recommended_amount": item.get("recommended_amount"),
        }
        for item in ordered[:limit]
    ]


def build_next_month_budget_target(
    item: Any,
) -> dict[str, float | bool | str]:
    current_amount = float(_read_budget_item_value(item, "amount") or 0.0)
    spent_amount = float(_read_budget_item_value(item, "spent_amount") or 0.0)
    projected_spent_amount = float(
        _read_budget_item_value(item, "projected_spent_amount") or 0.0
    )
    projected_status = str(_read_budget_item_value(item, "projected_status") or "")
    days_elapsed = int(_read_budget_item_value(item, "days_elapsed") or 0)

    if current_amount <= 0:
        return {
            "target_amount": 0.0,
            "adjusted": False,
            "reason": "Current budget amount is invalid, so no paced target was created.",
        }

    if days_elapsed < 7 or projected_spent_amount <= 0:
        return {
            "target_amount": round(current_amount, 2),
            "adjusted": False,
            "reason": (
                "There is not enough pace data yet, so the current budget amount was carried forward."
            ),
        }

    if projected_status in {"over_budget", "at_risk"}:
        target_amount = max(current_amount, projected_spent_amount)
        reason = "Raised to reflect the current projected month-end pace."
    else:
        target_amount = max(spent_amount, projected_spent_amount * 1.05)
        reason = "Tuned to the current pace with a small planning buffer."

    target_amount = round(max(target_amount, 0.01), 2)
    adjusted = abs(target_amount - current_amount) >= 0.01

    return {
        "target_amount": target_amount,
        "adjusted": adjusted,
        "reason": reason,
    }
